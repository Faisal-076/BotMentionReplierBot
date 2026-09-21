"""
Asynchronous Telegram Bot API Client supporting Bot API 10.0 Guest Mode and standard messaging.
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional
import aiohttp

logger = logging.getLogger("TelegramClient")


class TelegramClient:
    def __init__(self, token: str, session: Optional[aiohttp.ClientSession] = None):
        self.token = token.strip()
        self.api_url = f"https://api.telegram.org/bot{self.token}"
        self._session = session
        self._reply_session: Optional[aiohttp.ClientSession] = None
        self._owns_session = False
        self.bot_info: Optional[Dict[str, Any]] = None
        self._prewarm_task: Optional[asyncio.Task] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            connector = aiohttp.TCPConnector(
                limit=50,
                keepalive_timeout=75,
                ttl_dns_cache=600,
                enable_cleanup_closed=True,
            )
            self._session = aiohttp.ClientSession(
                connector=connector,
                timeout=aiohttp.ClientTimeout(total=35, connect=4),
            )
            self._owns_session = True
        return self._session

    async def _get_reply_session(self) -> aiohttp.ClientSession:
        """Dedicated pre-warmed session with zero-latency connection pool for instant replies."""
        if self._reply_session is None or self._reply_session.closed:
            connector = aiohttp.TCPConnector(
                limit=50,
                keepalive_timeout=120,
                ttl_dns_cache=1200,
                enable_cleanup_closed=True,
            )
            self._reply_session = aiohttp.ClientSession(
                connector=connector,
                timeout=aiohttp.ClientTimeout(total=8, connect=2),
            )
            try:
                self._prewarm_task = asyncio.create_task(self._prewarm_reply_connection())
            except Exception:
                pass
        return self._reply_session

    async def _prewarm_reply_connection(self):
        """Pre-establishes a live TLS socket to Telegram so replies dispatch in <30ms."""
        try:
            if self._reply_session and not self._reply_session.closed:
                async with self._reply_session.get("https://api.telegram.org/") as resp:
                    await resp.read()
        except Exception:
            pass

    async def close(self) -> None:
        if self._prewarm_task and not self._prewarm_task.done():
            self._prewarm_task.cancel()
        if self._owns_session and self._session and not self._session.closed:
            await self._session.close()
        if self._reply_session and not self._reply_session.closed:
            await self._reply_session.close()

    async def _request(
        self,
        method: str,
        endpoint: str,
        payload: Optional[Dict[str, Any]] = None,
        use_reply_session: bool = False,
    ) -> Dict[str, Any]:
        session = (
            await self._get_reply_session()
            if use_reply_session
            else await self._get_session()
        )
        url = f"{self.api_url}/{endpoint}"

        for attempt in range(1, 4):
            try:
                async with session.request(method, url, json=payload) as response:
                    data = await response.json()
                    if not data.get("ok"):
                        error_code = data.get("error_code")
                        description = data.get("description", "")
                        # Handle Telegram Rate Limiting (HTTP 429)
                        if error_code == 429:
                            retry_after = data.get("parameters", {}).get("retry_after", 2)
                            logger.warning(
                                f"Rate limited on {endpoint}. Sleeping for {retry_after}s..."
                            )
                            await asyncio.sleep(retry_after)
                            continue
                        logger.error(
                            f"Telegram API Error ({endpoint}) [{error_code}]: {description}"
                        )
                    return data
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                logger.warning(
                    f"Network error on {endpoint} (attempt {attempt}/3): {e}"
                )
                if attempt < 3:
                    await asyncio.sleep(1.5 * attempt)
                else:
                    return {"ok": False, "description": str(e)}

        return {"ok": False, "description": "Max retries exceeded"}

    async def get_me(self) -> Dict[str, Any]:
        """Fetch bot user details from Telegram."""
        result = await self._request("GET", "getMe")
        if result.get("ok"):
            self.bot_info = result.get("result")
        return result

    async def get_updates(
        self,
        offset: Optional[int] = None,
        limit: int = 100,
        timeout: int = 25,
        allowed_updates: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Poll for updates using getUpdates.
        Includes 'guest_message' for Guest Mode mention capture.
        """
        if allowed_updates is None:
            allowed_updates = ["guest_message", "message", "edited_message"]

        payload: Dict[str, Any] = {
            "limit": limit,
            "timeout": timeout,
            "allowed_updates": allowed_updates,
        }
        if offset is not None:
            payload["offset"] = offset

        res = await self._request("POST", "getUpdates", payload)
        if res.get("ok"):
            return res.get("result", [])
        return []

    async def answer_guest_query(
        self,
        guest_query_id: str,
        text: str,
        parse_mode: str = "HTML",
        disable_web_page_preview: bool = False,
    ) -> Dict[str, Any]:
        """
        Respond to a guest mention in a group where the bot is not a member.
        Uses Telegram Bot API 10.0 answerGuestQuery method with InlineQueryResultArticle.
        """
        import uuid

        # Support Telegram 10.1+ Rich Messages (heading1/h1) for extra large, banner-like font
        if "<h1" in text.lower() or "<h2" in text.lower():
            input_content = {
                "rich_message": {
                    "html": text
                }
            }
        else:
            input_content = {
                "message_text": text,
                "parse_mode": parse_mode,
                "link_preview_options": {"is_disabled": disable_web_page_preview},
            }

        result = {
            "type": "article",
            "id": str(uuid.uuid4())[:32],
            "title": "Reply",
            "input_message_content": input_content,
        }

        payload: Dict[str, Any] = {
            "guest_query_id": guest_query_id,
            "result": result,
        }
        logger.info(f"Dispatching answerGuestQuery (ID: {guest_query_id}, rich={bool('<h1' in text.lower())})")
        resp = await self._request("POST", "answerGuestQuery", payload, use_reply_session=True)
        
        # Fallback to standard message_text if rich_message was rejected by a server rule
        if not resp.get("ok") and "rich_message" in input_content:
            import re
            logger.warning(f"Rich message rejected ({resp.get('description')}), attempting standard HTML fallback...")
            fallback_text = re.sub(r"</?h[1-6]>", "\n\n", text).strip()
            fallback_result = {
                "type": "article",
                "id": str(uuid.uuid4())[:32],
                "title": "Reply",
                "input_message_content": {
                    "message_text": f"<b>{fallback_text}</b>",
                    "parse_mode": "HTML",
                    "link_preview_options": {"is_disabled": disable_web_page_preview},
                },
            }
            return await self._request(
                "POST",
                "answerGuestQuery",
                {"guest_query_id": guest_query_id, "result": fallback_result},
                use_reply_session=True,
            )
        return resp

    async def answer_inline_query(
        self,
        inline_query_id: str,
        text: str,
        title: str = "Send Message",
        parse_mode: str = "HTML",
    ) -> Dict[str, Any]:
        """Resolves inline query loading spinner immediately."""
        import uuid

        results = [
            {
                "type": "article",
                "id": str(uuid.uuid4())[:32],
                "title": title,
                "input_message_content": {
                    "message_text": text,
                    "parse_mode": parse_mode,
                },
            }
        ]
        payload = {
            "inline_query_id": inline_query_id,
            "results": results,
            "cache_time": 1,
        }
        return await self._request("POST", "answerInlineQuery", payload, use_reply_session=True)

    async def send_message(
        self,
        chat_id: int | str,
        text: str,
        reply_to_message_id: Optional[int] = None,
        parse_mode: str = "HTML",
        disable_web_page_preview: bool = False,
    ) -> Dict[str, Any]:
        """
        Standard reply message for groups where the bot is an official member.
        """
        # If rich headings are present, attempt sendRichMessage first
        if "<h1" in text.lower() or "<h2" in text.lower():
            rich_payload: Dict[str, Any] = {
                "chat_id": chat_id,
                "rich_message": {"html": text},
            }
            if reply_to_message_id:
                rich_payload["reply_parameters"] = {
                    "message_id": reply_to_message_id,
                    "allow_sending_without_reply": True,
                }
            rich_resp = await self._request("POST", "sendRichMessage", rich_payload, use_reply_session=True)
            if rich_resp.get("ok"):
                return rich_resp
            import re
            text = f"<b>{re.sub(r'</?h[1-6]>', '\n\n', text).strip()}</b>"

        payload: Dict[str, Any] = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "link_preview_options": {"is_disabled": disable_web_page_preview},
        }
        if reply_to_message_id:
            payload["reply_parameters"] = {
                "message_id": reply_to_message_id,
                "allow_sending_without_reply": True,
            }

        return await self._request("POST", "sendMessage", payload, use_reply_session=True)

    async def delete_webhook(self, drop_pending_updates: bool = False) -> Dict[str, Any]:
        """Remove active webhook before starting polling."""
        return await self._request(
            "POST", "deleteWebhook", {"drop_pending_updates": drop_pending_updates}
        )

    async def set_webhook(
        self,
        url: str,
        allowed_updates: Optional[List[str]] = None,
        drop_pending_updates: bool = False,
    ) -> Dict[str, Any]:
        """Configure webhook URL."""
        if allowed_updates is None:
            allowed_updates = ["guest_message", "message", "edited_message"]
        payload = {
            "url": url,
            "allowed_updates": allowed_updates,
            "drop_pending_updates": drop_pending_updates,
        }
        return await self._request("POST", "setWebhook", payload)
