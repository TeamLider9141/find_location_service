#!/bin/sh
# .env fayliga "Cheklovlar" (rate limit) bo'limini o'zbekcha izohlar bilan
# yozadi. Repo ichidan turib ishga tushiriladi:
#
#     sh scripts/env_cheklovlar.sh
#     sudo systemctl restart find-location
#
# Ikki marta ishlatsa ham dublikat qolmaydi: avval eski bo'limni va qolgan
# THROTTLE_ satrlarini olib tashlaydi, keyin yangisini yozadi. Token,
# ADMIN_IDS va DATABASE_PATH ga tegmaydi.
set -e
cd "$(dirname "$0")/.."

test -f .env || {
    echo ".env topilmadi. Avval: cp .env.example .env" >&2
    exit 1
}

cp .env .env.bak
echo "Zaxira: .env.bak"

sed '/^# ==/,$d' .env | grep -v '^THROTTLE_' > .env.tmp
mv .env.tmp .env

cat >> .env <<'ENV'

# =============================================================================
# CHEKLOVLAR (rate limit) — bitta haydovchi qanchalik tez yozishi mumkin
# =============================================================================
#
# MUAMMO: hech narsa bir odamni sekundda 50 xabar yuborishdan to'smaydi. Har
# xabar qidiruv + SQLite yozuv demak, ya'ni bitta odam butun bot sekinlashishiga
# sabab bo'ladi. Telegram ham botni 429 bilan jazolaydi.
#
# YECHIM: "token savati" (token bucket). Har haydovchining o'z savati bor.
#   - Savat to'la boshlanadi: ichida THROTTLE_BURST dona token.
#   - Har yuborilgan xabar 1 token yeydi.
#   - Vaqt o'tishi bilan token qaytadi: sekundda THROTTLE_REFILL_PER_SECOND dona.
#   - Token qolmasa xabar TASHLANADI — handler umuman ishlamaydi, bazaga
#     bormaydi. Haydovchiga "Juda tez yozayapsiz" javobi ketadi.
#
# Nega savat, oddiy "sekundda N ta" emas: odam menyu tugmalarini ketma-ket 4-5
# marta bosishi normal. Savat bu portlashni yutadi, lekin uzluksiz oqimni
# to'sadi. Oddiy limit esa normal bosishni ham bloklaydi.
#
# HAR O'ZGARTIRISHDAN KEYIN: sudo systemctl restart find-location
# Restart bo'lmasa yangi qiymat o'qilmaydi (fayl faqat ishga tushishda o'qiladi).
#
# QISQA JADVAL — batafsili har o'zgaruvchining ustida
#
# ┌─────────────────────────────────┬────────────────────────────────┬─────────────────────────┬─────────┬───────┐
# │ O'zgaruvchi                     │ Nima qiladi                    │ Oshirsang               │ Chegara │ Hozir │
# ├─────────────────────────────────┼────────────────────────────────┼─────────────────────────┼─────────┼───────┤
# │ THROTTLE_BURST                  │ ketma-ket ruxsat etilgan xabar │ yumshoqroq              │ >= 1    │ 5     │
# │ THROTTLE_REFILL_PER_SECOND      │ sekundda qaytadigan xabar      │ yumshoqroq              │ > 0     │ 1.0   │
# │ THROTTLE_WARNING_SECONDS        │ ogohlantirishlar orasi         │ kamroq ogohlantirish    │ >= 0    │ 10    │
# │ THROTTLE_IDLE_SECONDS           │ jim haydovchi qancha eslanadi  │ ko'proq xotira          │ > 0     │ 300   │
# │ THROTTLE_PRUNE_INTERVAL_SECONDS │ tozalash qadami                │ kamroq CPU, ko'p xotira │ >= 0    │ 60    │
# └─────────────────────────────────┴────────────────────────────────┴─────────────────────────┴─────────┴───────┘

