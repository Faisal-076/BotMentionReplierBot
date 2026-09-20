"""
FastAPI Dashboard Server providing Web UI control center and real-time bot management.
"""

import asyncio
from collections import deque
from datetime import datetime, timezone
import logging
import os
import hashlib
from pathlib import Path
from typing import Any, Dict, List, Optional
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
try:
    import orjson
    from fastapi.responses import ORJSONResponse
    DEFAULT_RESP_CLASS = ORJSONResponse
except ImportError:
    orjson = None
    DEFAULT_RESP_CLASS = JSONResponse

from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from cluster import BotCluster
from config import BotConfig, config
from replier import MentionReplier
from telegram_client import TelegramClient

BASE_DIR = Path(__file__).parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"

app = FastAPI(
    title="Telegram Bot Mention Replier Control Center",
    default_response_class=DEFAULT_RESP_CLASS,
)

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
        self.mode: str = "webhook"  # "webhook" or "polling"
        self.webhook_clients: Dict[str, TelegramClient] = {}
        self.webhook_repliers: Dict[str, Any] = {}


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
    """Starts the bot cluster in Webhook (Zero-Lag) or Polling mode."""
    if state.is_running:
        return
    try:
        config.validate()
    except Exception as e:
        logger.error(f"Cannot start cluster: {e}")
        return

    self_url = (
        os.environ.get("SELF_URL")
        or os.environ.get("RENDER_EXTERNAL_URL")
        or os.environ.get("KOYEB_PUBLIC_URL")
        or ""
    ).strip().rstrip("/")
    if self_url and not self_url.startswith("http"):
        self_url = f"https://{self_url}"

    configured_mode = os.environ.get(
        "UPDATE_MODE", "webhook" if self_url else "polling"
    ).lower()

    if configured_mode == "webhook" and self_url:
        state.mode = "webhook"
        state.is_running = True
        state.start_time = datetime.now(timezone.utc)
        logger.info(f"⚡ Starting Supersonic Webhook Engine on {self_url}...")

        state.webhook_clients.clear()
        state.webhook_repliers.clear()

        for token in config.bot_tokens:
            token_hash = hashlib.sha256(token.encode()).hexdigest()[:16]
            client = TelegramClient(token)
            me = await client.get_me()
            if me.get("ok"):
                username = me["result"].get("username", "Unknown")
                guest_supported = me["result"].get("supports_guest_queries", False)
                replier = MentionReplier(client, config)
                state.webhook_clients[token_hash] = client
                state.webhook_repliers[token_hash] = (
                    replier,
                    username,
                    guest_supported,
                )

                webhook_url = f"{self_url}/webhook/{token_hash}"
                res = await client.set_webhook(
                    url=webhook_url,
                    allowed_updates=[
                        "guest_message",
                        "message",
                        "edited_message",
                        "inline_query",
                    ],
                    drop_pending_updates=False,
                )
                if res.get("ok"):
                    logger.info(
                        f"🚀 [@{username}] Webhook active -> {webhook_url} (Guest Mode: {guest_supported})"
                    )
                else:
                    logger.error(
                        f"❌ Failed to set webhook for @{username}: {res.get('description')}"
                    )
        logger.info(
            f"⚡ Supersonic Webhook Cluster started with {len(state.webhook_repliers)} bot(s)."
        )
    else:
        state.mode = "polling"
        state.cluster = BotCluster(config)
        state.is_running = True
        state.start_time = datetime.now(timezone.utc)
        state.task = asyncio.create_task(state.cluster.start())
        logger.info("Bot Cluster started in Long Polling mode.")


async def stop_cluster_internal():
    """Stops the running bot cluster and clears webhooks if in webhook mode."""
    if not state.is_running:
        return
    state.is_running = False
    if state.mode == "webhook":
        for client in state.webhook_clients.values():
            try:
                await client.delete_webhook(drop_pending_updates=False)
                await client.close()
            except Exception:
                pass
        state.webhook_clients.clear()
        state.webhook_repliers.clear()
        logger.info("Webhook Bot Cluster stopped and webhooks cleared.")
    else:
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


