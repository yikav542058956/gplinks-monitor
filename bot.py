#!/usr/bin/env python3
"""
📱 GPLinks Monitor Bot v4.1 — FORWARD ANY USER MESSAGE TO TARGET CHAT
- Koi bhi user bot ko message bheje → bot TARGET_CHAT_ID mein forward karega
- Plain text forward (no HTML parse errors)
- Admin /login → Phone → OTP → 2FA → Monitor ON
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

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "8397171996:AAFZFT0ruUh4Augc4M6J19W7d9qKG5sHAVA")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "8580876995"))
TARGET_CHAT_ID = int(os.environ.get("TARGET_CHAT_ID", "8226002644"))
API_ID = int(os.environ.get("TELEGRAM_API_ID", "35812449"))
API_HASH = os.environ.get("TELEGRAM_API_HASH", "099cfed535a5b2dcd8e43f157d30e3ce")

PHONE, OTP, PASSWORD = range(3)

monitor_running = False
processed_links = set()
pending_links = {}
login_state = {}

GPLINKS_RE = re.compile(r"https?://(?:www\.)?gplinks?\.(?:co|com)/[a-zA-Z0-9]+(?:\?[^\s]*)?")
ANY_URL_RE = re.compile(r"https?://[^\s]+")

def is_dest(url):
    skip = ["gplinks.co","gplinks.com","gplink.co","gplink.com","skrresults.com","mrdrt.com",
            "trustify.click","rostelshute.shop","banchibipack.com","loginbreton.com",
            "generateed.pages.dev","t.me","telegram.me","web.telegram.org"]
    from urllib.parse import urlparse
    dom = urlparse(url).netloc.lower()
    return not any(dom == s or dom.endswith("."+s) for s in skip)


async def forward_to_target(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = update.message.text or update.message.caption or ""
    if not text.strip():
        return
    fwd = f"📩 {user.first_name} (@{user.username or 'N/A'}) [{user.id}]\n\n💬 {text}"
    try:
        await ctx.bot.send_message(TARGET_CHAT_ID, fwd)
        logger.info(f"✅ Forwarded user {user.id} → chat {TARGET_CHAT_ID}")
    except Exception as e:
        logger.error(f"❌ Forward failed: {e}")


async def cmd_start(update, ctx):
    uid = update.effective_user.id
    if uid != ADMIN_ID:
        await update.message.reply_text("👋 Hi! Send any link/message, I'll forward it.")
        return
    await update.message.reply_text(
        f"⚡ <b>GPLinks Forward Bot v4.1</b>\n\n"
        f"👤 Admin: <code>{ADMIN_ID}</code>\n"
        f"👀 Target: <code>{TARGET_CHAT_ID}</code>\n"
        f"📡 Monitor: {'🟢 ON' if monitor_running else '🔴 OFF'}\n"
        f"🔗 Processed: <b>{len(processed_links)}</b>\n\n"
        "📩 <b>ANY user message → Target chat!</b>\n\n"
        "/login — Login & start monitor\n"
        "/status — Stats\n"
        "/stop — Stop",
        parse_mode=ParseMode.HTML
    )


async def login_start(update, ctx):
    if update.effective_user.id != ADMIN_ID: return ConversationHandler.END
    login_state.clear()
    await update.message.reply_text("🔐 <b>LOGIN — Step 1/3</b>\n\n📱 Phone:\n<code>+919564335498</code>\n\n<i>/cancel</i>", parse_mode=ParseMode.HTML)
    return PHONE

async def login_phone(update, ctx):
    phone = update.message.text.strip()
    if not phone.startswith("+"): phone = "+" + phone
    msg = await update.message.reply_text("📲 Sending OTP...", parse_mode=ParseMode.HTML)
    try:
        from telethon import TelegramClient
        from telethon.sessions import StringSession
        client = TelegramClient(StringSession(), API_ID, API_HASH)
        await client.connect()
        sent = await client.send_code_request(phone)
        login_state["phone"] = phone
        login_state["client"] = client
        login_state["phone_code_hash"] = sent.phone_code_hash
        await msg.edit_text(f"📲 <b>OTP sent!</b>\n\n📝 <b>Step 2/3 — OTP:</b>\n<i>/cancel</i>", parse_mode=ParseMode.HTML)
        return OTP
    except Exception as e:
        await msg.edit_text(f"❌ {str(e)[:200]}\n/login", parse_mode=ParseMode.HTML)
        return ConversationHandler.END

async def login_otp(update, ctx):
    code = update.message.text.strip()
    client = login_state.get("client")
    phone = login_state.get("phone", "")
    phash = login_state.get("phone_code_hash", "")
    msg = await update.message.reply_text("🔐 Verifying...", parse_mode=ParseMode.HTML)
    try:
        me = await client.sign_in(phone, code, phone_code_hash=phash)
        s = client.session.save()
        await client.disconnect()
        await msg.edit_text(f"✅ <b>{me.first_name}</b>\n🟢 Monitoring...", parse_mode=ParseMode.HTML)
        asyncio.create_task(run_monitor(s, ctx))
        return ConversationHandler.END
    except Exception as e:
        err = str(e)
        if "password" in err.lower() or "2fa" in err.lower():
            await msg.edit_text("🔒 <b>2FA!</b>\n\n🔑 <b>Step 3/3 — Password:</b>\n<i>/cancel</i>", parse_mode=ParseMode.HTML)
            return PASSWORD
        elif "invalid" in err.lower() or "expired" in err.lower():
            await msg.edit_text("❌ OTP invalid!\n/login", parse_mode=ParseMode.HTML)
            try: await client.disconnect()
            except: pass
            return ConversationHandler.END
        else:
            await msg.edit_text(f"❌ {err[:200]}\n/login", parse_mode=ParseMode.HTML)
            try: await client.disconnect()
            except: pass
            return ConversationHandler.END

async def login_password(update, ctx):
    pwd = update.message.text.strip()
    client = login_state.get("client")
    msg = await update.message.reply_text("🔑 Checking...", parse_mode=ParseMode.HTML)
    try:
        me = await client.sign_in(password=pwd)
        s = client.session.save()
        await client.disconnect()
        await msg.edit_text(f"✅ <b>{me.first_name}</b>\n🟢 Monitoring...", parse_mode=ParseMode.HTML)
        asyncio.create_task(run_monitor(s, ctx))
        return ConversationHandler.END
    except Exception as e:
        await msg.edit_text(f"❌ {str(e)[:200]}\n/login", parse_mode=ParseMode.HTML)
        try: await client.disconnect()
        except: pass
        return ConversationHandler.END

async def login_cancel(update, ctx):
    c = login_state.pop("client", None)
    if c:
        try: await c.disconnect()
        except: pass
    login_state.clear()
    await update.message.reply_text("🚫 Cancelled.")
    return ConversationHandler.END


async def run_monitor(session_str, ctx):
    global monitor_running
    from telethon import TelegramClient, events
    from telethon.sessions import StringSession
    client = TelegramClient(StringSession(session_str), API_ID, API_HASH)
    await client.start()
    monitor_running = True
    try:
        await ctx.bot.send_message(ADMIN_ID, f"🟢 <b>Monitor ON!</b>\n👀 <code>{TARGET_CHAT_ID}</code>", parse_mode=ParseMode.HTML)
    except: pass

    @client.on(events.NewMessage(chats=[TARGET_CHAT_ID]))
    async def h(event):
        if not monitor_running: return
        text = event.message.text or ""
        if not text.strip(): return
        gl = GPLINKS_RE.findall(text)
        urls = ANY_URL_RE.findall(text)
        for g in gl:
            if g not in processed_links and g not in pending_links:
                pending_links[g] = time.time()
                try: await ctx.bot.send_message(ADMIN_ID, f"🔗 <b>GPLinks!</b>\n<code>{g}</code>\n⏳ Waiting...", parse_mode=ParseMode.HTML)
                except: pass
        for u in urls:
            if "gplinks" in u.lower(): continue
            if is_dest(u):
                for g, t in list(pending_links.items()):
                    if g not in processed_links and time.time() - t < 120:
                        processed_links.add(g)
                        del pending_links[g]
                        try: await ctx.bot.send_message(ADMIN_ID, f"✅ <b>Dest!</b>\n🔗 <code>{g}</code>\n🎯 <code>{u}</code>\n<a href='{u}'>Open</a>", parse_mode=ParseMode.HTML, disable_web_page_preview=False)
                        except: pass
        for g, t in list(pending_links.items()):
            if time.time() - t > 300: del pending_links[g]
    while monitor_running:
        await asyncio.sleep(1)


async def cmd_status(update, ctx):
    if update.effective_user.id != ADMIN_ID: return
    await update.message.reply_text(f"📊 Monitor: {'🟢' if monitor_running else '🔴'}\n🔗 {len(processed_links)}", parse_mode=ParseMode.HTML)

async def cmd_stop(update, ctx):
    global monitor_running
    if update.effective_user.id != ADMIN_ID: return
    monitor_running = False
    await update.message.reply_text("⏹️ Stopped.", parse_mode=ParseMode.HTML)


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
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, forward_to_target))
    logger.info("🤖 Bot v4.1 — Forward + Monitor — Started!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
