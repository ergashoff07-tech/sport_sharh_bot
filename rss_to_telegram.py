"""
RSS -> Telegram kanal avtomatik post qiluvchi skript.

Ishlash tartibi:
1. config.py (yoki FEEDS o'zgaruvchisi) da ko'rsatilgan RSS manbalarni o'qiydi.
2. posted.json faylida oldin joylangan xabarlar ro'yxatini saqlaydi (takrorlanmasligi uchun).
3. Yangi (hali joylanmagan) har bir yangilikni Telegram kanalga yuboradi.
4. posted.json faylini yangilaydi (GitHub Actions bu faylni commit qilib qo'yadi).
"""

import os
import json
import time
import hashlib
import urllib.request
import xml.etree.ElementTree as ET

# ============ SOZLAMALAR ============
# RSS manbalar ro'yxati - bu yerga xohlagan saytlaringizning RSS havolasini qo'shing
# (o'zbekcha ham, chet el (ingliz/rus va h.k.) saytlar ham bo'lishi mumkin)
FEEDS = [
    "http://feeds.bbci.co.uk/sport/football/rss.xml",
    "https://www.skysports.com/rss/11095",
    "https://www.espn.com/espn/rss/soccer/news",
]

# Har bir ishga tushishda nechta yangi xabar joylash mumkinligi (spam bo'lmasligi uchun)
MAX_POSTS_PER_RUN = 5

# Tarjima sozlamalari:
#   "off"    -> tarjima qilinmaydi, asl tildagicha joylanadi
#   "google" -> bepul, tez, sifat o'rtacha (internetga bog'liq, ba'zan bloklanishi mumkin)
#   "claude" -> Anthropic Claude API orqali tarjima (sifatli, lekin ANTHROPIC_API_KEY kerak)
TRANSLATE_MODE = "google"
TARGET_LANGUAGE = "uz"  # o'zbekcha

POSTED_FILE = os.path.join(os.path.dirname(__file__), "posted.json")

# Telegram ma'lumotlari GitHub Secrets orqali keladi (pastga qarang)
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")  # masalan: @mening_kanalim yoki -1001234567890
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")  # faqat TRANSLATE_MODE="claude" bo'lsa kerak


def load_posted():
    if os.path.exists(POSTED_FILE):
        with open(POSTED_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    return set()


def save_posted(posted_set):
    # faylni cheksiz o'sishdan saqlash uchun oxirgi 2000 tasini qoldiramiz
    trimmed = list(posted_set)[-2000:]
    with open(POSTED_FILE, "w", encoding="utf-8") as f:
        json.dump(trimmed, f, ensure_ascii=False, indent=2)


def item_id(link, title):
    # link asosiy identifikator, bo'lmasa title dan hash yasaymiz
    base = link or title
    return hashlib.sha256(base.encode("utf-8")).hexdigest()


def fetch_feed_items(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        data = resp.read()
    root = ET.fromstring(data)
    items = []
    # RSS 2.0 format: channel/item
    for item in root.findall(".//item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        description = (item.findtext("description") or "").strip()
        items.append({"title": title, "link": link, "description": description})
    return items


def clean_html(text):
    # description ichidagi oddiy HTML teglarni olib tashlaymiz
    import re
    text = re.sub("<[^<]+?>", "", text)
    return text.strip()


def translate_with_google(text):
    if not text:
        return text
    from deep_translator import GoogleTranslator
    return GoogleTranslator(source="auto", target=TARGET_LANGUAGE).translate(text)


def translate_with_claude(text):
    if not text:
        return text
    if not ANTHROPIC_API_KEY:
        raise RuntimeError("TRANSLATE_MODE='claude' uchun ANTHROPIC_API_KEY secret kerak")
    api_url = "https://api.anthropic.com/v1/messages"
    payload = {
        "model": "claude-sonnet-4-6",
        "max_tokens": 1000,
        "messages": [
            {
                "role": "user",
                "content": (
                    "Quyidagi matnni o'zbek tiliga (lotin alifbosida) tabiiy va ravon "
                    "tarjima qil. Faqat tarjimani qaytar, boshqa hech narsa yozma:\n\n" + text
                ),
            }
        ],
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        api_url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        result = json.loads(resp.read().decode("utf-8"))
    return "".join(b.get("text", "") for b in result.get("content", []) if b.get("type") == "text").strip()


def translate(text):
    if TRANSLATE_MODE == "off" or not text:
        return text
    try:
        if TRANSLATE_MODE == "google":
            return translate_with_google(text)
        elif TRANSLATE_MODE == "claude":
            return translate_with_claude(text)
    except Exception as e:
        print(f"[OGOHLANTIRISH] Tarjima qilinmadi, asl matn qoldirildi: {e}")
    return text


def send_to_telegram(title, link, description):
    if not BOT_TOKEN or not CHAT_ID:
        raise RuntimeError("TELEGRAM_BOT_TOKEN yoki TELEGRAM_CHAT_ID topilmadi (Secrets sozlanganmi?)")

    text = f"<b>{title}</b>"
    desc = clean_html(description)
    if desc:
        # juda uzun bo'lmasin
        if len(desc) > 400:
            desc = desc[:400].rsplit(" ", 1)[0] + "..."
        text += f"\n\n{desc}"
    if link:
        text += f"\n\n🔗 {link}"

    api_url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": False,
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        api_url, data=data, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        result = json.loads(resp.read().decode("utf-8"))
    if not result.get("ok"):
        raise RuntimeError(f"Telegram xatoligi: {result}")


def main():
    if not FEEDS:
        print("Diqqat: FEEDS ro'yxati bo'sh. rss_to_telegram.py faylida FEEDS ni to'ldiring.")
        return

    posted = load_posted()
    new_posted = set(posted)
    total_sent = 0

    for feed_url in FEEDS:
        try:
            items = fetch_feed_items(feed_url)
        except Exception as e:
            print(f"[XATO] {feed_url} dan o'qib bo'lmadi: {e}")
            continue

        # Eskisidan yangisiga qarab yuboramiz (RSS odatda yangisi tepada bo'ladi, shu uchun teskari aylantiramiz)
        for it in reversed(items):
            if total_sent >= MAX_POSTS_PER_RUN:
                break
            uid = item_id(it["link"], it["title"])
            if uid in posted:
                continue
            try:
                title = translate(it["title"])
                description = translate(clean_html(it["description"]))
                send_to_telegram(title, it["link"], description)
                print(f"[OK] Yuborildi: {title}")
                new_posted.add(uid)
                total_sent += 1
                time.sleep(2)  # Telegram limitiga urilmaslik uchun kichik pauza
            except Exception as e:
                print(f"[XATO] Yuborib bo'lmadi ({it['title']}): {e}")

    save_posted(new_posted)
    print(f"Jami yuborilgan yangi xabarlar: {total_sent}")


if __name__ == "__main__":
    main()
