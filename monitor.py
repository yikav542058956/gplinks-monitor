#!/usr/bin/env python3
"""
🕵️ GPLinks Monitor Bot
- Logs in as Telegram USER (not bot) via Telethon
- Monitors chat 8226002644 for GPLinks links
- Auto-bypasses using Playwright browser
- Sends destination link back to the monitored chat
- Admin commands for admins 8226002644 & 8580876995
"""

import asyncio, logging, os, re, sys, time, json
from urllib.parse import urlparse

# ── Telegram Client ──
from telethon import TelegramClient, events
from telethon.sessions import StringSession

# ── Bypass ──
PLAYWRIGHT_AVAILABLE = False
try:
    from playwright.async_api import async_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    pass

# ── Config ──────────────────────────────────────────
API_ID = int(os.environ.get("TELEGRAM_API_ID", "35812449"))
API_HASH = os.environ.get("TELEGRAM_API_HASH", "099cfed535a5b2dcd8e43f157d30e3ce")
SESSION_STR = os.environ.get("TELEGRAM_SESSION", "")

MONITOR_CHAT_ID = int(os.environ.get("MONITOR_CHAT_ID", "8226002644"))
ADMIN_IDS = [int(x.strip()) for x in os.environ.get("ADMIN_IDS", "8226002644,8580876995").split(",")]

logging.basicConfig(format="%(asctime)s [%(levelname)s] %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

processed_links: set = set()

GPLINKS_PATTERN = re.compile(r"https?://(?:www\.)?gplinks?\.(?:co|com)/[a-zA-Z0-9]+(?:\?[^\s]*)?")

def find_all_gplinks(text: str) -> list[str]:
    return GPLINKS_PATTERN.findall(text)

def is_valid_dest(u: str) -> bool:
    skip = ["gplinks.co","gplinks.com","gplink.co","gplink.com",
            "skrresults.com","mrdrt.com","trustify.click",
            "rostelshute.shop","banchibipack.com","loginbreton.com",
            "google.com","doubleclick.net","googlesyndication.com",
            "generateed.pages.dev"]
    dom = urlparse(u).netloc.lower()
    return not any(dom == s or dom.endswith("."+s) for s in skip)

async def bypass_gplinks(url: str) -> str:
    if not PLAYWRIGHT_AVAILABLE:
        raise RuntimeError("Playwright not installed")
    steps, dest = 0, None
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox","--disable-setuid-sandbox","--disable-dev-shm-usage","--disable-gpu"])
        ctx = await browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/151.0.0.0 Safari/537.36", viewport={"width":1366,"height":768})
        page = await ctx.new_page()
        await page.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>false});window.chrome={runtime:{}};")
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        for _ in range(15):
            if "skrresults" in page.url.lower(): break
            await asyncio.sleep(1)
        for _ in range(40):
            cur = page.url
            if is_valid_dest(cur): dest = cur; break
            try: await page.evaluate("(function(){var t=document.getElementById('myTimer');if(t)t.textContent='0';var d=document.getElementById('myTimerDiv');if(d)d.style.display='none';var v=document.getElementById('VerifyBtn');if(v){v.style.display='block';v.disabled=false;}var g=document.getElementById('GoNewxtDiv');if(g)g.style.display='block';document.querySelectorAll('button').forEach(function(b){if((b.textContent||'').toUpperCase().trim()==='CANCEL')b.click();});})();")
            except: pass
            await asyncio.sleep(0.5)
            try:
                ok = await page.evaluate("(function(){var v=document.getElementById('VerifyBtn');if(v&&v.offsetParent){v.click();return'clicked';}return'no';})();")
                if ok == 'clicked': steps += 1; await asyncio.sleep(0.8)
            except: pass
            try: await page.evaluate("(function(){var n=document.getElementById('NextBtn');if(n&&n.offsetParent)n.click();})();")
            except: pass
            try: await page.evaluate("(function(){var f=document.getElementById('adsForm');if(f){var s=f.querySelector('[name=step_id]');if(s)s.value='5';var a=f.querySelector('[name=ad_impressions]');if(a)a.value='5';}})();")
            except: pass
            nu = page.url
            if nu != cur and is_valid_dest(nu): dest = nu; break
            await asyncio.sleep(1.0)
        await browser.close()
    if dest: return dest
    if steps >= 5: raise Exception("DEST_SERVER_DOWN")
    raise Exception("Bypass failed")

async def send_to_chat(client: TelegramClient, message: str):
    try:
        await client.send_message(MONITOR_CHAT_ID, message, parse_mode="html", link_preview=False)
    except Exception as e:
        logger.error(f"Send failed: {e}")

async def process_link(client: TelegramClient, url: str):
    if url in processed_links: return
    processed_links.add(url)
    logger.info(f"🔗 Processing: {url[:60]}...")
    try:
        await send_to_chat(client, f"⚡ <b>Processing...</b>\n<code>{url[:50]}...</code>")
        dest = await bypass_gplinks(url)
        await send_to_chat(client, f"✅ <b>Done!</b>\n🔗 <code>{dest}</code>\n<a href='{dest}'>Open →</a>")
        logger.info(f"✅ {dest[:80]}")
    except Exception as e:
        if "DEST_SERVER_DOWN" in str(e):
            await send_to_chat(client, "⚠️ <b>Destination DOWN!</b>\nAll steps complete, server offline.")
        else:
            await send_to_chat(client, f"❌ {str(e)[:200]}")
        logger.error(f"Failed: {e}")

async def main():
    logger.info("🕵️ Starting GPLinks Monitor...")
    if SESSION_STR and len(SESSION_STR) > 50:
        client = TelegramClient(StringSession(SESSION_STR), API_ID, API_HASH)
        logger.info("Using StringSession")
    else:
        sf = SESSION_STR or "telegram_session"
        client = TelegramClient(sf, API_ID, API_HASH)
        logger.info(f"Using file: {sf}")

    @client.on(events.NewMessage(chats=[MONITOR_CHAT_ID]))
    async def handler(event):
        text = event.message.text or ""
        if not text.strip(): return
        urls = find_all_gplinks(text)
        if not urls: return
        logger.info(f"📨 {len(urls)} link(s) from {event.message.sender_id}")
        for url in urls:
            asyncio.create_task(process_link(client, url))

    @client.on(events.NewMessage(pattern=r"^/(start|status|help)$"))
    async def cmd_handler(event):
        if event.message.sender_id not in ADMIN_IDS: return
        cmd = event.pattern_match.group(1)
        if cmd == "start":
            await event.reply(f"🕵️ <b>GPLinks Monitor</b>\n\n👀 Chat: <code>{MONITOR_CHAT_ID}</code>\n🔗 Auto-bypass ON\n\n/status /help", parse_mode="html")
        elif cmd == "status":
            await event.reply(f"📊 <b>Status</b>\n👀 Chat: <code>{MONITOR_CHAT_ID}</code>\n🔗 Processed: <b>{len(processed_links)}</b>\n🎭 Playwright: {'✅' if PLAYWRIGHT_AVAILABLE else '❌'}", parse_mode="html")
        elif cmd == "help":
            await event.reply("/start — Info\n/status — Stats\n\nSend GPLinks link in monitored chat → auto-bypass!")

    await client.start()
    me = await client.get_me()
    logger.info(f"✅ Logged in as: {me.first_name} (@{me.username or 'N/A'})")
    logger.info(f"👀 Watching: {MONITOR_CHAT_ID}")
    await send_to_chat(client, "🟢 <b>Monitor Active!</b>\nAuto-bypass GPLinks links...")
    await client.run_until_disconnected()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 Shutting down...")
