"""
Main CLI entry point for BotMentionReplierBot.
"""

import asyncio
import logging
import os
import sys

# Ensure UTF-8 stdout/stderr on Windows console
if sys.platform == "win32":
    try:
        if sys.stdout.encoding.lower() != "utf-8":
            sys.stdout.reconfigure(encoding="utf-8")
        if sys.stderr.encoding.lower() != "utf-8":
            sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass
else:
    # High-performance event loop for Linux production containers
    try:
        import uvloop
        uvloop.install()
    except Exception:
        pass

from config import config
from cluster import BotCluster
from telegram_client import TelegramClient

# Setup clean console logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("Main")


async def verify_bots():
    """Verifies all configured bot tokens and inspects Guest Mode status."""
    print("\n==========================================")
    print("🔍 BOT TOKEN & GUEST MODE VERIFICATION")
    print("==========================================")

    tokens = config.bot_tokens
    if not tokens:
        print("❌ Error: No BOT_TOKENS defined in .env file.")
        return

    print(f"Checking {len(tokens)} bot token(s)...\n")

    for i, token in enumerate(tokens, 1):
        client = TelegramClient(token)
        try:
            res = await client.get_me()
            if res.get("ok"):
                info = res["result"]
                bot_id = info.get("id")
                username = info.get("username")
                name = info.get("first_name")
                guest_mode = info.get("supports_guest_queries", False)

                print(f"[{i}] ✅ {name} (@{username}) | ID: {bot_id}")
                if guest_mode:
                    print(
                        "    🌟 Guest Mode: ENABLED! (Can reply to mentions without group membership)"
                    )
                else:
                    print(
                        "    ⚠️  Guest Mode: NOT ENABLED in @BotFather"
                    )
                    print(
                        "        -> To enable: Go to @BotFather > /mybots > Bot Settings > Guest Mode > Turn On"
                    )
            else:
                print(
                    f"[{i}] ❌ Invalid Token (...{token[-8:]}): {res.get('description')}"
                )
        except Exception as e:
            print(f"[{i}] ❌ Connection failed: {e}")
        finally:
            await client.close()

    print("\n==========================================\n")


def run_polling():
    """Starts the bot cluster in Long Polling mode."""
    try:
        config.validate()
    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        sys.exit(1)

    cluster = BotCluster(config)
    try:
        asyncio.run(cluster.start())
    except KeyboardInterrupt:
        logger.info("Bot cluster stopped by user.")


def run_webhook():
    """Starts the bot cluster with FastAPI Webhook server."""
    try:
        config.validate()
    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        sys.exit(1)

    import uvicorn

    logger.info(
        f"Starting Webhook server on {config.webhook_host}:{config.webhook_port}..."
    )
    uvicorn.run(
        "webhook_server:app",
        host=config.webhook_host,
        port=config.webhook_port,
        reload=False,
    )


def run_dashboard():
    """Starts the modern Web UI Control Center and Bot Cluster simultaneously."""
    import uvicorn

    port = int(os.environ.get("PORT", config.webhook_port))
    logger.info(
        f"🚀 Starting Web UI Dashboard Control Center on http://{config.webhook_host}:{port}"
    )
    uvicorn_kwargs = {
        "app": "dashboard_server:app",
        "host": config.webhook_host,
        "port": port,
        "reload": False,
    }
    if sys.platform != "win32":
        uvicorn_kwargs["loop"] = "uvloop"
        uvicorn_kwargs["http"] = "httptools"
    uvicorn.run(**uvicorn_kwargs)


if __name__ == "__main__":
    action = sys.argv[1] if len(sys.argv) > 1 else "dashboard"

    if action == "verify":
        asyncio.run(verify_bots())
    elif action == "webhook":
        run_webhook()
    elif action in ("dashboard", "ui", "web"):
        run_dashboard()
    elif action in ("run", "poll", "start"):
        run_polling()
    else:
        print("Usage: python main.py [dashboard|run|verify|webhook]")
        sys.exit(1)