async def anti_sleep_keepalive_worker():
    """
    Maximum-reliability Anti-Sleep Engine.
    Dispatches lightweight asynchronous keepalive pings every 90 seconds (1.5 mins)
    to the public cloud domain (Render / Northflank), preventing sleep mode (scale-to-zero)
    and eliminating cold-start latency.
    """
    import aiohttp

    await asyncio.sleep(10)  # Short initial wait for uvicorn to bind
    self_url = (
        os.environ.get("SELF_URL")
        or os.environ.get("RENDER_EXTERNAL_URL")
        or os.environ.get("KOYEB_PUBLIC_URL")
        or ""
    ).strip().rstrip("/")

    if not self_url:
        logger.info(
            "ℹ️ Anti-Sleep Engine: SELF_URL / RENDER_EXTERNAL_URL not set. Running in local/standby mode."
        )
        return

    if not self_url.startswith("http"):
        self_url = f"https://{self_url}"
    health_url = f"{self_url}/health"

    logger.info(f"🛡️ Anti-Sleep Ultra Engine ACTIVATED! Auto-pinging {health_url} every 90s.")

    ping_count = 0
    connector = aiohttp.TCPConnector(limit=5, keepalive_timeout=30)
    async with aiohttp.ClientSession(
        connector=connector,
        timeout=aiohttp.ClientTimeout(total=10),
        headers={"User-Agent": "UltraAntiSleep/2.0-KeepAlive"},
    ) as session:
        while True:
            try:
                await asyncio.sleep(90)  # Ping every 90s - completely defeats 15-min or 5-min idle timeouts
                ping_count += 1
                async with session.get(health_url) as resp:
                    if resp.status == 200:
                        if ping_count % 10 == 0:  # Log every 15 minutes to avoid cluttering logs
                            logger.info(
                                f"🛡️ Anti-Sleep Heartbeat: #{ping_count} successful keepalive pings. Host is hot and awake!"
                            )
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.debug(f"Anti-sleep keepalive ping note: {e}")


@app.on_event("startup")
async def app_startup():
    auto_start = os.environ.get("AUTO_START_CLUSTER", "true").lower() in (
        "true",
        "1",
        "yes",
    )
    # Auto-start bot cluster if tokens exist and not disabled
    if config.bot_tokens and auto_start:
        asyncio.create_task(start_cluster_internal())
    elif config.bot_tokens and not auto_start:
        logger.info(
            "Bot cluster auto-start is paused (AUTO_START_CLUSTER=false). Ready to start via Web UI."
        )

    # Launch background anti-sleep keepalive engine
    asyncio.create_task(anti_sleep_keepalive_worker())


@app.get("/", response_class=HTMLResponse)
async def serve_dashboard():
    index_file = TEMPLATES_DIR / "index.html"
    if not index_file.exists():
        return HTMLResponse("<h1>Dashboard loading... Please refresh in a moment.</h1>")
    return HTMLResponse(index_file.read_text(encoding="utf-8"))


@app.get("/health")
async def health_check():
    return {
        "status": "ok",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "is_running": state.is_running,
        "mode": state.mode,
    }


@app.post("/webhook/{token_hash}")
async def handle_incoming_telegram_webhook(token_hash: str, request: Request):
    """
    Sub-millisecond Webhook Ingestion Engine.
    Parses incoming Telegram update in C/Rust (orjson) and fires MentionReplier in zero-latency task.
    """
    if token_hash not in state.webhook_repliers:
        raise HTTPException(status_code=404, detail="Webhook endpoint not found")

    body = await request.body()
    try:
        update = orjson.loads(body) if orjson else json.loads(body.decode("utf-8"))
    except Exception:
        import json as py_json

        try:
            update = py_json.loads(body.decode("utf-8"))
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid JSON payload")

    replier, _, _ = state.webhook_repliers[token_hash]
    # Zero-delay concurrent execution
    asyncio.create_task(replier.process_update(update))
    return {"ok": True}


