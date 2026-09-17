# RSS → Telegram avtomatik bot

Bu bot berilgan RSS manba(lar)dan yangi xabarlarni o'qib, sizning Telegram kanalingizga
avtomatik joylab boradi. GitHub Actions orqali ishlaydi — kompyuteringiz yoqilgan
bo'lishi shart emas.

## 1-qadam: Telegram bot yaratish

1. Telegram'da **@BotFather** ga yozing.
2. `/newbot` buyrug'ini yuboring, botga nom va username bering.
3. BotFather sizga **token** beradi (masalan: `123456:ABC-DEF...`). Uni saqlab qo'ying.

## 2-qadam: Botni kanalga admin qilish

1. O'z Telegram kanalingizga o'ting → **Administrators** → **Add Admin**.
2. Yaratgan botingizni qidirib toping va admin qilib qo'shing (kamida "Post Messages" huquqi bilan).
3. Kanal **chat ID**sini aniqlang:
   - Agar kanal ochiq (public) bo'lsa va usernamesi bor bo'lsa — shunchaki `@kanal_username` ishlatavering.
   - Agar yopiq (private) kanal bo'lsa, chat ID raqamini olish uchun botni admin qilgandan so'ng
     kanalga bitta xabar yuboring, so'ng brauzerda quyidagi manzilni oching:
     `https://api.telegram.org/bot<TOKEN>/getUpdates` — javobda `"chat":{"id": -100...}` qatorini topasiz.

## 3-qadam: RSS manba havolasini topish

`rss_to_telegram.py` faylini oching va `FEEDS` ro'yxatiga o'zingiz kuzatmoqchi bo'lgan
saytning RSS havolasini qo'shing. Ko'p yangilik saytlarida RSS odatda quyidagi
ko'rinishlarda bo'ladi — saytning o'zidan yoki qidiruv orqali tekshirib ko'ring:

```
https://sayt.uz/rss
https://sayt.uz/rss.xml
https://sayt.uz/feed
```

Masalan:

```python
FEEDS = [
    "https://kun.uz/uz/rss",
    "https://www.gazeta.uz/uz/rss/",
]
```

> Eslatma: ba'zi saytlar RSS taqdim etmaydi yoki himoyalangan bo'lishi mumkin — shunday holatda
> boshqa manba tanlang yoki menga sayt nomini ayting, birga qidiramiz.

### Chet el manbalarni o'zbekchaga tarjima qilib joylash

`rss_to_telegram.py` faylining tepasida `TRANSLATE_MODE` bor:

- `"google"` (standart) — bepul, avtomatik tarjima. Qo'shimcha sozlash shart emas.
- `"claude"` — sifatliroq tarjima, lekin Anthropic API kaliti kerak (agar mavjud bo'lsa,
  uni `ANTHROPIC_API_KEY` nomi bilan GitHub Secrets'ga qo'shing — 5-qadamga qarang).
- `"off"` — tarjima qilinmaydi, xabar asl tilida joylanadi.

`FEEDS` ro'yxatiga chet el saytining (masalan Reuters, BBC, TASS va h.k.) RSS havolasini
qo'shsangiz bo'ldi — qolganini skript o'zi qiladi: yangilikni oladi, o'zbekchaga o'giradi,
so'ng kanalga joylaydi.

## 4-qadam: GitHub'ga yuklash

1. [github.com](https://github.com) da yangi **repository** yarating (masalan `telegram-news-bot`), **private** qilib qo'yishingiz mumkin.
2. Shu papkadagi barcha fayllarni o'sha repoga yuklang (GitHub saytida "Add file" → "Upload files" orqali eng oson).

## 5-qadam: Maxfiy kalitlarni (Secrets) qo'shish

1. Repo ichida: **Settings** → **Secrets and variables** → **Actions** → **New repository secret**.
2. Quyidagi secret'larni qo'shing:
   - `TELEGRAM_BOT_TOKEN` — BotFather bergan token
   - `TELEGRAM_CHAT_ID` — kanal username (`@kanal_username`) yoki raqamli ID
   - `ANTHROPIC_API_KEY` — **faqat** `TRANSLATE_MODE = "claude"` tanlasangiz kerak (Google tarjima uchun shart emas)

## 6-qadam: Ishga tushirish

- Workflow avtomatik ravishda **har 30 daqiqada** ishga tushadi (`.github/workflows/post.yml` da sozlangan).
- Vaqtni o'zgartirish uchun shu fayldagi `cron` qatorini tahrirlang (masalan `*/10 * * * *` — har 10 daqiqada).
- Qo'lda sinab ko'rish uchun: repo'dagi **Actions** bo'limiga o'ting → workflow'ni tanlang → **Run workflow**.

## Qanday ishlaydi

- Har safar ishga tushganda, skript RSS manbalardan xabarlarni o'qiydi.
- `posted.json` faylida qaysi xabarlar allaqachon joylanganini eslab qoladi (takror bo'lmasligi uchun).
- Faqat yangi xabarlarni Telegram kanalga yuboradi va `posted.json`ni yangilab, GitHub'ga qaytarib commit qiladi.
- Bitta ishga tushishda ko'pi bilan 5 ta xabar yuboradi (spam bo'lmasligi uchun) — buni `MAX_POSTS_PER_RUN` orqali o'zgartirishingiz mumkin.

## Yordam kerakmi?

Agar RSS havolasini topa olmasangiz yoki xatolik chiqsa, sayt nomini va xato matnini
menga yuboring — birga hal qilamiz.
