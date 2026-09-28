"""
Tracked start links: every "@rizqshopbot" in a reply becomes a hidden link
that tells the shop where the customer came from.

    <a href="https://t.me/rizqshopbot?start=mn-...">@rizqshopbot</a>

The reader only sees @rizqshopbot. Everything travels inside the start
parameter (Telegram: max 64 characters of A-Z a-z 0-9 _ -), so there is no
server and no key between the two bots. The shop decodes it in
RizqShopBot/backend/src/services/mentionSource/payload.js — keep both in step:

    mn-<kind>-<place>-<msg>-<caller>-<time>[-<dplace>-<dmsg>]

    kind   c = comment under a channel post   place = the CHANNEL, msg = its post
                                               dplace/dmsg = discussion group + comment
           g = group message                  msg = the mention
           p = private chat                   msg = the mention
           x = anything else (inline query)
    place  public username (no @), or "0" + base36(|chat id|)
    msg / caller / time   base36, "0" = unknown; time = unix seconds

Fields are dropped from the END when the link would pass 64 characters, so
the place and the post always survive.
"""

import html
import os
import re
from typing import Any, Dict, List, Optional

MAX_START_PARAM = 64
TARGET_BOT = os.getenv("TRACK_BOT_USERNAME", "rizqshopbot").lstrip("@").strip()
_USERNAME = re.compile(r"^[A-Za-z][A-Za-z0-9_]{3,31}$")
_DIGITS = "0123456789abcdefghijklmnopqrstuvwxyz"


def b36(value: Any) -> str:
    try:
        n = abs(int(value))
    except (TypeError, ValueError):
        return "0"
    if n == 0:
        return "0"
    out = ""
    while n:
        n, r = divmod(n, 36)
        out = _DIGITS[r] + out
    return out


def place_of(chat: Optional[Dict[str, Any]]) -> str:
    """A public username when there is one, else '0' + base36 of the id."""
    if not isinstance(chat, dict):
        return "0"
    username = chat.get("username")
    if username and _USERNAME.match(username):
        return username
    return "0" + b36(chat.get("id")) if chat.get("id") else "0"


def build_start_payload(msg: Optional[Dict[str, Any]], caller: Optional[Dict[str, Any]] = None) -> str:
    """The start parameter for one mention (guest or member message, or none)."""
    msg = msg or {}
    chat = msg.get("chat") or {}
    reply = msg.get("reply_to_message") or {}
    origin = reply.get("forward_origin") or {}
    caller_id = (caller or {}).get("id") or (msg.get("from") or {}).get("id")
    when = msg.get("date")

    if reply.get("is_automatic_forward") and origin.get("type") == "channel":
        # A comment under a channel post: the CHANNEL and its post are what matter.
        fields = ["c", place_of(origin.get("chat")), b36(origin.get("message_id")), b36(caller_id), b36(when),
                  place_of(chat), b36(msg.get("message_id"))]
    elif chat.get("type") in ("group", "supergroup"):
        fields = ["g", place_of(chat), b36(msg.get("message_id")), b36(caller_id), b36(when)]
    elif chat.get("type") == "private":
        fields = ["p", place_of(chat), b36(msg.get("message_id")), b36(caller_id), b36(when)]
    else:
        fields = ["x", place_of(chat), b36(msg.get("message_id")), b36(caller_id), b36(when)]

    payload = "mn-" + "-".join(fields)
    while len(payload) > MAX_START_PARAM and len(fields) > 3:
        fields.pop()
        payload = "mn-" + "-".join(fields)
    return payload[:MAX_START_PARAM]


def start_url(payload: str, bot: str = TARGET_BOT) -> str:
    return f"https://t.me/{bot}?start={payload}"


def link_html(payload: str, bot: str = TARGET_BOT) -> str:
    return f'<a href="{html.escape(start_url(payload, bot), quote=True)}">@{bot}</a>'


def linkify(text: str, payload: str, bot: str = TARGET_BOT) -> str:
    """
    Turn every plain "@<bot>" into the tracked link. Text already inside an
    <a>…</a> is left alone (no nested links), and "@<bot>x" / "x@<bot>" are
    not matched — only the whole username.
    """
    if not bot or not text:
        return text
    mention = re.compile(rf"(?<![\w@/]){re.escape('@' + bot)}(?!\w)", re.IGNORECASE)
    parts: List[str] = re.split(r"(<a\b[^>]*>.*?</a>)", text, flags=re.IGNORECASE | re.DOTALL)
    for i, part in enumerate(parts):
        if i % 2 == 0:
            parts[i] = mention.sub(lambda _m: link_html(payload, bot), part)
    return "".join(parts)