@app.get("/api/benchmark")
async def run_latency_benchmark():
    """
    Executes deep network and Telegram Bot API latency measurements
    directly from this cloud container to api.telegram.org.
    """
    import socket
    import ssl
    import time
    import statistics
    import aiohttp

    target_host = "api.telegram.org"
    target_port = 443

    # 1. DNS Resolution (5 iterations)
    dns_times = []
    resolved_ip = "unknown"
    for _ in range(5):
        t0 = time.perf_counter()
        try:
            addrs = socket.getaddrinfo(target_host, target_port)
            dns_times.append((time.perf_counter() - t0) * 1000)
            resolved_ip = addrs[0][4][0]
        except Exception:
            pass

    # 2. TCP Handshake to api.telegram.org (5 iterations)
    tcp_times = []
    for _ in range(5):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(3.0)
        t0 = time.perf_counter()
        try:
            s.connect((resolved_ip, target_port))
            tcp_times.append((time.perf_counter() - t0) * 1000)
        except Exception:
            pass
        finally:
            s.close()

    # 3. TLS Handshake (5 iterations)
    tls_times = []
    ssl_context = ssl.create_default_context()
    for _ in range(5):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(3.0)
        try:
            s.connect((resolved_ip, target_port))
            t0 = time.perf_counter()
            ss = ssl_context.wrap_socket(s, server_hostname=target_host)
            tls_times.append((time.perf_counter() - t0) * 1000)
            ss.close()
        except Exception:
            s.close()

    # 4. HTTPS Round Trip Time (Warm keepalive vs cold connection)
    http_times = []
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as session:
        for _ in range(5):
            t0 = time.perf_counter()
            try:
                async with session.get(f"https://{target_host}/") as resp:
                    await resp.read()
                http_times.append((time.perf_counter() - t0) * 1000)
            except Exception:
                pass

    # 5. Geolocation / IP details
    geo_info = {}
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=3)) as session:
            async with session.get("http://ip-api.com/json/") as resp:
                if resp.status == 200:
                    geo_info = await resp.json()
    except Exception:
        pass

    def calc_stats(arr):
        if not arr:
            return {"min_ms": 0, "avg_ms": 0, "max_ms": 0, "samples": []}
        return {
            "min_ms": round(min(arr), 2),
            "avg_ms": round(statistics.mean(arr), 2),
            "max_ms": round(max(arr), 2),
            "samples": [round(x, 2) for x in arr],
        }

    return {
        "target": target_host,
        "resolved_ip": resolved_ip,
        "server_env": {
            "platform": "Render" if os.environ.get("RENDER") else ("Northflank" if os.environ.get("PORT") and not os.environ.get("RENDER") else "Local/Cloud"),
            "country": geo_info.get("country", "Unknown"),
            "city": geo_info.get("city", "Unknown"),
            "isp": geo_info.get("isp", "Unknown"),
            "public_ip": geo_info.get("query", "Unknown"),
        },
        "dns_resolution": calc_stats(dns_times),
        "tcp_handshake": calc_stats(tcp_times),
        "tls_handshake": calc_stats(tls_times),
        "http_rtt_keepalive": calc_stats(http_times),
    }


@app.get("/api/status")
async def get_status():
    uptime = 0
    if state.is_running and state.start_time:
        uptime = int((datetime.now(timezone.utc) - state.start_time).total_seconds())

    runners_info = []
    if state.mode == "webhook":
        for replier, uname, guest_ok in state.webhook_repliers.values():
            runners_info.append(
                {
                    "username": uname,
                    "is_running": state.is_running,
                    "guest_supported": guest_ok,
                }
            )
    elif state.cluster and state.cluster.runners:
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
        "mode": state.mode,
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
