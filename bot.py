#!/usr/bin/env python3
"""
📱 GPLinks Monitor Bot v3.1 — INTERACTIVE LOGIN
- Admin /start kare → Login button dikhe
- Bot step-by-step puchega: Phone → OTP → 2FA (if needed)
- Login ke baad chat 8226002644 monitor karega
- Destination links admin ko forward karega
"""

import asyncio, logging, os, re, time
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ConversationHandler, filters, ContextTypes
)
from telegram.constants import ParseMode

logging.basicConfig(format="%(asctime)s [%(levelname)s] %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "8397171996:AAFZFT0ruUh4Augc4M6J19W7d9qKG5sHAVA")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "8580876995"))
TARGET_CHAT_ID = int(os.environ.get("TARGET_CHAT_ID", "8226002644"))
API_ID = int(os.environ.get("TELEGRAM_API_ID", "35812449"))
API_HASH = os.environ.get("TELEGRAM_API_HASH", "099cfed535a5b2dcd8e43f157d30e3ce")

PHONE, OTP, PASSWORD = range(3)

monitor_client = None
monitor_running = False
processed_links = set()
pending_links = {}
login_data = {}

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
    skip = ["gplinks.co","gplinks.com","gplink.co","gplink.com","skrresults.com","mrdrt.com",
            "trustify.click","rostelshute.shop","banchibipack.com","loginbreton.com",
            "generateed.pages.dev","t.me","telegram.me","web.telegram.org"]
    from urllib.parse import urlparse
    dom = urlparse(url).netloc.lower()
    return not any(dom == s or dom.endswith("."+s) for s in skip)


# ════════════════════════════════════════════
#  LOGIN CONVERSATION (Step by Step)
# ════════════════════════════════════════════

async def start_login(update, ctx):
    """Step 1: Ask for phone number"""
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ Private bot.")
        return ConversationHandler.END
    
    await update.message.reply_text(
        "🔐 <b>Telegram Login</b>\n\n"
        "📱 <b>Step 1/3:</b> Apna phone number bhejo\n"
        "Format: <code>+919564335498</code>\n\n"
        "<i>/cancel to abort</i>",
        parse_mode=ParseMode.HTML
    )
    return PHONE


async def got_phone(update, ctx):
    """Step 2: Got phone → send OTP"""
    phone = update.message.text.strip()
    if not phone.startswith("+"):
        phone = "+" + phone
    
    login_data["phone"] = phone
    
    try:
        from telethon import TelegramClient
        from telethon.sessions import StringSession
        client = TelegramClient(StringSession(), API_ID, API_HASH)
        await client.connect()
        sent = await client.send_code_request(phone)
        login_data["client"] = client
        login_data["phone_code_hash"] = sent.phone_code_hash
        
        await update.message.reply_text(
            f"📲 <b>OTP sent to {phone}!</b>\n\n"
            f"📝 <b>Step 2/3:</b> OTP code bhejo\n\n"
            f"<i>/cancel to abort</i>",
            parse_mode=ParseMode.HTML
        )
        return OTP
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)[:200]}\n\nTry again: /login")
        return ConversationHandler.END


async def got_otp(update, ctx):
    """Step 3: Got OTP → sign in or ask 2FA"""
    code = update.message.text.strip()
    client = login_data.get("client")
    phone = login_data.get("phone", "")
    phone_code_hash = login_data.get("phone_code_hash", "")
    
    try:
        me = await client.sign_in(phone, code, phone_code_hash=phone_code_hash)
        session_str = client.session.save()
        await client.disconnect()
        
        await update.message.reply_text(
            f"✅ <b>Logged in as:</b> {me.first_name} (@{me.username or 'N/A'})\n\n"
            f"🟢 Starting monitor on <code>{TARGET_CHAT_ID}</code>...",
            parse_mode=ParseMode.HTML
        )
        
        asyncio.create_task(start_monitor_with_session(session_str, update, ctx))
        return ConversationHandler.END
        
    except Exception as e:
        err = str(e)
        if "password" in err.lower() or "2fa" in err.lower():
            await update.message.reply_text(
                "🔒 <b>2FA Protected!</b>\n\n"
                "🔑 <b>Step 3/3:</b> 2FA password bhejo\n\n"
                "<i>/cancel to abort</i>",
                parse_mode=ParseMode.HTML
            )
            return PASSWORD
        elif "invalid" in err.lower() or "expired" in err.lower():
            await update.message.reply_text(f"❌ OTP invalid/expired!\nTry again: /login")
            await client.disconnect()
            return ConversationHandler.END
        else:
            await update.message.reply_text(f"❌ Error: {err[:200]}\nTry again: /login")
            await client.disconnect()
            return ConversationHandler.END


async def got_password(update, ctx):
    """Step 4: Got 2FA → final sign in"""
    pwd = update.message.text.strip()
    client = login_data.get("client")
    
    try:
        me = await client.sign_in(password=pwd)
        session_str = client.session.save()
        await client.disconnect()
        
        await update.message.reply_text(
            f"✅ <b>Logged in!</b> {me.first_name} (@{me.username or 'N/A'})\n\n"
            f"🟢 Starting monitor on <code>{TARGET_CHAT_ID}</code>...",
            parse_mode=ParseMode.HTML
        )
        
        asyncio.create_task(start_monitor_with_session(session_str, update, ctx))
        return ConversationHandler.END
        
    except Exception as e:
        await update.message.reply_text(f"❌ Login failed: {str(e)[:200]}\nTry again: /login")
        await client.disconnect()
        return ConversationHandler.END


