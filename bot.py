#!/usr/bin/env python3
"""
📱 GPLinks Monitor Bot — ADMIN LOGIN FLOW
- Admin ko /start pe Login button dikhata hai
- Admin web browser me login karta hai (OTP + 2FA)
- Login ke baad bot chat 8226002644 monitor karta hai
- Destination links copy karke admin(s) ko forward karta hai
"""

import asyncio, logging, os, re, time
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from telegram.constants import ParseMode

logging.basicConfig(format="%(asctime)s [%(levelname)s] %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "8397171996:AAFZFT0ruUh4Augc4M6J19W7d9qKG5sHAVA")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "8580876995"))
TARGET_CHAT_ID = int(os.environ.get("TARGET_CHAT_ID", "8226002644"))
API_ID = int(os.environ.get("TELEGRAM_API_ID", "35812449"))
API_HASH = os.environ.get("TELEGRAM_API_HASH", "099cfed535a5b2dcd8e43f157d30e3ce")

monitor_client = None
monitor_running = False
processed_links = set()
pending_links = {}

TELETHON_OK = False
try:
    from telethon import TelegramClient, events
    from telethon.sessions import StringSession
    TELETHON_OK = True
except ImportError:
    pass

GPLINKS_RE = re.compile(r"https?://(?:www\.)?gplinks?\.(?:co|com)/[a-zA-Z0-9]+(?:\?[^\s]*)?")
ANY_URL_RE = re.compile(r"https?://[^\s]+")

def is_dest(url):
    skip = ["gplinks.co","gplinks.com","gplink.co","gplink.com","skrresults.com","mrdrt.com","trustify.click","rostelshute.shop","banchibipack.com","loginbreton.com","generateed.pages.dev","t.me","telegram.me","web.telegram.org"]
    from urllib.parse import urlparse
    dom = urlparse(url).netloc.lower()
    return not any(dom == s or dom.endswith("."+s) for s in skip)

async def cmd_start(update, ctx):
    uid = update.effective_user.id
    if uid != ADMIN_ID:
        await update.message.reply_text("⛔ Private bot hai.")
        return
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔐 Login to Telegram", callback_data="login")],
        [InlineKeyboardButton("📊 Status", callback_data="status")],
        [InlineKeyboardButton("⏹️ Stop Monitor", callback_data="stop")],
    ])
    await update.message.reply_text(
        f"⚡ <b>GPLinks Forward Bot v3.0</b>\n\n"
        f"👤 Admin: <code>{ADMIN_ID}</code>\n"
        f"👀 Target: <code>{TARGET_CHAT_ID}</code>\n"
        f"📡 Monitor: {('🟢 Running' if monitor_running else '🔴 Stopped')}\n\n"
        "<b>Login karo phir session string bhejo!</b>",
        reply_markup=kb, parse_mode=ParseMode.HTML)

async def on_callback(update, ctx):
    global monitor_running
    cb = update.callback_query
    if cb.from_user.id != ADMIN_ID:
        await cb.answer("⛔", show_alert=True)
        return
    if cb.data == "login":
        await cb.answer()
        await cb.message.reply_text(
            "🔐 <b>Login Instructions:</b>\n\n"
            "1️⃣ Telegram Web pe login karo: <a href='https://web.telegram.org/k/'>Open Web</a>\n"
            "2️⃣ Phone: <code>+919564335498</code>\n"
            "3️⃣ OTP enter karo\n"
            "4️⃣ 2FA: <code>trdaerp1wer</code>\n\n"
            "Phir <b>session string bhejo</b> — bot auto-detect karega!",
            parse_mode=ParseMode.HTML, disable_web_page_preview=True)
    elif cb.data == "status":
        await cb.answer()
        await cb.message.reply_text(f"📊 Monitor: {('🟢' if monitor_running else '🔴')}\n🔗 Processed: {len(processed_links)}", parse_mode=ParseMode.HTML)
    elif cb.data == "stop":
        monitor_running = False
        await cb.answer("Stopped!")
        await cb.message.reply_text("⏹️ Stopped.", parse_mode=ParseMode.HTML)

async def start_monitor(session_str, update, ctx):
    global monitor_running, monitor_client
    from telethon import TelegramClient as TC, events
    from telethon.sessions import StringSession
    client = TC(StringSession(session_str), API_ID, API_HASH)
    await client.start()
    me = await client.get_me()
    await update.message.reply_text(f"✅ Logged in: {me.first_name}\n👀 Monitoring chat {TARGET_CHAT_ID}...", parse_mode=ParseMode.HTML)
    monitor_client = client
    monitor_running = True

    @client.on(events.NewMessage(chats=[TARGET_CHAT_ID]))
    async def h(event):
        if not monitor_running: return
        text = event.message.text or ""
        if not text.strip(): return
        gplinks = GPLINKS_RE.findall(text)
        all_urls = ANY_URL_RE.findall(text)
        for gl in gplinks:
            if gl not in processed_links and gl not in pending_links:
                pending_links[gl] = time.time()
                logger.info(f"🔗 {gl[:60]}")
        for url in all_urls:
            if "gplinks" in url.lower(): continue
            if is_dest(url):
                for gl, t in list(pending_links.items()):
                    if gl not in processed_links and time.time() - t < 120:
                        processed_links.add(gl)
                        del pending_links[gl]
                        msg = f"🔗 <b>Source:</b> <code>{gl}</code>\n🎯 <b>Dest:</b> <code>{url}</code>\n<a href='{url}'>Open</a>"
                        try: await client.send_message(ADMIN_ID, msg, parse_mode="html", link_preview=False)
                        except: pass
                        try: await ctx.bot.send_message(ADMIN_ID, msg, parse_mode=ParseMode.HTML, disable_web_page_preview=False)
                        except: pass
        for gl, t in list(pending_links.items()):
            if time.time() - t > 300: del pending_links[gl]

    while monitor_running:
        await asyncio.sleep(1)

async def on_text(update, ctx):
    if update.effective_user.id != ADMIN_ID: return
    text = update.message.text.strip()
    if len(text) > 100 and not text.startswith("/"):
        await update.message.reply_text("🔐 Connecting...", parse_mode=ParseMode.HTML)
        try:
            await start_monitor(text, update, ctx)
        except Exception as e:
            await update.message.reply_text(f"❌ {str(e)[:300]}", parse_mode=ParseMode.HTML)
        return
    gplinks = GPLINKS_RE.findall(text)
    if gplinks:
        await update.message.reply_text(f"🔗 GPLinks mila! Monitor: {('🟢 ON' if monitor_running else '🔴 OFF')}\nLogin: /start", parse_mode=ParseMode.HTML)

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CallbackQueryHandler(on_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    logger.info("🤖 Bot v3.0 starting...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
