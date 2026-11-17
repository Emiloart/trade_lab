"""Telegram delivery that never leaks the bot token."""

from __future__ import annotations

import json
import urllib.error
import urllib.request


class NotifyError(RuntimeError):
    """Raised when an alert could not be delivered."""


def send_telegram(token: str, chat_id: str, text: str, timeout: float = 10.0) -> None:
    """Send a plain-text message.

    Errors are re-raised without the original exception chained, because the
    request URL (which contains the bot token) appears in urllib's messages.
    """
    if not token or not chat_id:
        raise NotifyError("BOT_TOKEN and CHAT_ID must both be set")

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = json.dumps(
        {"chat_id": chat_id, "text": text, "disable_web_page_preview": True}
    ).encode("utf-8")
    request = urllib.request.Request(
        url, data=payload, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = json.load(response)
    except urllib.error.HTTPError as exc:
        raise NotifyError(f"Telegram returned HTTP {exc.code}") from None
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        raise NotifyError(f"Telegram request failed: {type(exc).__name__}") from None

    if not body.get("ok"):
        raise NotifyError("Telegram rejected the message")
