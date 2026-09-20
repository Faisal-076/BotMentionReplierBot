"""
Bot Cluster Manager: Runs multiple bot instances concurrently in parallel asyncio tasks.
"""

import asyncio
import logging
from typing import List
from config import BotConfig
from replier import MentionReplier
from telegram_client import TelegramClient

logger = logging.getLogger("BotCluster")


class SingleBotRunner:
    def __init__(self, token: str, config: BotConfig):
        self.token = token
        self.config = config
        self.client = TelegramClient(token)
        self.replier = MentionReplier(self.client, config)
        self.bot_username = "Unknown"
        self.is_running = False

    async def initialize(self) -> bool:
        """Verifies bot token and fetches bot profile."""
        res = await self.client.get_me()
        if not res.get("ok"):
            logger.error(
                f"Failed to initialize bot with token ending in ...{self.token[-6:]}: {res.get('description')}"
            )
            return False

        info = res["result"]
        self.bot_username = info.get("username", "Unknown")
        guest_supported = info.get("supports_guest_queries", False)

        logger.info(
            f"🤖 Bot [@{self.bot_username}] connected successfully! "
            f"(Guest Mode Enabled in Telegram: {guest_supported})"
        )

        if not guest_supported:
            logger.warning(
                f"⚠️ NOTICE: [@{self.bot_username}] does not have 'Guest Mode' enabled yet. "
                f"Please open @BotFather -> /mybots -> Bot Settings -> Guest Mode to enable."
            )

        # Clear any stale webhook before polling
        await self.client.delete_webhook(drop_pending_updates=False)
        return True

    async def run_polling(self) -> None:
        """Long-polling loop for this bot instance."""
        self.is_running = True
        offset = None
        logger.info(f"🚀 [@{self.bot_username}] Started polling for mentions...")

        while self.is_running:
            try:
                updates = await self.client.get_updates(
                    offset=offset,
                    timeout=self.config.poll_timeout,
                    allowed_updates=["guest_message", "message", "edited_message"],
                )

                for update in updates:
                    update_id = update.get("update_id")
                    if update_id is not None:
                        offset = update_id + 1

                    # Process in background task for zero latency
                    asyncio.create_task(self.replier.process_update(update))

            except asyncio.CancelledError:
                logger.info(f"Stopping polling for [@{self.bot_username}]...")
                break
            except Exception as e:
                logger.error(f"Error in polling loop for [@{self.bot_username}]: {e}")
                await asyncio.sleep(2)

        await self.client.close()

    def stop(self) -> None:
        self.is_running = False


class BotCluster:
    def __init__(self, config: BotConfig):
        self.config = config
        self.runners: List[SingleBotRunner] = []
        self._tasks: List[asyncio.Task] = []

    async def start(self) -> None:
        """Initialize all bots in the cluster and start polling in parallel."""
        tokens = self.config.bot_tokens
        logger.info(f"Initializing Bot Cluster with {len(tokens)} bot(s)...")

        for token in tokens:
            runner = SingleBotRunner(token, self.config)
            success = await runner.initialize()
            if success:
                self.runners.append(runner)

        if not self.runners:
            logger.error("No bots could be initialized. Please check your BOT_TOKENS.")
            return

        logger.info(f"⚡ Launching {len(self.runners)} bot instance(s) concurrently...")
        self._tasks = [
            asyncio.create_task(runner.run_polling()) for runner in self.runners
        ]

        try:
            await asyncio.gather(*self._tasks)
        except asyncio.CancelledError:
            logger.info("Cluster shutdown initiated.")
            for runner in self.runners:
                runner.stop()
            await asyncio.gather(*self._tasks, return_exceptions=True)
