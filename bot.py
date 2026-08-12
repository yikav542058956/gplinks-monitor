#!/usr/bin/env python3
"""
📱 GPLinks Monitor Bot v4.0 — FULL INTERACTIVE LOGIN
- /start → /login → Phone → OTP → 2FA → Logged in → Monitor
- Sab kuch bot ke andar, step-by-step
- No external website needed
- Chat 8226002644 monitor + forward destination to admin
"""

import asyncio, logging, os, re, time
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    ConversationHandler, filters, ContextTypes
)
from telegram.constants import ParseMode

logging.basicConfig(format="%(asctime)s [%(levelname)s] %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# ── Config ──
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "8397171996:AAFZFT0ruUh4Augc4M6J19W7d9qKG5sHAVA")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "8580876995"))
TARGET_CHAT_ID = int(os.environ.get("TARGET_CHAT_ID", "8226002644"))
API_ID = int(os.environ.get("TELEGRAM_API_ID", "35812449"))
API_HASH = os.environ.get("TELEGRAM_API_HASH", "099cfed535a5b2dcd8e43f157d30e3ce")

# ── States ──
PHONE, OTP, PASSWORD = range(3)

# ── Global State ──
monitor_running = False
processed_links = set()
pending_links = {}
login_state = {}  # {user_id: {phone, client, phone_code_hash}}

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
#  START
# ════════════════════════════════════════════

async def cmd_start(update, ctx):
    uid = update.effective_user.id
    if uid != ADMIN_ID:
        await update.message.reply_text("⛔ Private bot hai.")
        return
    
    await update.message.reply_text(
        f"⚡ <b>GPLinks Forward Bot v4.0</b>\n\n"
        f"👤 Admin: <code>{ADMIN_ID}</code>\n"
        f"👀 Target Chat: <code>{TARGET_CHAT_ID}</code>\n"
        f"📡 Monitor: {'🟢 ON' if monitor_running else '🔴 OFF'}\n"
        f"🔗 Processed: <b>{len(processed_links)}</b>\n\n"
        "<b>Commands:</b>\n"
        "/login — <b>Login (Phone → OTP → 2FA)</b>\n"
        "/status — Stats\n"
        "/stop — Stop Monitor",
        parse_mode=ParseMode.HTML
    )


# ════════════════════════════════════════════
#  LOGIN CONVERSATION
# ════════════════════════════════════════════

async def login_start(update, ctx):
    """Step 1: Ask for phone number"""
    if update.effective_user.id != ADMIN_ID:
        return ConversationHandler.END
    
    login_state.clear()
    
    await update.message.reply_text(
        "🔐 <b>LOGIN — Step 1/3</b>\n\n"
        "📱 Apna phone number bhejo:\n"
        "<code>+919564335498</code>\n\n"
        "<i>/cancel to abort</i>",
        parse_mode=ParseMode.HTML
    )
    return PHONE


async def login_phone(update, ctx):
    """Step 2: Got phone → send OTP"""
    phone = update.message.text.strip()
    if not phone.startswith("+"):
        phone = "+" + phone
    
    msg = await update.message.reply_text(f"📲 <b>Sending OTP to {phone}...</b>", parse_mode=ParseMode.HTML)
    
    try:
        from telethon import TelegramClient
        from telethon.sessions import StringSession
        
        client = TelegramClient(StringSession(), API_ID, API_HASH)
        await client.connect()
        sent = await client.send_code_request(phone)
        
        login_state["phone"] = phone
        login_state["client"] = client
        login_state["phone_code_hash"] = sent.phone_code_hash
        
        await msg.edit_text(
            f"📲 <b>OTP sent to {phone}!</b>\n\n"
            f"📝 <b>Step 2/3 — OTP code bhejo:</b>\n\n"
            f"<i>/cancel to abort</i>",
            parse_mode=ParseMode.HTML
        )
        return OTP
        
    except Exception as e:
        await msg.edit_text(f"❌ <b>Failed:</b> {str(e)[:200]}\n\nTry: /login", parse_mode=ParseMode.HTML)
        return ConversationHandler.END


async def login_otp(update, ctx):
    """Step 3: Got OTP → sign in or ask 2FA"""
    code = update.message.text.strip()
    client = login_state.get("client")
    phone = login_state.get("phone", "")
    phone_code_hash = login_state.get("phone_code_hash", "")
    
    msg = await update.message.reply_text("🔐 <b>Verifying OTP...</b>", parse_mode=ParseMode.HTML)
    
    try:
        me = await client.sign_in(phone, code, phone_code_hash=phone_code_hash)
        # NO 2FA → DONE!
        session_str = client.session.save()
        await client.disconnect()
        
        await msg.edit_text(
            f"✅ <b>Logged in as:</b> {me.first_name} (@{me.username or 'N/A'})\n\n"
            f"🟢 Starting monitor on <code>{TARGET_CHAT_ID}</code>...",
            parse_mode=ParseMode.HTML
        )
        
        asyncio.create_task(run_monitor(session_str, ctx))
        return ConversationHandler.END
        
    except Exception as e:
        err = str(e)
        if "password" in err.lower() or "2fa" in err.lower():
            await msg.edit_text(
                "🔒 <b>2FA Protected!</b>\n\n"
                "🔑 <b>Step 3/3 — 2FA password bhejo:</b>\n\n"
                "<i>/cancel to abort</i>",
                parse_mode=ParseMode.HTML
            )
            return PASSWORD
        
        elif "invalid" in err.lower() or "expired" in err.lower():
            await msg.edit_text(f"❌ OTP invalid/expired!\n\nTry: /login", parse_mode=ParseMode.HTML)
            try: await client.disconnect()
            except: pass
            return ConversationHandler.END
        
        else:
            await msg.edit_text(f"❌ Error: {err[:200]}\n\nTry: /login", parse_mode=ParseMode.HTML)
            try: await client.disconnect()
            except: pass
            return ConversationHandler.END


