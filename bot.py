import os
import json
import time
import asyncio
import yt_dlp
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters
)
from telegram.request import HTTPXRequest

logging.basicConfig(level=logging.CRITICAL)

CONFIG_FILE = "config.json"
USERS_FILE = "users.json"
COOKIES_FILE = "cookies.txt"


if not os.path.exists(CONFIG_FILE):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump({
            "bot_token": "PUT_YOUR_NEW_TOKEN_HERE",
            "mandatory_channels": ["@DevZone_IT"],
            "max_file_size_gb": 1
        }, f, ensure_ascii=False, indent=2)

config = json.load(open(CONFIG_FILE, "r", encoding="utf-8"))

BOT_TOKEN = config["bot_token"]
MANDATORY_CHANNELS = config["mandatory_channels"]
MAX_FILE_SIZE = config["max_file_size_gb"] * 1024 * 1024 * 1024


def load_users():
    if not os.path.exists(USERS_FILE):
        return {}
    return json.load(open(USERS_FILE, "r", encoding="utf-8"))


def save_users(data):
    json.dump(data, open(USERS_FILE, "w", encoding="utf-8"), ensure_ascii=False, indent=2)


def ensure_user(user):
    data = load_users()
    uid = str(user.id)
    if uid not in data:
        data[uid] = {
            "username": user.username,
            "registered": time.strftime("%Y-%m-%d %H:%M:%S"),
            "downloads": 0
        }
        save_users(data)


async def check_subscriptions(user_id, bot):
    for channel in MANDATORY_CHANNELS:
        try:
            member = await bot.get_chat_member(channel, user_id)
            if member.status not in ("member", "administrator", "creator"):
                return False
        except:
            return False
    return True


def subscribe_keyboard():
    keyboard = []
    for ch in MANDATORY_CHANNELS:
        keyboard.append([
            InlineKeyboardButton(f"Подписаться {ch}", url=f"https://t.me/{ch.replace('@','')}")
        ])
    keyboard.append([InlineKeyboardButton("Проверить", callback_data="check_subscribe")])
    return InlineKeyboardMarkup(keyboard)


def download_media(url, filename):
    ydl_opts = {
        "format": "bestvideo[ext=mp4]/best[ext=mp4]/best",
        "outtmpl": filename,
        "cookiefile": COOKIES_FILE if os.path.exists(COOKIES_FILE) else None,
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "ignoreerrors": True,
        "max_filesize": MAX_FILE_SIZE,
        "concurrent_fragment_downloads": 8,
        "http_chunk_size": 10 * 1024 * 1024,
        "retries": 3,
        "fragment_retries": 3,
        "socket_timeout": 15,
        "js_runtimes": {"node": {}}
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            return ydl.extract_info(url, download=True)
    except:
        return None


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ensure_user(update.effective_user)
    if not await check_subscriptions(update.effective_user.id, context.bot):
        await update.message.reply_text(
            "Подпишись на канал, чтобы пользоваться ботом.",
            reply_markup=subscribe_keyboard()
        )
        return
    await update.message.reply_text("Отправь ссылку на видео или фото.")


async def check_subscribe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if await check_subscriptions(q.from_user.id, context.bot):
        await q.edit_message_text("Подписка подтверждена.")
    else:
        await q.edit_message_text("Ты не подписался.", reply_markup=subscribe_keyboard())


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()

    if not url.startswith("http"):
        await update.message.reply_text("Это не ссылка.")
        return

    if not await check_subscriptions(update.effective_user.id, context.bot):
        await update.message.reply_text(
            "Сначала подпишись.",
            reply_markup=subscribe_keyboard()
        )
        return

    await update.message.reply_text("Скачиваю...")

    base = f"media_{update.effective_user.id}_{int(time.time())}"
    filename = base + ".%(ext)s"

    loop = asyncio.get_running_loop()
    info = await loop.run_in_executor(None, lambda: download_media(url, filename))

    if not info or not info.get("ext"):
        await update.message.reply_text("Не удалось получить медиа.")
        return

    ext = info["ext"]
    file_path = f"{base}.{ext}"

    if not os.path.exists(file_path):
        await update.message.reply_text("Файл не найден.")
        return

    title = info.get("title", "Медиа")

    try:
        with open(file_path, "rb") as f:
            try:
                if ext.lower() in ["jpg", "jpeg", "png", "webp"]:
                    await update.message.reply_photo(photo=f, caption=title)
                else:
                    await update.message.reply_video(video=f, caption=title)
            except:
                f.seek(0)
                await update.message.reply_document(document=f, caption=title)
    except:
        pass
    finally:
        try:
            os.remove(file_path)
        except:
            pass

    users = load_users()
    uid = str(update.effective_user.id)
    users[uid]["downloads"] += 1
    save_users(users)


def main():
    request = HTTPXRequest(
        connect_timeout=60,
        read_timeout=120,
        write_timeout=300,
        pool_timeout=60
    )

    app = Application.builder().token(BOT_TOKEN).request(request).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(check_subscribe, pattern="check_subscribe"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.run_polling()


if __name__ == "__main__":
    main()
