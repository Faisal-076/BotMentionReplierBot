"""
Tracked start links (tracking.py). The samples are the real guest-mention
fields logged on 2026-09-27; RizqShop's test/mentionSource.test.js decodes
the same two payloads, so the pair pins the contract from both ends.
"""

from tracking import MAX_START_PARAM, b36, build_start_payload, linkify

COMMENT = {
    "message_id": 367,
    "date": 1790539989,
    "chat": {"id": -1003174323122, "type": "supergroup", "title": "Prompt Gemini | پرامپت جمینی chat"},
    "from": {"id": 6327694456},
    "reply_to_message": {
        "message_id": 331,
        "is_automatic_forward": True,
        "forward_origin": {"type": "channel", "chat": {"id": -1001259142350, "type": "channel", "username": "Sona_ads"}, "message_id": 696},
    },
}
GROUP = {
    "message_id": 565210,
    "date": 1790540160,
    "chat": {"id": -1001465330657, "type": "supergroup", "username": "MailSellBMgroups"},
    "from": {"id": 959814038},
}


def test_comment_names_the_channel_post_and_the_comment():
    p = build_start_payload(COMMENT)
    assert p == f"mn-c-Sona_ads-{b36(696)}-{b36(6327694456)}-{b36(1790539989)}-0{b36(1003174323122)}-{b36(367)}"
    assert len(p) <= MAX_START_PARAM


def test_group_and_private_and_unknown():
    assert build_start_payload(GROUP) == f"mn-g-MailSellBMgroups-{b36(565210)}-{b36(959814038)}-{b36(1790540160)}"
    private = {"message_id": 164735, "date": 1, "chat": {"id": 5946365015, "type": "private", "username": "Mahdib32"}, "from": {"id": 6738766733}}
    assert build_start_payload(private).startswith("mn-p-Mahdib32-")
    assert build_start_payload(None, {"id": 5}) == "mn-x-0-0-5-0"


def test_too_long_drops_from_the_end_never_the_place():
    msg = dict(COMMENT)
    msg["reply_to_message"] = dict(COMMENT["reply_to_message"])
    msg["reply_to_message"]["forward_origin"] = {"type": "channel", "chat": {"id": -1, "username": "A" * 32}, "message_id": 10**9}
    p = build_start_payload(msg)
    assert len(p) <= MAX_START_PARAM
    assert p.startswith("mn-c-" + "A" * 32 + "-" + b36(10**9))


def test_linkify_hides_the_payload_behind_the_username():
    out = linkify("<h1>🤖 Order in @rizqshopbot</h1><h1>@RizqShopBot again</h1>", "mn-g-x-1-2-3")
    assert out.count('href="https://t.me/rizqshopbot?start=mn-g-x-1-2-3">@rizqshopbot</a>') == 2
    # left alone: an existing link, a longer username, an email-like string
    kept = '<a href="https://t.me/rizqshopbot">@rizqshopbot</a> @rizqshopbot_bot me@rizqshopbot'
    assert linkify(kept, "p") == kept
