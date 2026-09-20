"""
Comprehensive automated tests for BotMentionReplierBot.
"""

import asyncio
from unittest.mock import AsyncMock, patch
import pytest
from config import BotConfig
from replier import MentionReplier
from telegram_client import TelegramClient


@pytest.fixture
def mock_config():
    cfg = BotConfig()
    cfg.bot_tokens = ["123456:TEST_TOKEN_1", "789012:TEST_TOKEN_2"]
    cfg.reply_mode = "both"
    cfg.parse_mode = "HTML"
    cfg.reply_templates = [
        "Hello <b>{first_name}</b>, welcome to {chat_title}! From {bot_name}."
    ]
    cfg.reply_delay = 0.0
    return cfg


@pytest.fixture
def mock_client():
    client = TelegramClient("123456:TEST_TOKEN_1")
    client.bot_info = {
        "id": 123456,
        "first_name": "ReplierBot",
        "username": "replier_bot",
        "supports_guest_queries": True,
    }
    client.answer_guest_query = AsyncMock(return_value={"ok": True, "result": True})
    client.send_message = AsyncMock(return_value={"ok": True, "result": True})
    return client


def test_template_formatting(mock_client, mock_config):
    replier = MentionReplier(mock_client, mock_config)
    caller_user = {
        "id": 999,
        "first_name": "Rahim",
        "last_name": "Uddin",
        "username": "rahim99",
    }
    caller_chat = {"id": -10012345, "title": "Developer Group"}

    text = replier.format_reply_text(caller_user, caller_chat)
    assert "Rahim" in text
    assert "Developer Group" in text
    assert "ReplierBot" in text
    assert "<b>" in text


@pytest.mark.asyncio
async def test_guest_message_handling(mock_client, mock_config):
    replier = MentionReplier(mock_client, mock_config)
    fake_guest_update = {
        "update_id": 1001,
        "guest_message": {
            "guest_query_id": "query_abc_123",
            "text": "@replier_bot hello test",
            "guest_bot_caller_user": {
                "id": 555,
                "first_name": "Karim",
                "username": "karim_tg",
            },
            "guest_bot_caller_chat": {"id": -1005555, "title": "Crypto Signals"},
        },
    }

    await replier.process_update(fake_guest_update)

    # Verify answer_guest_query was called
    mock_client.answer_guest_query.assert_called_once()
    call_args = mock_client.answer_guest_query.call_args[1]
    assert call_args["guest_query_id"] == "query_abc_123"
    assert "Karim" in call_args["text"]


@pytest.mark.asyncio
async def test_guest_message_deduplication(mock_client, mock_config):
    replier = MentionReplier(mock_client, mock_config)
    fake_guest_update = {
        "update_id": 1002,
        "guest_message": {
            "guest_query_id": "duplicate_query_999",
            "text": "@replier_bot test",
            "guest_bot_caller_user": {"first_name": "TestUser"},
            "guest_bot_caller_chat": {"title": "TestChat"},
        },
    }

    # First call
    await replier.process_update(fake_guest_update)
    assert mock_client.answer_guest_query.call_count == 1

    # Second identical call should be ignored by deduplication
    await replier.process_update(fake_guest_update)
    assert mock_client.answer_guest_query.call_count == 1


@pytest.mark.asyncio
async def test_member_mention_handling(mock_client, mock_config):
    replier = MentionReplier(mock_client, mock_config)
    fake_member_update = {
        "update_id": 2001,
        "message": {
            "message_id": 42,
            "chat": {"id": -100999, "title": "Community Chat"},
            "from": {"id": 888, "first_name": "Sakib"},
            "text": "Hey @replier_bot check this out!",
            "entities": [{"type": "mention", "offset": 4, "length": 12}],
        },
    }

    await replier.process_update(fake_member_update)

    # Verify send_message was called with quote reply
    mock_client.send_message.assert_called_once()
    call_args = mock_client.send_message.call_args[1]
    assert call_args["chat_id"] == -100999
    assert call_args["reply_to_message_id"] == 42
    assert "Sakib" in call_args["text"]


def test_config_validation():
    cfg = BotConfig()
    cfg.bot_tokens = []
    with pytest.raises(ValueError, match="No BOT_TOKENS found"):
        cfg.validate()

    cfg.bot_tokens = ["dummy_token"]
    cfg.reply_mode = "invalid_mode"
    with pytest.raises(ValueError, match="Invalid REPLY_MODE"):
        cfg.validate()
