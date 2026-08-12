#!/usr/bin/env python3
"""
🕵️ GPLinks Monitor Bot v2.0 — SIMPLE
- Monitors chat 8226002644
- Jab koi GPLinks link aaye → wait for reply
- Jo destination link aaye → copy & forward to admin
- NO bypass needed — destination already mil jata hai chat mein
"""

import asyncio, logging, os, re, sys, time
from telethon import TelegramClient, events
from telethon.sessions import StringSession

# ── Config ──────────────────────────────────────────
API_ID = int(os.environ.get("TELEGRAM_API_ID", "35812449"))
API_HASH = os.environ.get("TELEGRAM_API_HASH", "099cfed535a5b2dcd8e43f157d30e3ce")
SESSION_STR = os.environ.get("TELEGRAM_SESSION", "")

MONITOR_CHAT_ID = int(os.environ.get("MONITOR_CHAT_ID", "8226002644"))
ADMIN_IDS = [int(x.strip()) for x in os.environ.get("ADMIN_IDS", "8226002644,8580876995").split(",")]

logging.basicConfig(format="%(asctime)s [%(levelname)s] %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# ── Patterns ────────────────────────────────────────
GPLINKS_PATTERN = re.compile(r"https?://(?:www\.)?gplinks?\.(?:co|com)/[a-zA-Z0-9]+(?:\?[^\s]*)?")
URL_PATTERN = re.compile(r"https?://[^\s]+")

# State
pending_links: dict = {}  # {gplinks_url: time} — links we saw, waiting for destination
processed: set = set()


def extract_any_url(text: str) -> list[str]:
    return URL_PATTERN.findall(text)

def extract_gplinks(text: str) -> list[str]:
    return GPLINKS_PATTERN.findall(text)


def is_destination(url: str) -> bool:
    """Check if URL looks like a destination (not GPLinks, not intermediate)"""
    skip = ["gplinks.co","gplinks.com","gplink.co","gplink.com",
            "skrresults.com","mrdrt.com","trustify.click",
            "rostelshute.shop","banchibipack.com","loginbreton.com",
            "generateed.pages.dev","t.me","telegram.me"]
    from urllib.parse import urlparse
    dom = urlparse(url).netloc.lower()
    return not any(dom == s or dom.endswith("."+s) for s in skip)


async def forward_to_admin(client: TelegramClient, gplinks_url: str, destination_url: str):
    """Forward the destination to all admin IDs"""
    msg = (f"🔗 <b>GPLinks Link:</b>\n<code>{gplinks_url}</code>\n\n"
           f"🎯 <b>Destination:</b>\n<code>{destination_url}</code>\n\n"
           f"<a href='{destination_url}'>Open Link →</a>")
    
    for aid in ADMIN_IDS:
        try:
            await client.send_message(aid, msg, parse_mode="html", link_preview=False)
            logger.info(f"📤 Forwarded to admin {aid}")
        except Exception as e:
            logger.error(f"Failed to send to {aid}: {e}")


async def main():
    logger.info("🕵️ Starting GPLinks Forward Bot v2.0...")

    if SESSION_STR and len(SESSION_STR) > 50:
        client = TelegramClient(StringSession(SESSION_STR), API_ID, API_HASH)
    else:
        client = TelegramClient(SESSION_STR or "telegram_session", API_ID, API_HASH)

    # ── Message handler: detect GPLinks links ──
    @client.on(events.NewMessage(chats=[MONITOR_CHAT_ID]))
    async def on_message(event):
        text = event.message.text or ""
        if not text.strip():
            return

        gplinks = extract_gplinks(text)
        all_urls = extract_any_url(text)

        # ── CASE 1: New GPLinks link detected → mark as pending ──
        for gl in gplinks:
            if gl not in processed and gl not in pending_links:
                pending_links[gl] = time.time()
                logger.info(f"🔗 New GPLinks: {gl[:60]}...")

        # ── CASE 2: Check if any URL is a destination ──
        for url in all_urls:
            # Skip GPLinks URLs themselves
            if "gplinks" in url.lower():
                continue

            # Check if this URL is a destination for a pending link
            if is_destination(url):
                # Find any pending link from last 60 seconds
                to_remove = []
                for gl, t in pending_links.items():
                    if gl not in processed and time.time() - t < 120:  # within 2 min
                        processed.add(gl)
                        to_remove.append(gl)
                        logger.info(f"✅ Destination: {url[:80]}...")
                        await forward_to_admin(client, gl, url)
                
                for gl in to_remove:
                    del pending_links[gl]

        # ── Cleanup: remove old pending links (>5 min) ──
        to_remove = [gl for gl, t in pending_links.items() if time.time() - t > 300]
        for gl in to_remove:
            del pending_links[gl]

    # ── Admin commands ──
    @client.on(events.NewMessage(pattern=r"^/(start|status|help)$"))
    async def cmd_handler(event):
        if event.message.sender_id not in ADMIN_IDS:
            return
        cmd = event.pattern_match.group(1)
        if cmd == "start":
            await event.reply(f"🕵️ <b>GPLinks Forward Bot v2.0</b>\n\n👀 Monitoring: <code>{MONITOR_CHAT_ID}</code>\n📤 Forwarding destinations to admins\n\n/status /help", parse_mode="html")
        elif cmd == "status":
            await event.reply(f"📊 <b>Status</b>\n👀 Chat: <code>{MONITOR_CHAT_ID}</code>\n⏳ Pending: <b>{len(pending_links)}</b>\n✅ Processed: <b>{len(processed)}</b>\n👑 Admins: <b>{len(ADMIN_IDS)}</b>", parse_mode="html")
        elif cmd == "help":
            await event.reply("Bot monitors the chat. When a GPLinks destination appears, it forwards to admins.\n\n/start /status", parse_mode="html")

    await client.start()
    me = await client.get_me()
    logger.info(f"✅ Logged in as: {me.first_name} (@{me.username or 'N/A'})")
    logger.info(f"👀 Watching chat: {MONITOR_CHAT_ID}")

    # Startup notification
    for aid in ADMIN_IDS:
        try:
            await client.send_message(aid, f"🟢 <b>Forward Bot Active!</b>\nWatching chat <code>{MONITOR_CHAT_ID}</code>", parse_mode="html")
        except:
            pass

    await client.run_until_disconnected()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 Shutting down...")
