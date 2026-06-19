import logging
import requests
from decouple import config

logger = logging.getLogger(__name__)


def notify_telegram(message: str):
    """
    Sends a message to the founder's Telegram via bot.
    Fails silently (just logs) if not configured or unreachable —
    never let a notification failure break the payout run.
    """
    token = config("TELEGRAM_BOT_TOKEN", default=None)
    chat_id = config("TELEGRAM_CHAT_ID", default=None)

    if not token or not chat_id:
        logger.warning("Telegram not configured — TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID missing.")
        return

    try:
        requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": message, "parse_mode": "HTML"},
            timeout=10,
        )
    except requests.RequestException as exc:
        logger.error("Telegram notify failed: %s", exc)