async def login_password(update, ctx):
    """Step 4: Got 2FA password → final sign in"""
    pwd = update.message.text.strip()
    client = login_state.get("client")
    
    msg = await update.message.reply_text("🔑 <b>Checking password...</b>", parse_mode=ParseMode.HTML)
    
    try:
        me = await client.sign_in(password=pwd)
        session_str = client.session.save()
        await client.disconnect()
        
        await msg.edit_text(
            f"✅ <b>Logged in as:</b> {me.first_name} (@{me.username or 'N/A'})\n\n"
            f"🟢 Starting monitor on <code>{TARGET_CHAT_ID}</code>...",
            parse_mode=ParseMode.HTML
        )
        
        asyncio.create_task(run_monitor(session_str, ctx))
        return ConversationHandler.END
        
    except Exception as e:
        await msg.edit_text(f"❌ Wrong password! {str(e)[:200]}\n\nTry: /login", parse_mode=ParseMode.HTML)
        try: await client.disconnect()
        except: pass
        return ConversationHandler.END


async def login_cancel(update, ctx):
    client = login_state.pop("client", None)
    if client:
        try: await client.disconnect()
        except: pass
    login_state.clear()
    await update.message.reply_text("🚫 Cancelled. /login to retry.")
    return ConversationHandler.END


# ════════════════════════════════════════════
#  MONITOR
# ════════════════════════════════════════════

async def run_monitor(session_str, ctx):
    global monitor_running
    
    from telethon import TelegramClient, events
    from telethon.sessions import StringSession
    
    client = TelegramClient(StringSession(session_str), API_ID, API_HASH)
    await client.start()
    monitor_running = True
    logger.info(f"👀 Monitoring chat {TARGET_CHAT_ID}...")
    
    # Notify admin
    try:
        await ctx.bot.send_message(ADMIN_ID,
            f"🟢 <b>Monitor Started!</b>\n👀 Chat: <code>{TARGET_CHAT_ID}</code>",
            parse_mode=ParseMode.HTML)
    except: pass
    
    @client.on(events.NewMessage(chats=[TARGET_CHAT_ID]))
    async def handler(event):
        if not monitor_running:
            return
        text = event.message.text or ""
        if not text.strip():
            return
        
        gplinks = GPLINKS_RE.findall(text)
        all_urls = ANY_URL_RE.findall(text)
        
        # New GPLinks
        for gl in gplinks:
            if gl not in processed_links and gl not in pending_links:
                pending_links[gl] = time.time()
                logger.info(f"🔗 {gl[:60]}")
                try:
                    await ctx.bot.send_message(ADMIN_ID,
                        f"🔗 <b>New GPLinks link!</b>\n<code>{gl}</code>\n⏳ Waiting...",
                        parse_mode=ParseMode.HTML)
                except: pass
        
        # Destinations
        for url in all_urls:
            if "gplinks" in url.lower():
                continue
            if is_dest(url):
                for gl, t in list(pending_links.items()):
                    if gl not in processed_links and time.time() - t < 120:
                        processed_links.add(gl)
                        del pending_links[gl]
                        msg = (f"✅ <b>Destination!</b>\n\n"
                               f"🔗 <b>Source:</b> <code>{gl}</code>\n"
                               f"🎯 <b>Dest:</b> <code>{url}</code>\n"
                               f"<a href='{url}'>Open Link →</a>")
                        try:
                            await ctx.bot.send_message(ADMIN_ID, msg,
                                parse_mode=ParseMode.HTML, disable_web_page_preview=False)
                        except: pass
        
        # Cleanup
        for gl, t in list(pending_links.items()):
            if time.time() - t > 300:
                del pending_links[gl]
    
    while monitor_running:
        await asyncio.sleep(1)


# ════════════════════════════════════════════
#  OTHER COMMANDS
# ════════════════════════════════════════════

async def cmd_status(update, ctx):
    if update.effective_user.id != ADMIN_ID:
        return
    await update.message.reply_text(
        f"📊 <b>Status</b>\n"
        f"📡 Monitor: {'🟢 ON' if monitor_running else '🔴 OFF'}\n"
        f"🔗 Processed: {len(processed_links)}\n"
        f"⏳ Pending: {len(pending_links)}",
        parse_mode=ParseMode.HTML
    )


async def cmd_stop(update, ctx):
    global monitor_running
    if update.effective_user.id != ADMIN_ID:
        return
    monitor_running = False
    await update.message.reply_text("⏹️ <b>Monitor stopped.</b>\n/login to restart.", parse_mode=ParseMode.HTML)


# ════════════════════════════════════════════
def main():
    app = Application.builder().token(BOT_TOKEN).build()
    
    conv = ConversationHandler(
        entry_points=[CommandHandler("login", login_start)],
        states={
            PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, login_phone)],
            OTP: [MessageHandler(filters.TEXT & ~filters.COMMAND, login_otp)],
            PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, login_password)],
        },
        fallbacks=[CommandHandler("cancel", login_cancel)],
    )
    
    app.add_handler(conv)
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("stop", cmd_stop))
    
    logger.info("🤖 Bot v4.0 — Full Interactive Login — Started!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
