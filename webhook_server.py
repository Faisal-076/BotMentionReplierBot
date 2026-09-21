"""
FastAPI Webhook Server for high-performance production deployments.
"""

import hashlib
import logging
from typing import Any, Dict
from fastapi import FastAPI, HTTPException, Request
from config import BotConfig
from replier import MentionReplier
from telegram_client import TelegramClient

logger = logging.getLogger("WebhookServer")

app = FastAPI(title="Telegram Guest Mention Replier Webhook")


class WebhookManager:
    def __init__(self, config: BotConfig):
        self.config = config
        self.clients: Dict[str, TelegramClient] = {}
        self.repliers: Dict[str, MentionReplier] = {}

    async def initialize(self) -> None:
        for token in self.config.bot_tokens:
            token_hash = hashlib.sha256(token.encode()).hexdigest()[:16]
            client = TelegramClient(token)
            me = await client.get_me()
            if me.get("ok"):
                self.clients[token_hash] = client
                self.repliers[token_hash] = MentionReplier(client, self.config)
                logger.info(
                    f"Webhook registered for bot @{me['result'].get('username')} [Route: /webhook/{token_hash}]"
                )

    async def register_webhooks_with_telegram(self) -> None:
        if not self.config.webhook_url_base:
            raise ValueError("WEBHOOK_URL_BASE is required for webhook mode.")

        for token_hash, client in self.clients.items():
            webhook_url = f"{self.config.webhook_url_base}/webhook/{token_hash}"
            res = await client.set_webhook(
                url=webhook_url,
                allowed_updates=["guest_message", "message", "edited_message", "inline_query"],
                drop_pending_updates=False,
            )
            if res.get("ok"):
                logger.info(f"Telegram Webhook set: {webhook_url}")
            else:
                logger.error(
                    f"Failed to set webhook for {token_hash}: {res.get('description')}"
                )


manager: WebhookManager = None  # Initialized on app startup


@app.on_event("startup")
async def startup_event():
    global manager
    from config import config

    manager = WebhookManager(config)
    await manager.initialize()
    if config.webhook_url_base:
        await manager.register_webhooks_with_telegram()


@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "active_bots": len(manager.clients) if manager else 0,
    }


@app.post("/webhook/{token_hash}")
async def handle_webhook(token_hash: str, request: Request):
    if not manager or token_hash not in manager.repliers:
        raise HTTPException(status_code=404, detail="Bot not found")

    try:
        update: Dict[str, Any] = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    replier = manager.repliers[token_hash]
    # Handle update asynchronously in background with exception logging
    import asyncio

    task = asyncio.create_task(replier.process_update(update))
    task.add_done_callback(lambda t: logger.error(f"Webhook update error: {t.exception()}") if not t.cancelled() and t.exception() else None)
    return {"ok": True}