async def cancel_login(update, ctx):
    client = login_data.pop("client", None)
    if client:
        await client.disconnect()
    login_data.clear()
    await update.message.reply_text("🚫 Login cancelled. /login to retry.")
    return ConversationHandler.END


# ════════════════════════════════════════════
#  MONITORING
# ════════════════════════════════════════════

async def start_monitor_with_session(session_str, update, ctx):
    global monitor_running, monitor_client
    from telethon import TelegramClient as TC, events
    from telethon.sessions import StringSession
    
    client = TC(StringSession(session_str), API_ID, API_HASH)
    await client.start()
    
    monitor_client = client
    monitor_running = True
    
    logger.info(f"👀 Monitoring chat {TARGET_CHAT_ID}...")
    
    @client.on(events.NewMessage(chats=[TARGET_CHAT_ID]))
    async def handler(event):
        if not monitor_running:
            return
        text = event.message.text or ""
        if not text.strip():
            return
        
        gplinks = GPLINKS_RE.findall(text)
        all_urls = ANY_URL_RE.findall(text)
        
        for gl in gplinks:
            if gl not in processed_links and gl not in pending_links:
                pending_links[gl] = time.time()
                logger.info(f"🔗 New: {gl[:60]}")
                try:
                    await ctx.bot.send_message(ADMIN_ID, f"🔗 <b>New link found!</b>\n<code>{gl}</code>\n⏳ Waiting for destination...", parse_mode=ParseMode.HTML)
                except: pass
        
        for url in all_urls:
            if "gplinks" in url.lower():
                continue
            if is_dest(url):
                for gl, t in list(pending_links.items()):
                    if gl not in processed_links and time.time() - t < 120:
                        processed_links.add(gl)
                        del pending_links[gl]
                        msg = f"✅ <b>Destination!</b>\n🔗 <b>Source:</b> <code>{gl}</code>\n🎯 <b>Dest:</b> <code>{url}</code>\n<a href='{url}'>Open →</a>"
                        try:
                            await ctx.bot.send_message(ADMIN_ID, msg, parse_mode=ParseMode.HTML, disable_web_page_preview=False)
                        except: pass
        
        for gl, t in list(pending_links.items()):
            if time.time() - t > 300:
                del pending_links[gl]
    
    while monitor_running:
        await asyncio.sleep(1)


# ════════════════════════════════════════════
#  SIMPLE COMMANDS
# ════════════════════════════════════════════

async def cmd_start(update, ctx):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ Private bot.")
        return
    
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔐 Login", callback_data="start_login")],
        [InlineKeyboardButton("📊 Status", callback_data="status")],
        [InlineKeyboardButton("⏹️ Stop", callback_data="stop")],
    ])
    
    await update.message.reply_text(
        f"⚡ <b>GPLinks Forward Bot v3.1</b>\n\n"
        f"👤 Admin: <code>{ADMIN_ID}</code>\n"
        f"👀 Target: <code>{TARGET_CHAT_ID}</code>\n"
        f"📡 Monitor: {'🟢 ON' if monitor_running else '🔴 OFF'}\n"
        f"🔗 Processed: <b>{len(processed_links)}</b>\n\n"
        "<b>Login karo → monitoring automatic!</b>",
        reply_markup=kb, parse_mode=ParseMode.HTML
    )


async def cmd_status(update, ctx):
    if update.effective_user.id != ADMIN_ID:
        return
    await update.message.reply_text(
        f"📊 <b>Status</b>\n📡 Monitor: {'🟢' if monitor_running else '🔴'}\n"
        f"🔗 Processed: {len(processed_links)}\n⏳ Pending: {len(pending_links)}",
        parse_mode=ParseMode.HTML
    )


async def on_callback(update, ctx):
    global monitor_running
    cb = update.callback_query
    if cb.from_user.id != ADMIN_ID:
        await cb.answer("⛔", show_alert=True)
        return
    
    if cb.data == "start_login":
        await cb.answer()
        await cb.message.reply_text("Use <b>/login</b> command to start login!", parse_mode=ParseMode.HTML)
    elif cb.data == "status":
        await cb.answer()
        await update.message.reply_text(
            f"📊 Monitor: {'🟢' if monitor_running else '🔴'}\n🔗 Processed: {len(processed_links)}",
            parse_mode=ParseMode.HTML
        )
    elif cb.data == "stop":
        monitor_running = False
        await cb.answer("Stopped!")
        await cb.message.reply_text("⏹️ Stopped.", parse_mode=ParseMode.HTML)


# ════════════════════════════════════════════
def main():
    app = Application.builder().token(BOT_TOKEN).build()
    
    conv = ConversationHandler(
        entry_points=[CommandHandler("login", start_login)],
        states={
            PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_phone)],
            OTP: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_otp)],
            PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_password)],
        },
        fallbacks=[CommandHandler("cancel", cancel_login)],
    )
    
    app.add_handler(conv)
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CallbackQueryHandler(on_callback))
    
    logger.info("🤖 Bot v3.1 — Interactive Login — Starting...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
