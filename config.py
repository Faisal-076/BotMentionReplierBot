"""
Configuration loader and settings validation for BotMentionReplierBot.
"""

import os
from pathlib import Path
from typing import List
from dotenv import load_dotenv

# Load .env if present
env_path = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=env_path)


class BotConfig:
    def __init__(self):
        tokens_raw = os.getenv("BOT_TOKENS", "").strip()
        self.bot_tokens: List[str] = [t.strip() for t in tokens_raw.split(",") if t.strip()]

        self.reply_mode: str = os.getenv("REPLY_MODE", "both").lower().strip()
        self.parse_mode: str = os.getenv("PARSE_MODE", "HTML").strip()
        self.disable_web_page_preview: bool = (
            os.getenv("DISABLE_WEB_PAGE_PREVIEW", "false").lower() in ("true", "1", "yes")
        )
        self.reply_delay: float = float(os.getenv("REPLY_DELAY", "0.0"))

        templates_raw = os.getenv(
            "REPLY_TEMPLATES",
            "🔥 <b>Hello {first_name}</b>, thanks for mentioning me!|||"
            "✨ <b>Special alert for {first_name}</b>: Check our updates!",
        )
        self.reply_templates: List[str] = [
            tmpl.replace("\\n", "\n").strip()
            for tmpl in templates_raw.split("|||")
            if tmpl.strip()
        ]

        self.poll_timeout: int = int(os.getenv("POLL_TIMEOUT", "25"))
        self.webhook_host: str = os.getenv("WEBHOOK_HOST", "0.0.0.0")
        self.webhook_port: int = int(os.getenv("WEBHOOK_PORT", "8000"))
        self.webhook_url_base: str = os.getenv("WEBHOOK_URL_BASE", "").strip().rstrip("/")

    def validate(self) -> None:
        """Validates configuration parameters."""
        if not self.bot_tokens:
            raise ValueError(
                "No BOT_TOKENS found. Please define BOT_TOKENS in your .env file."
            )
        if self.reply_mode not in ("guest", "member", "both"):
            raise ValueError(
                f"Invalid REPLY_MODE: '{self.reply_mode}'. Allowed values: 'guest', 'member', 'both'."
            )
        if not self.reply_templates:
            raise ValueError(
                "No REPLY_TEMPLATES configured. Please provide at least one template."
            )


# Default global config instance
config = BotConfig()