# -----------------------------------------------------------------------------
# THROTTLE_BURST — savat sig'imi
# -----------------------------------------------------------------------------
# Haydovchi hech kutmasdan ketma-ket qancha xabar yuborishi mumkin.
# Oshirsang: yumshoqroq bo'ladi, tez yozadigan odam bezovta bo'lmaydi.
# Kamaytirsang: qattiqroq, lekin normal foydalanuvchi ham "juda tez" javobini
#   olishi mumkin.
# Kamida 1. 0 yoki manfiy yozsang e'tiborsiz qoldiriladi va 5 ishlatiladi —
#   aks holda 0 hammani, shu jumladan tuzatishi kerak admin'ni ham bloklardi.
THROTTLE_BURST=5

# -----------------------------------------------------------------------------
# THROTTLE_REFILL_PER_SECOND — token qaytish tezligi
# -----------------------------------------------------------------------------
# Sekundda qancha token qaytadi. Ya'ni uzoq muddatda ruxsat etilgan tezlik.
# 1.0  = sekundda 1 xabar (hozirgi holat)
# 0.5  = 2 sekundda 1 xabar (qattiqroq)
# 2.0  = sekundda 2 xabar (yumshoqroq)
# Savat THROTTLE_BURST dan oshib to'lmaydi — bir kun jim turgan haydovchi ham
#   faqat 5 token bilan qaytadi, 86400 bilan emas.
# 0 dan katta bo'lishi shart. 0 yozsang token hech qachon qaytmaydi, ya'ni
#   birinchi 5 xabardan keyin haydovchi abadiy bloklanadi. Shuning uchun 0
#   e'tiborsiz qoldiriladi.
THROTTLE_REFILL_PER_SECOND=1.0

# -----------------------------------------------------------------------------
# THROTTLE_WARNING_SECONDS — ogohlantirish orasidagi sekund
# -----------------------------------------------------------------------------
# Xabar tashlanganda haydovchiga "Juda tez yozayapsiz" javobi ketadi. Lekin HAR
# tashlangan xabarga javob berilsa, bitta flood ikkitaga aylanadi: u 50 ta
# yuboradi, bot 50 ta javob qaytaradi. Shuning uchun ogohlantirish shu sekundda
# faqat bir marta yuboriladi, qolganlari jim tashlanadi.
# 10 = odatiy. 60 = kamroq bezovta qilish. 0 = har tashlangan xabarga javob
#   (bu ataylab tanlov, xato deb hisoblanmaydi).
THROTTLE_WARNING_SECONDS=10

# -----------------------------------------------------------------------------
# THROTTLE_IDLE_SECONDS — savat qancha vaqt eslanadi
# -----------------------------------------------------------------------------
# Savatlar xotirada, har haydovchi uchun bittasi. Hech narsa o'chirmasa, bir
# marta yozgan har odam bot to'xtaguncha xotirada qoladi — bu sekin sizib
# chiqish (memory leak). Shu sekunddan uzoq jim turgan haydovchi o'chiriladi.
# O'chirilgan haydovchi keyingi xabarida to'la savat bilan qaytadi. Shu sababli
#   bu qiymat juda kichik bo'lmasligi kerak: 5 sekund qilsang, har 6 sekundda
#   xabar yuborgan odam hech qachon cheklanmaydi.
# 300 = 5 daqiqa, odatiy. 0 dan katta bo'lishi shart.
THROTTLE_IDLE_SECONDS=300

# -----------------------------------------------------------------------------
# THROTTLE_PRUNE_INTERVAL_SECONDS — tozalash qanchada bir ishlaydi
# -----------------------------------------------------------------------------
# Yuqoridagi o'chirish butun ro'yxatni aylanib chiqadi. Buni HAR xabarda qilsa,
# eng arzon yo'l eng qimmatga aylanadi (10 000 haydovchi = har xabarda 10 000
# tekshiruv). Shuning uchun tozalash taymer bilan ishlaydi.
# 60 = daqiqada bir marta, odatiy.
# Oshirsang: kamroq CPU, ko'proq xotira. Kamaytirsang: teskarisi.
# Bu sozlama cheklov qattiqligiga TA'SIR QILMAYDI — faqat xotira tozalash.
THROTTLE_PRUNE_INTERVAL_SECONDS=60
ENV

echo "Yozildi. Endi: sudo systemctl restart find-location"
