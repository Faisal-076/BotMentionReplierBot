"""
Core replier engine for handling incoming Telegram updates, formatting messages,
and triggering Guest Mode (answerGuestQuery) or Member Mode replies.
"""

import asyncio
from datetime import datetime, timezone
import html
import logging
import random
from typing import Any, Dict, Optional, Set
from config import BotConfig
from telegram_client import TelegramClient

logger = logging.getLogger("MentionReplier")


class MentionReplier:
    def __init__(self, client: TelegramClient, config: BotConfig):
        self.client = client
        self.config = config
        self.processed_ids: Set[str] = set()
        self._cache_limit = 5000

    def _track_processed(self, query_id: str) -> bool:
        """Returns True if already processed, otherwise marks as processed."""
        if query_id in self.processed_ids:
            return True
        if len(self.processed_ids) >= self._cache_limit:
            # Clear half of the cache to avoid unbound memory growth
            self.processed_ids = set(list(self.processed_ids)[self._cache_limit // 2 :])
        self.processed_ids.add(query_id)
        return False

    def format_reply_text(
        self,
        caller_user: Optional[Dict[str, Any]] = None,
        chat: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Picks a random template and substitutes variables."""
        template = random.choice(self.config.reply_templates)

        first_name = (caller_user or {}).get("first_name", "Friend")
        last_name = (caller_user or {}).get("last_name", "")
        username = (caller_user or {}).get("username")
        user_id = (caller_user or {}).get("id", "")
        chat_title = (chat or {}).get("title", "Group")

        bot_name = (self.client.bot_info or {}).get("first_name", "Bot")
        bot_username = (self.client.bot_info or {}).get("username", "")

        user_tag = f"@{username}" if username else first_name

        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

        # Safe HTML escaping for user inputs
        if self.config.parse_mode.upper() == "HTML":
            first_name = html.escape(first_name)
            last_name = html.escape(last_name)
            user_tag = html.escape(user_tag)
            chat_title = html.escape(chat_title)

        try:
            formatted = template.format(
                first_name=first_name,
                last_name=last_name,
                username=user_tag,
                user_id=user_id,
                bot_name=bot_name,
                bot_username=f"@{bot_username}" if bot_username else "",
                chat_title=chat_title,
                date=now_str,
            )
        except Exception:
            formatted = template

        if self.config.parse_mode.upper() == "HTML":
            import re
            # Auto-convert Markdown link syntax [text](url) to HTML <a href="url">text</a>
            formatted = re.sub(r"\[([^\]]+)\]\((https?://[^\)]+)\)", r'<a href="\2">\1</a>', formatted)

        return formatted

    async def handle_guest_message(self, guest_msg: Dict[str, Any]) -> None:
        """
        Handles Guest Mode mention event.
        Dispatches answerGuestQuery without needing to be in the group.
        """
        guest_query_id = guest_msg.get("guest_query_id")
        if not guest_query_id:
            logger.warning("Received guest_message without guest_query_id.")
            return

        if self._track_processed(f"guest_{guest_query_id}"):
            logger.info(f"Duplicate guest_query_id ignored: {guest_query_id}")
            return

        caller_user = (
            guest_msg.get("guest_bot_caller_user")
            or guest_msg.get("from")
            or {}
        )
        caller_chat = (
            guest_msg.get("guest_bot_caller_chat")
            or guest_msg.get("chat")
            or {}
        )
        mention_text = guest_msg.get("text", "")

        user_name = caller_user.get("first_name", "Unknown")
        user_handle = f"@{caller_user.get('username')}" if caller_user.get('username') else ""
        logger.info(
            f"🎯 [Guest Mention] Triggered by {user_name} {user_handle} in chat '{caller_chat.get('title', 'Unknown')}'"
        )
        logger.debug(f"Mention text: {mention_text}")

        if self.config.reply_delay > 0:
            await asyncio.sleep(self.config.reply_delay)

        reply_content = self.format_reply_text(caller_user, caller_chat)

        result = await self.client.answer_guest_query(
            guest_query_id=guest_query_id,
            text=reply_content,
            parse_mode=self.config.parse_mode,
            disable_web_page_preview=self.config.disable_web_page_preview,
        )

        if result.get("ok"):
            logger.info(
                f"✅ Successfully replied to Guest Mention in '{caller_chat.get('title', 'Unknown')}' (Query ID: {guest_query_id})"
            )
        else:
            err_desc = result.get("description", "Unknown error")
            err_code = result.get("error_code", "Unknown code")
            logger.error(
                f"❌ Failed to reply to Guest Mention in '{caller_chat.get('title', 'Unknown')}': [{err_code}] {err_desc}"
            )
            # Auto-retry with plain text if formatting/link was rejected
            if any(term in err_desc.lower() for term in ["parse", "entity", "link"]):
                import re

                logger.info("🔄 Retrying Guest Query with plain text fallback...")
                plain_text = re.sub(r"<[^>]+>", "", reply_content)
                retry_res = await self.client.answer_guest_query(
                    guest_query_id=guest_query_id,
                    text=plain_text,
                    parse_mode="",
                    disable_web_page_preview=True,
                )
                if retry_res.get("ok"):
                    logger.info("✅ Fallback plain text reply succeeded!")
                else:
                    logger.error(f"❌ Fallback retry also failed: {retry_res.get('description')}")

    async def handle_regular_message(self, message: Dict[str, Any]) -> None:
        """
        Handles regular group messages where the bot is a member.
        Checks for mentions and replies.
        """
        msg_id = message.get("message_id")
        chat = message.get("chat", {})
        chat_id = chat.get("id")
        from_user = message.get("from", {})
        text = message.get("text", "") or message.get("caption", "")

        if not chat_id or not msg_id or not text:
            return

        # Check if bot is mentioned
        bot_username = (self.client.bot_info or {}).get("username", "").lower()
        if not bot_username:
            return

        is_mentioned = False
        if f"@{bot_username}" in text.lower():
            is_mentioned = True
        else:
            # Check entities
            entities = message.get("entities", []) + message.get("caption_entities", [])
            for ent in entities:
                if ent.get("type") == "mention":
                    offset = ent.get("offset", 0)
                    length = ent.get("length", 0)
                    entity_text = text[offset : offset + length].lower()
                    if entity_text == f"@{bot_username}":
                        is_mentioned = True
                        break

        if not is_mentioned:
            return

        dedup_key = f"msg_{chat_id}_{msg_id}"
        if self._track_processed(dedup_key):
            return

        logger.info(
            f"🎯 [Member Mention] Bot mentioned by {from_user.get('first_name')} in chat '{chat.get('title')}'"
        )

        if self.config.reply_delay > 0:
            await asyncio.sleep(self.config.reply_delay)

        reply_content = self.format_reply_text(from_user, chat)

        result = await self.client.send_message(
            chat_id=chat_id,
            text=reply_content,
            reply_to_message_id=msg_id,
            parse_mode=self.config.parse_mode,
            disable_web_page_preview=self.config.disable_web_page_preview,
        )

        if result.get("ok"):
            logger.info(f"✅ Successfully replied to Member Mention in chat {chat_id}")
        else:
            logger.error(f"❌ Failed to reply in chat {chat_id}: {result.get('description')}")

    async def process_update(self, update: Dict[str, Any]) -> None:
        """Route update to the appropriate handler based on REPLY_MODE."""
        update_keys = [k for k in update.keys() if k != "update_id"]
        logger.debug(f"Incoming update [{update.get('update_id')}]: {update_keys}")

        # 1. Guest Mode Mention
        if "guest_message" in update and self.config.reply_mode in ("guest", "both"):
            await self.handle_guest_message(update["guest_message"])

        # 2. Standard Message Mention (in group where bot is a member)
        elif "message" in update and self.config.reply_mode in ("member", "both"):
            await self.handle_regular_message(update["message"])

        # 3. Edited Message Mention
        elif "edited_message" in update and self.config.reply_mode in ("member", "both"):
            await self.handle_regular_message(update["edited_message"])

        # 4. Inline Query (If triggered via @AutoBotStore_bot search)
        elif "inline_query" in update:
            iq = update["inline_query"]
            iq_id = iq.get("id")
            from_user = iq.get("from", {})
            reply_text = self.format_reply_text(from_user, None)
            await self.client.answer_inline_query(
                inline_query_id=iq_id,
                text=reply_text,
                title="Send Bot Reply",
                parse_mode=self.config.parse_mode,
            )
