#!/bin/sh
# Soatlik zaxira: baza O'ZGARGAN bo'lsagina nusxa oladi va nusxa faylini
# super adminlarga Telegram orqali yuboradi. O'zgarmagan bo'lsa jim chiqadi —
# bir xil nusxadan 24 ta saqlashning ma'nosi yo'q.
#
# O'rnatish (serverda, bir marta):
#     crontab -e
#     0 * * * * /bin/sh /home/ubuntu/find_location_service/scripts/backup_bazani.sh >> /home/ubuntu/backups/zaxira.log 2>&1
#
# Nusxalar $HOME/backups/places-soatlik-<soat>.sqlite3 nomida turadi:
# 24 ta o'rin, har kuni o'z soati ustiga yoziladi. Kunlik 03:00 dagi arxiv
# cron'i bunga tegmaydi — u alohida ishlayveradi.
set -e
cd "$(dirname "$0")/.."

BAZA="data/find_location.sqlite3"
PAPKA="$HOME/backups"
IZ="$PAPKA/.oxirgi_hash"

test -f "$BAZA" || { echo "$(date '+%F %T') baza topilmadi: $BAZA"; exit 1; }
test -f .env || { echo "$(date '+%F %T') .env topilmadi"; exit 1; }
mkdir -p "$PAPKA"

# Token va super adminlar serverdagi .env dan o'qiladi — skriptda sir yo'q.
TOKEN=$(grep '^TELEGRAM_BOT_TOKEN=' .env | cut -d= -f2-)
ADMINLAR=$(grep '^SUPER_ADMIN_IDS=' .env | cut -d= -f2- | tr ',' ' ')

hozirgi=$(sha256sum "$BAZA" | cut -d' ' -f1)
oldingi=$(cat "$IZ" 2>/dev/null || true)

if [ "$hozirgi" = "$oldingi" ]; then
    # Hech narsa o'zgarmagan — nusxa ham, xabar ham kerak emas.
    exit 0
fi

nusxa="$PAPKA/places-soatlik-$(date +%H).sqlite3"
# .backup — bot yozayotgan paytda ham butun nusxa oladigan xavfsiz yo'l;
# oddiy cp yozuv o'rtasida buzuq fayl qoldirishi mumkin.
sqlite3 "$BAZA" ".backup '$nusxa'"
echo "$hozirgi" > "$IZ"

joylar=$(sqlite3 "$nusxa" "SELECT COUNT(*) FROM places;")
izoh="🗄 Zaxira $(date '+%F %H:%M'). Joylar: $joylar ta."

for admin in $ADMINLAR; do
    curl -s -F "chat_id=$admin" -F "document=@$nusxa" -F "caption=$izoh" \
        "https://api.telegram.org/bot$TOKEN/sendDocument" > /dev/null \
        || echo "$(date '+%F %T') $admin ga yuborilmadi"
done

echo "$(date '+%F %T') zaxira olindi: $nusxa (joylar: $joylar ta)"
