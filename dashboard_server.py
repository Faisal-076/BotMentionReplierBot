"""
FastAPI Dashboard Server providing Web UI control center and real-time bot management.
"""

import asyncio
from collections import deque
from datetime import datetime, timezone
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from cluster import BotCluster
from config import BotConfig, config
from telegram_client import TelegramClient

BASE_DIR = Path(__file__).parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"

app = FastAPI(title="Telegram Bot Mention Replier Control Center")

# Ensure static and templates directories exist
TEMPLATES_DIR.mkdir(exist_ok=True)
STATIC_DIR.mkdir(exist_ok=True)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# In-memory circular buffer for live logs
log_buffer: deque = deque(maxlen=250)


class UILogHandler(logging.Handler):
    def emit(self, record):
        try:
            msg = self.format(record)
            time_str = datetime.now(timezone.utc).strftime("%H:%M:%S")
            log_buffer.append(
                {
                    "time": time_str,
                    "level": record.levelname,
                    "logger": record.name,
                    "message": record.getMessage(),
                    "raw": msg,
                }
            )
        except Exception:
            pass


ui_handler = UILogHandler()
ui_handler.setFormatter(
    logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
)
logging.getLogger().addHandler(ui_handler)
logger = logging.getLogger("Dashboard")


class ClusterState:
    def __init__(self):
        self.cluster: Optional[BotCluster] = None
        self.task: Optional[asyncio.Task] = None
        self.is_running: bool = False
        self.start_time: Optional[datetime] = None
        self.total_mentions_handled: int = 0


state = ClusterState()


class ConfigUpdateRequest(BaseModel):
    bot_tokens: List[str]
    reply_mode: str
    parse_mode: str
    disable_web_page_preview: bool
    reply_delay: float
    reply_templates: List[str]
    poll_timeout: int = 25


def save_env_file(cfg: ConfigUpdateRequest) -> None:
    """Safely updates the .env file with new settings."""
    env_file = BASE_DIR / ".env"
    tokens_str = ",".join([t.strip() for t in cfg.bot_tokens if t.strip()])
    templates_str = "|||".join([t.strip() for t in cfg.reply_templates if t.strip()])

    content = f"""# ================================================================
# TELEGRAM GUEST & MENTION REPLIER BOT - CONFIGURATION
# Updated via Web UI Control Center at {datetime.now(timezone.utc).isoformat()}
# ================================================================

BOT_TOKENS={tokens_str}
REPLY_MODE={cfg.reply_mode}
PARSE_MODE={cfg.parse_mode}
DISABLE_WEB_PAGE_PREVIEW={"true" if cfg.disable_web_page_preview else "false"}
REPLY_DELAY={cfg.reply_delay}
REPLY_TEMPLATES={templates_str}
POLL_TIMEOUT={cfg.poll_timeout}
WEBHOOK_HOST=0.0.0.0
WEBHOOK_PORT=8000
WEBHOOK_URL_BASE=
"""
    env_file.write_text(content, encoding="utf-8")

    # Reload in-memory global config
    config.bot_tokens = [t.strip() for t in cfg.bot_tokens if t.strip()]
    config.reply_mode = cfg.reply_mode
    config.parse_mode = cfg.parse_mode
    config.disable_web_page_preview = cfg.disable_web_page_preview
    config.reply_delay = cfg.reply_delay
    config.reply_templates = [t.strip() for t in cfg.reply_templates if t.strip()]
    config.poll_timeout = cfg.poll_timeout


async def start_cluster_internal():
    """Starts the bot cluster task."""
    if state.is_running:
        return
    try:
        config.validate()
    except Exception as e:
        logger.error(f"Cannot start cluster: {e}")
        return

    state.cluster = BotCluster(config)
    state.is_running = True
    state.start_time = datetime.now(timezone.utc)
    state.task = asyncio.create_task(state.cluster.start())
    logger.info("Bot Cluster started from Control Center.")


