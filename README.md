# qrb-bot ✈️🇯🇵

A Telegram bot that watches a group for the **qrb** sticker (the cat-on-a-plane
"想去日本了" sticker) and counts how many times each user sends it. Run
`/qrbstat` to see today's leaderboard for the chat.

The "想去日本了" sticker appears in these sticker sets:

- https://t.me/addstickers/qrb_by_fStikBot
- https://t.me/addstickers/line338316218469_by_gene_moe_sticker_bot

## How matching works

Every Telegram file has a stable, globally-unique `file_unique_id`. The bot
counts a sticker when its id is in the allowlist (`QRB_FILE_UNIQUE_IDS`). This is
exact and instant — no image download or decoding, and no false positives. The
known qrb sticker ids are the default, so it works out of the box.

To add another sticker, run with `QRB_DEBUG=1`, send the sticker in any chat, and
the bot replies with its `file_unique_id` — add it to `QRB_FILE_UNIQUE_IDS`.

## Setup

### 1. Create the bot and get a token

1. In Telegram, talk to [@BotFather](https://t.me/BotFather).
2. Send `/newbot` and follow the prompts. Copy the token it gives you.
3. **Important:** send `/setprivacy` → pick your bot → **Disable**. Without this,
   group privacy mode hides normal messages (including stickers) from the bot and
   counting won't work.

### 2. Install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Configure

```bash
cp .env.example .env
# edit .env and paste your token into TELEGRAM_BOT_TOKEN
```

### 4. Run

```bash
python bot.py
```

Then add the bot to your group. It starts counting qrb stickers immediately.

## Commands

- `/qrbstat` — show today's per-user qrb count for the current chat.
- `/start` — short help message.

## Configuration (environment variables / `.env`)

| Variable               | Default          | Description                                          |
| ---------------------- | ---------------- | ---------------------------------------------------- |
| `TELEGRAM_BOT_TOKEN`   | _(req'd)_        | Token from @BotFather.                               |
| `QRB_FILE_UNIQUE_IDS`  | known qrb ids    | Comma-separated sticker ids to count.               |
| `QRB_DB`               | `qrb.db`         | SQLite database file path.                           |
| `QRB_TZ`               | system tz        | Timezone for "today", e.g. `Asia/Shanghai`.        |
| `QRB_DEBUG`            | _(off)_          | `1` to dump incoming stickers instead of counting.  |

## Data

Each detected sticker is stored as a row in the `qrb_events` table
(`chat_id`, `user_id`, `username`, `ts`). `/qrbstat` aggregates rows whose
timestamp falls within the current local calendar day.
