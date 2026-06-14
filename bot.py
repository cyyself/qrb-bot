"""qrb-bot — a Telegram bot that counts the "qrb" sticker per user, per day.

It watches every sticker posted in a group. When a sticker's ``file_unique_id``
is in the configured allowlist, it records the event in a SQLite database. Users
can run /qrbstat to see today's per-user qrb counts for the current chat.

Matching strategy
-----------------
Telegram gives every file a stable, globally-unique ``file_unique_id``. We simply
check each incoming sticker's id against an allowlist (QRB_FILE_UNIQUE_IDS). This
is exact and instant — no image download or decoding, and no false positives.
To discover the id of a sticker, run with QRB_DEBUG=1 and send it in a chat.
"""

import json
import logging
import os
import sqlite3
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #
load_dotenv()

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
DB_PATH = os.environ.get("QRB_DB", "qrb.db")
# Comma-separated list of sticker file_unique_ids to count as qrb. Defaults to
# the known qrb stickers; override via the env var.
DEFAULT_FILE_UNIQUE_IDS = "AgADFSQAAnB-YVQ,AgAD-yIAAhnG6FQ"
QRB_FILE_UNIQUE_IDS = {
    s.strip()
    for s in os.environ.get("QRB_FILE_UNIQUE_IDS", DEFAULT_FILE_UNIQUE_IDS).split(",")
    if s.strip()
}
# Timezone used to decide what "today" means. Defaults to the system timezone.
TZ = ZoneInfo(os.environ["QRB_TZ"]) if os.environ.get("QRB_TZ") else None
# When set (QRB_DEBUG=1), dump every incoming sticker's full payload so you can
# read its file_unique_id (and other fields) and add it to the allowlist.
DEBUG = os.environ.get("QRB_DEBUG", "").lower() in ("1", "true", "yes")

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("qrb-bot")


# --------------------------------------------------------------------------- #
# Database
# --------------------------------------------------------------------------- #
def init_db() -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS qrb_events (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id   INTEGER NOT NULL,
                user_id   INTEGER NOT NULL,
                username  TEXT,
                ts        INTEGER NOT NULL
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_chat_ts ON qrb_events (chat_id, ts)"
        )


def record_event(chat_id: int, user_id: int, username: str, ts: int) -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT INTO qrb_events (chat_id, user_id, username, ts) "
            "VALUES (?, ?, ?, ?)",
            (chat_id, user_id, username, ts),
        )


def today_bounds(now: datetime) -> tuple[int, int]:
    """Return (start_ts, end_ts) unix seconds spanning the local calendar day."""
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    return int(start.timestamp()), int(end.timestamp())


def today_counts(chat_id: int) -> list[tuple[str, int]]:
    """Return [(username, count), ...] for today, highest first."""
    now = datetime.now(TZ)
    start_ts, end_ts = today_bounds(now)
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(
            """
            SELECT user_id,
                   MAX(username) AS username,
                   COUNT(*)      AS cnt
            FROM qrb_events
            WHERE chat_id = ? AND ts >= ? AND ts < ?
            GROUP BY user_id
            ORDER BY cnt DESC
            """,
            (chat_id, start_ts, end_ts),
        ).fetchall()
    return [(username or f"user {user_id}", cnt) for user_id, username, cnt in rows]


# --------------------------------------------------------------------------- #
# Telegram handlers
# --------------------------------------------------------------------------- #
def display_name(update: Update) -> str:
    user = update.effective_user
    if user is None:
        return "unknown"
    if user.username:
        return f"@{user.username}"
    return user.full_name or f"user {user.id}"


async def dump_sticker(update: Update) -> None:
    """Log the full message + reply with the key sticker fields (debug mode)."""
    message = update.effective_message
    sticker = message.sticker

    # Full raw payload to the server log, for the complete picture.
    logger.info(
        "RAW MESSAGE:\n%s", json.dumps(message.to_dict(), indent=2, ensure_ascii=False)
    )

    fields = {
        "set_name": sticker.set_name,
        "emoji": sticker.emoji,
        "file_unique_id": sticker.file_unique_id,
        "file_id": sticker.file_id,
        "type": sticker.type,
        "is_animated": sticker.is_animated,
        "is_video": sticker.is_video,
        "width": sticker.width,
        "height": sticker.height,
        "in_allowlist": sticker.file_unique_id in QRB_FILE_UNIQUE_IDS,
    }
    lines = ["🔍 sticker debug:"]
    lines += [f"{k}: {v}" for k, v in fields.items()]
    await message.reply_text("\n".join(lines))


async def handle_sticker(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    sticker = message.sticker if message else None
    if sticker is None:
        return

    # In debug mode, dump every sticker's fields and stop (no counting).
    if DEBUG:
        await dump_sticker(update)
        return

    # Count only stickers whose file_unique_id is in the allowlist.
    if sticker.file_unique_id not in QRB_FILE_UNIQUE_IDS:
        return

    record_event(
        chat_id=update.effective_chat.id,
        user_id=update.effective_user.id,
        username=display_name(update),
        ts=int(time.time()),
    )


async def qrbstat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    counts = today_counts(chat.id)
    if not counts:
        await update.effective_message.reply_text("No qrb stickers counted today ✈️🇯🇵")
        return

    lines = ["✈️🇯🇵 count today:"]
    for rank, (username, cnt) in enumerate(counts, start=1):
        lines.append(f"{rank}. {username} — {cnt}")
    await update.effective_message.reply_text("\n".join(lines))


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text(
        "Hi! Add me to a group and I'll count every qrb sticker.\n"
        "Use /qrbstat to see today's leaderboard."
    )


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #
def main() -> None:
    if not BOT_TOKEN:
        raise SystemExit(
            "TELEGRAM_BOT_TOKEN is not set. Get a token from @BotFather and put "
            "it in a .env file or export it as an environment variable."
        )

    init_db()

    if DEBUG:
        logger.info("DEBUG mode: dumping stickers, not counting.")
    elif QRB_FILE_UNIQUE_IDS:
        logger.info("Matching %d sticker id(s).", len(QRB_FILE_UNIQUE_IDS))
    else:
        logger.warning("QRB_FILE_UNIQUE_IDS is empty — nothing will be counted.")

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("qrbstat", qrbstat))
    app.add_handler(MessageHandler(filters.Sticker.ALL, handle_sticker))

    logger.info("qrb-bot starting…")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
