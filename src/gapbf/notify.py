"""Instant Telegram notification for a found pattern.

Stdlib only (urllib), mirrors scripts/health_ping.py's sender but is
NON-FATAL: if the bot token / chat id are absent, or the send fails, it logs
and returns instead of raising, so a notification problem can never lose a
hard-won successful decrypt.

Env (injected live by `infisical run`, same names as health_ping):
  TELEGRAM_RS_AUTOMATION_BOT_TOKEN  (or TELEGRAM_BOT_TOKEN)
  TELEGRAM_RS_AUTOMATION_CHAT_ID    (or TELEGRAM_CHAT_ID)
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request

logger = logging.getLogger(__name__)


def _creds() -> tuple[str, str]:
    token = os.environ.get("TELEGRAM_RS_AUTOMATION_BOT_TOKEN") or os.environ.get(
        "TELEGRAM_BOT_TOKEN", ""
    )
    chat_id = os.environ.get("TELEGRAM_RS_AUTOMATION_CHAT_ID") or os.environ.get(
        "TELEGRAM_CHAT_ID", ""
    )
    return token, chat_id


def notify(text: str) -> bool:
    """Send a Telegram message. Returns True on success, False otherwise.
    Never raises."""
    token, chat_id = _creds()
    if not token or not chat_id:
        logger.warning("Telegram creds not set; skipping notification: %s", text)
        return False
    data = json.dumps({"chat_id": chat_id, "text": text}).encode()
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=data,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            body = json.load(r)
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        logger.error("Telegram notification failed: %s", error)
        return False
    if not body.get("ok"):
        logger.error("Telegram notification rejected: %s", body)
        return False
    return True


def notify_success(pattern: list[str], device_id: str | None = None) -> None:
    joined = "".join(pattern)
    dev = f" on {device_id}" if device_id else ""
    notify(f"🎉 gapbf FOUND THE PATTERN{dev}: {joined}\nnodes: {pattern}")
