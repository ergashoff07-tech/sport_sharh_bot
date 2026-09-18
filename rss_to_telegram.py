"""
RSS -> Telegram kanal avtomatik post qiluvchi skript.

Ishlash tartibi:
1. Har 5 daqiqada barcha FEEDS manbalarini tekshiradi (haqiqiy vaqtga eng yaqin,
   bepul avtomatika uchun texnik jihatdan eng tez mumkin bo'lgan oraliq).
2. Agar bir nechta manba BIR XIL voqea haqida yozgan bo'lsa (sarlavhalar o'xshash),
   ularni bitta post sifatida qabul qiladi va faqat BIR MARTA joylaydi.
3. Har bir ishga tushishda faqat 1 ta yangi (yoki birlashtirilgan) voqeani joylaydi.
4. Rasm bo'lsa - rasm bilan, matnni iqtibos (quote) blokida chiroyli formatlab yuboradi.
5. Manba havolasi postga qo'shilmaydi.
"""

import os
import re
import json
import difflib
import hashlib
import urllib.request
import xml.etree.ElementTree as ET

# ============ SOZLAMALAR ============
FEEDS = [
    "http://feeds.bbci.co.uk/sport/football/rss.xml",
    "https://www.skysports.com/rss/11095",
    "https://www.espn.com/espn/rss/soccer/news",
]

TRANSLATE_MODE = "google"   # "off" / "google" / "claude"
TARGET_LANGUAGE = "uz"

# Ikki sarlavha shuncha foiz o'xshash bo'lsa - "bir xil voqea" deb hisoblanadi
SIMILARITY_THRESHOLD = 0.55

BASE_DIR = os.path.dirname(__file__)
POSTED_FILE = os.path.join(BASE_DIR, "posted.json")
STATE_FILE = os.path.join(BASE_DIR, "state.json")

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")


def load_posted():
    if os.path.exists(POSTED_FILE):
        with open(POSTED_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    return set()


def save_posted(posted_set):
    trimmed = list(posted_set)[-3000:]
    with open(POSTED_FILE, "w", encoding="utf-8") as f:
        json.dump(trimmed, f, ensure_ascii=False, indent=2)


def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"next_feed_index": 0}


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def item_id(link, title):
    base = link or title
    return hashlib.sha256(base.encode("utf-8")).hexdigest()


def normalize_title(t):
    t = t.lower()
    t = re.sub(r"[^\w\s]", "", t)
    t = re.sub(r"\s+", " ", t)
    return t.strip()


def is_similar(t1, t2):
    return difflib.SequenceMatcher(None, normalize_title(t1), normalize_title(t2)).ratio() >= SIMILARITY_THRESHOLD


def fetch_feed_items(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        data = resp.read()
    root = ET.fromstring(data)
    items = []
    for item in root.findall(".//item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        description = (item.findtext("description") or "").strip()

        image_url = None
        enclosure = item.find("enclosure")
        if enclosure is not None and enclosure.get("type", "").startswith("image"):
            image_url = enclosure.get("url")
        if not image_url:
            for child in item:
                tag = child.tag.split("}")[-1]
                if tag in ("content", "thumbnail") and child.get("url"):
                    image_url = child.get("url")
                    break

        items.append({
            "title": title,
            "link": link,
            "description": description,
            "image": image_url,
        })
    return items


def clean_html(text):
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
        "messages": [{
            "role": "user",
            "content": (
                "Quyidagi matnni o'zbek tiliga (lotin alifbosida) tabiiy va ravon "
                "tarjima qil. Faqat tarjimani qaytar, boshqa hech narsa yozma:\n\n" + text
            ),
        }],
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        api_url, data=data,
        headers={
            "Content-Type": "application/json",
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        result = json.loads(resp.read().decode("utf-8"))
    return "".join(
        b.get("text", "") for b in result.get("content", []) if b.get("type") == "text"
    ).strip()


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


def _telegram_api(method, payload):
    api_url = f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(api_url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=25) as resp:
        result = json.loads(resp.read().decode("utf-8"))
    if not result.get("ok"):
        raise RuntimeError(f"Telegram xatoligi: {result}")


def build_caption(title, description, limit):
    head = f"⚽️ <b>{title}</b>"
    desc = clean_html(description)
    text = head
    if desc:
        room = limit - len(head) - len("\n\n<blockquote></blockquote>") - 4
        if room > 20:
            if len(desc) > room:
                desc = desc[:room].rsplit(" ", 1)[0] + "..."
            text += f"\n\n<blockquote>{desc}</blockquote>"
    return text


def send_to_telegram(title, description, image_url):
    if not BOT_TOKEN or not CHAT_ID:
        raise RuntimeError("TELEGRAM_BOT_TOKEN yoki TELEGRAM_CHAT_ID topilmadi (Secrets sozlanganmi?)")

    if image_url:
        caption = build_caption(title, description, limit=1024)
        try:
            _telegram_api("sendPhoto", {
                "chat_id": CHAT_ID,
                "photo": image_url,
                "caption": caption,
                "parse_mode": "HTML",
            })
            return
        except Exception as e:
            print(f"[OGOHLANTIRISH] Rasm bilan yuborib bo'lmadi, matn sifatida yuboriladi: {e}")

    caption = build_caption(title, description, limit=4096)
    _telegram_api("sendMessage", {
        "chat_id": CHAT_ID,
        "text": caption,
        "parse_mode": "HTML",
    })


def main():
    if not FEEDS:
        print("Diqqat: FEEDS ro'yxati bo'sh.")
        return

    posted = load_posted()
    state = load_state()
    n = len(FEEDS)
    start_idx = state.get("next_feed_index", 0) % n

    all_pending = []
    for offset in range(n):
        idx = (start_idx + offset) % n
        feed_url = FEEDS[idx]
        try:
            items = fetch_feed_items(feed_url)
        except Exception as e:
            print(f"[XATO] {feed_url} dan o'qib bo'lmadi: {e}")
            continue
        for it in reversed(items):
            uid = item_id(it["link"], it["title"])
            if uid not in posted:
                it2 = dict(it)
                it2["uid"] = uid
                it2["feed_idx"] = idx
                all_pending.append(it2)

    if not all_pending:
        print("Yangi xabar topilmadi.")
        state["next_feed_index"] = (start_idx + 1) % n
        save_state(state)
        return

    anchor = all_pending[0]

    cluster = [anchor]
    for it in all_pending[1:]:
        if is_similar(it["title"], anchor["title"]):
            cluster.append(it)

    chosen_image = anchor.get("image")
    if not chosen_image:
        for it in cluster:
            if it.get("image"):
                chosen_image = it["image"]
                break

    try:
        title = translate(anchor["title"])
        description = translate(clean_html(anchor["description"]))
        send_to_telegram(title, description, chosen_image)
        print(f"[OK] Yuborildi: {title}  (bu voqeani {len(cluster)} ta manba yozgan edi)")
    except Exception as e:
        print(f"[XATO] Yuborib bo'lmadi: {e}")
        state["next_feed_index"] = (start_idx + 1) % n
        save_state(state)
        return

    for it in cluster:
        posted.add(it["uid"])

    state["next_feed_index"] = (anchor["feed_idx"] + 1) % n
    save_posted(posted)
    save_state(state)


if __name__ == "__main__":
    main()