async def stop_cluster_internal():
    """Stops the running bot cluster."""
    if not state.is_running:
        return
    state.is_running = False
    if state.cluster:
        for runner in state.cluster.runners:
            runner.stop()
    if state.task:
        state.task.cancel()
        try:
            await state.task
        except asyncio.CancelledError:
            pass
    logger.info("Bot Cluster stopped from Control Center.")


@app.on_event("startup")
async def app_startup():
    # Auto-start bot cluster if tokens exist
    if config.bot_tokens:
        asyncio.create_task(start_cluster_internal())


@app.get("/", response_class=HTMLResponse)
async def serve_dashboard():
    index_file = TEMPLATES_DIR / "index.html"
    if not index_file.exists():
        return HTMLResponse("<h1>Dashboard loading... Please refresh in a moment.</h1>")
    return HTMLResponse(index_file.read_text(encoding="utf-8"))


@app.get("/api/status")
async def get_status():
    uptime = 0
    if state.is_running and state.start_time:
        uptime = int((datetime.now(timezone.utc) - state.start_time).total_seconds())

    runners_info = []
    if state.cluster and state.cluster.runners:
        for r in state.cluster.runners:
            runners_info.append(
                {
                    "username": r.bot_username,
                    "is_running": r.is_running,
                    "guest_supported": (r.client.bot_info or {}).get(
                        "supports_guest_queries", False
                    ),
                }
            )

    return {
        "is_running": state.is_running,
        "uptime_seconds": uptime,
        "active_bots_count": len(runners_info),
        "bots": runners_info,
        "configured_tokens_count": len(config.bot_tokens),
        "reply_mode": config.reply_mode,
        "templates_count": len(config.reply_templates),
    }


@app.get("/api/config")
async def get_current_config():
    return {
        "bot_tokens": config.bot_tokens,
        "reply_mode": config.reply_mode,
        "parse_mode": config.parse_mode,
        "disable_web_page_preview": config.disable_web_page_preview,
        "reply_delay": config.reply_delay,
        "reply_templates": config.reply_templates,
        "poll_timeout": config.poll_timeout,
    }


@app.post("/api/config")
async def update_config(payload: ConfigUpdateRequest):
    try:
        save_env_file(payload)
        logger.info("Configuration updated and saved to .env via Web UI.")
        return {"ok": True, "message": "Configuration saved successfully!"}
    except Exception as e:
        logger.error(f"Failed to save configuration: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/cluster/start")
async def api_start_cluster():
    if state.is_running:
        return {"ok": True, "message": "Cluster is already running."}
    await start_cluster_internal()
    return {"ok": True, "message": "Cluster started successfully."}


@app.post("/api/cluster/stop")
async def api_stop_cluster():
    if not state.is_running:
        return {"ok": True, "message": "Cluster is already stopped."}
    await stop_cluster_internal()
    return {"ok": True, "message": "Cluster stopped successfully."}


@app.post("/api/cluster/restart")
async def api_restart_cluster():
    await stop_cluster_internal()
    await asyncio.sleep(1)
    await start_cluster_internal()
    return {"ok": True, "message": "Cluster restarted successfully."}


@app.get("/api/tokens/verify")
async def api_verify_tokens():
    """Verify live status and Guest Mode on Telegram servers for all configured tokens."""
    results = []
    for token in config.bot_tokens:
        client = TelegramClient(token)
        try:
            res = await client.get_me()
            if res.get("ok"):
                info = res["result"]
                results.append(
                    {
                        "token_preview": f"...{token[-8:]}",
                        "id": info.get("id"),
                        "first_name": info.get("first_name"),
                        "username": info.get("username"),
                        "guest_mode": info.get("supports_guest_queries", False),
                        "status": "valid",
                    }
                )
            else:
                results.append(
                    {
                        "token_preview": f"...{token[-8:]}",
                        "status": "invalid",
                        "error": res.get("description"),
                    }
                )
        except Exception as e:
            results.append(
                {
                    "token_preview": f"...{token[-8:]}",
                    "status": "error",
                    "error": str(e),
                }
            )
        finally:
            await client.close()
    return {"results": results}


@app.get("/api/logs")
async def get_live_logs():
    return {"logs": list(log_buffer)}
