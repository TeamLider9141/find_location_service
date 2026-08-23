# Umumiy manzillar bazasi — dizayn

**Sana:** 2026-08-23
**Holat:** tasdiqlangan, amalga oshirish kutilmoqda

## Muammo

Bot hozir OSM (Nominatim + Overpass) ustida qurilgan: foydalanuvchi manzil yozadi, bot uni
OpenStreetMap'dan qidiradi. Saqlangan manzillar esa shaxsiy — har kim faqat o'zi
saqlaganini ko'radi.

Haqiqiy ehtiyoj boshqacha. Bot Rossiyada ishlaydigan haydovchilar uchun, ular yurgan
joylarning ko'pi OSM'da yo umuman yo'q, yo noto'g'ri belgilangan: yo'l bo'yidagi oshxona,
nomsiz usta, kartada ko'rinmaydigan parking. Bu joylarni faqat u yerga borgan haydovchi
biladi.

Shuning uchun ma'lumot manbai teskari bo'ladi: **bazada faqat foydalanuvchilar qo'shgan
manzillar bo'ladi, va bu baza hamma uchun umumiy.** Haydovchi biror joyga birinchi marta
borganda uni botga qo'shadi — nomi, kategoriyasi, va lokatsiya tashlash orqali
koordinatasi. Keyingi safar o'sha haydovchi yoki butunlay boshqa haydovchi kategoriya va
nom bo'yicha qidirib, o'sha lokatsiyani oladi.

## Qarorlar

Dizayn muhokamasida qabul qilingan qarorlar:

| Savol | Qaror |
|---|---|
| OSM provayderlari | Butunlay olib tashlanadi. Yagona manba — foydalanuvchilar. |
| Egalik | Qidiruv hamma uchun ochiq; tahrirlash va o'chirish faqat qo'shgan odamga. |
| Qidiruv yo'li | Ikkalasi ham: nom bo'yicha matn qidiruv **va** kategoriya bo'yicha ro'yxat. |
| "Atrofda" tugmasi | Qoladi, lekin OSM o'rniga bazadan masofa bo'yicha topadi. |
| Dublikat | Ogohlantiriladi, lekin bloklanmaydi — foydalanuvchi qaror qiladi. |
| `address` maydoni | `note` ga aylanadi: ixtiyoriy erkin matn izoh. |

## Arxitektura

Clean architecture qatlamlari o'z joyida qoladi. O'zgarish — domenning markazi.

OSM ketishi bilan `app/domain/entities/place.py` nomi bo'shaydi. Umumiy yozuv endi
haqiqiy domen obyekti: "kimningdir saqlangan nusxasi" emas, balki bazadagi joyning o'zi.
Shuning uchun `SavedPlace` → `Place`, `SavedPlaceRepository` → `PlaceRepository`.

### Domen

```python
@dataclass(frozen=True)
class Place:
    id: int
    added_by_user_id: int      # faqat tahrir/o'chirish huquqi uchun
    name: str
    category: PlaceCategory
    coordinates: Coordinates
    note: str                  # ixtiyoriy, bo'sh bo'lishi mumkin
    created_at: datetime
```

`source` va `source_id` maydonlari o'chadi — endi manba doim foydalanuvchi.

`PlaceCategory` va `Coordinates` (`distance_to` bilan birga) o'zgarishsiz qoladi.

### Baza sxemasi

```sql
CREATE TABLE places (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    added_by_user_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    name_normalized TEXT NOT NULL,
    category TEXT NOT NULL,
    latitude REAL NOT NULL,
    longitude REAL NOT NULL,
    note TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_places_category ON places(category);
CREATE INDEX idx_places_name_normalized ON places(name_normalized);
CREATE INDEX idx_places_author ON places(added_by_user_id);
```

`name_normalized` — qidiruvning kaliti. Haydovchi `gazprom` deb yozadi, bazada esa
`Газпром` turadi. Mavjud `app/application/query_normalization.py` dagi lotin→kirill
translit kodi OSM bilan birga o'chmaydi: u `app/application/name_normalization.py` ga
ko'chadi va yozuvda ham, qidiruvda ham bir xil qo'llaniladi (kichik harf + translit).

Eski `saved_places` jadvali tegilmaydi — yangi jadval boshqa nomda, shuning uchun
`data/find_location.sqlite3` fayli qolaveradi.

### Repository interfeysi

```python
class PlaceRepository(Protocol):
    def add(self, place: Place) -> Place: ...
    def get(self, place_id: int) -> Place | None: ...
    def search(
        self,
        name: str | None = None,
        category: PlaceCategory | None = None,
        limit: int = 10,
    ) -> list[Place]: ...
    def nearby(
        self,
        coordinates: Coordinates,
        radius_meters: int,
        category: PlaceCategory | None = None,
        limit: int = 10,
    ) -> list[Place]: ...
    def list_by_author(self, user_id: int) -> list[Place]: ...
    def find_duplicates(
        self,
        name: str,
        coordinates: Coordinates,
        radius_meters: int = 200,
    ) -> list[Place]: ...
    def update(
        self,
        place_id: int,
        user_id: int,
        name: str | None = None,
        category: PlaceCategory | None = None,
        note: str | None = None,
    ) -> Place | None: ...
    def delete(self, place_id: int, user_id: int) -> bool: ...
```

`update` da `None` qiymat "tegilmasin" degani, bo'sh satr esa "tozalansin" — shuning uchun
`note=""` izohni o'chiradi, `note=None` esa uni o'z holida qoldiradi.

Diqqat: `get`, `search`, `nearby` da `user_id` **yo'q** — bu umumiy o'qish. `update` va
`delete` da esa `user_id` bor va u huquq tekshiruvi sifatida ishlaydi: begona yozuvga
`update` `None`, `delete` `False` qaytaradi.

`nearby` ikki bosqichda ishlaydi: SQL'da bounding-box bilan qo'pol filtr (indeksdan
foydalanadi), so'ng Python'da `Coordinates.distance_to` bilan aniq masofa hisoblanib
saralanadi. Bu SQLite'da trigonometriyasiz ishlaydigan eng sodda usul.

`find_duplicates` "o'xshashlik"ni aniq belgilaydi: ikkita yozuv dublikat deb hisoblanadi,
agar ularning `name_normalized` qiymatlari teng bo'lsa **yoki** biri ikkinchisining ichida
substring sifatida uchrasa, **va** ular orasidagi masofa `radius_meters` dan kichik bo'lsa.
Fuzzy taqqoslash (Levenshtein va shunga o'xshash) ishlatilmaydi — imlo xatosi bo'lgan
dublikatni tutmaydi, lekin natijasi oldindan aytiladigan va tushuntirsa bo'ladigan bo'ladi.

## Bot oqimlari

### Asosiy menyu

```
[ 🔎 Qidirish ]
[ 📍 Yaqin atrofda ]    [ ➕ Joy qo'shish ]
[ 📒 Mening joylarim ]  [ ⚙️ Sozlamalar ]
```

### Qo'shish oqimi

```
➕ Joy qo'shish
  → "Joy nomini yozing"                     → matn
  → "Kategoriyani tanlang"                  → 6 ta inline tugma
  → "Lokatsiyani yuboring"                  → location / venue / xarita linki / "41.3, 69.2"
  → dublikat tekshiruvi ─┬─ topilmadi → davom
                         └─ topildi   → "200 m ichida 'Газпром' (⛽) bor.
                                          Baribir qo'shaymi?" [Ha] [Yo'q]
  → "Izoh qo'shasizmi? Masalan: M5, 120-km, kechasi ochiq — yoki /skip"
  → ✅ saqlandi
```

Har qadamda `/cancel` oqimni to'xtatadi. Lokatsiya qabuli uchun mavjud
`app/presentation/telegram/location_input.py` o'zgarishsiz qayta ishlatiladi — u URL,
koordinata jufti, venue va location'ni allaqachon tushunadi.

### Qidiruv oqimi

```
🔎 Qidirish → "Nom yozing yoki kategoriya tanlang" + 6 kategoriya tugmasi
   ├ matn "gazprom"  → name_normalized LIKE → natijalar, har birida kategoriya belgisi
   └ ⛽ tugmasi      → o'sha kategoriyadagi hammasi

📍 Yaqin atrofda → "Lokatsiyangizni yuboring"
   → radius ichidagi joylar, masofa bo'yicha saralangan
   → kategoriya bo'yicha filtr tugmalari
```

Natijadan bittasini bosish → to'liq karta: nom, kategoriya, izoh, koordinata, Google Maps
linki. Bot qo'shimcha ravishda Telegram lokatsiyasini ham yuboradi, shunda haydovchi uni
to'g'ridan-to'g'ri navigatorga uzata oladi.

Hech qanday oqim ichida bo'lmagan paytda yuborilgan oddiy matn ham nom bo'yicha qidiruv
deb qabul qilinadi — ya'ni "🔎 Qidirish" tugmasini bosish shart emas, shunchaki nom yozsa
bo'ladi. Bu hozirgi botning `F.text` catch-all xatti-harakati bilan bir xil, shuning uchun
foydalanuvchi uchun yangi odat kerak emas. Amalda bu handler eng oxirgi router'da turishi
kerak, aks holda u boshqa handler'larni bosib ketadi.

Radius va natijalar soni `UserSettings` dan keladi — sozlamalar featuresi o'zgarishsiz
ishlashda davom etadi.

### Holat boshqaruvi

Hozirgi `InMemoryAddLocationFlowStore` string rejimlarni saqlaydi (`"add"`, `"search"`,
`"nearby:fuel"`). To'rt qadamli qo'shish oqimi uchun bu yetmaydi.

Uning o'rniga aiogram'ning o'z FSM'i: `StatesGroup` + `FSMContext`. U qadam ma'lumotini
o'zi olib yuradi, va keyinchalik bir qatorda Redis backend'ga ko'chadi.

**Yon foyda:** callback'lar endi haqiqiy `place_id` ni olib yuradi (`place:1042`), indeks
emas. Bu auditda topilgan bug'ni bepul yopadi — ilgari foydalanuvchi kategoriya tanlash
oralig'ida yangi qidiruv qilsa, `confirm_save:0:fuel` butunlay boshqa joyni saqlar edi.
`InMemoryLocationSelectionStore` butunlay o'chadi.

## Xatolar

Tashqi API yo'qolishi bilan butun bir xato sinfi ketadi: 429 rate limit, 504 Overpass,
timeout, `KeyError: osm_type`. Qoladigan uchtasi:

| Holat | Javob |
|---|---|
| SQLite xatosi | "Baza bilan muammo. Birozdan so'ng urinib ko'ring." + log |
| Begona joyni tahrir/o'chirish | "Bu joyni faqat uni qo'shgan foydalanuvchi o'zgartira oladi." |
| Noto'g'ri kirish | Qadam qayta so'raladi, oqim buzilmaydi |

`app/presentation/telegram/errors.py` dagi `answerable_message` va `user_id_of` guardlari
o'z joyida qoladi — 48 soatlik eskirgan xabar muammosi va anonim admin holati yo'qolgani
yo'q.

## Config

`nominatim_base_url`, `overpass_base_url`, `nominatim_user_agent` o'chadi. `Settings` da
`telegram_bot_token` va `database_path` qoladi. `.env.example` mos ravishda qisqaradi.

## Testlar

Hozirgi suite 1864 satr, shundan taxminan 1300 satri OSM'ga bog'liq va o'chadi. O'rniga
kelganlari kuchliroq: mock HTTP transport o'rniga haqiqiy SQLite (`tmp_path`) ustida
test yoziladi.

**Repository (SQLite, `tmp_path`):**
- `search` nom bo'yicha kirill va lotin ikkalasida ishlashi
- `search` kategoriya filtri
- `nearby` bounding-box + masofa saralashi
- `find_duplicates` radius chegarasi (199 m topadi, 201 m topmaydi)
- `delete` begona `user_id` bilan `False` qaytarishi
- `update` begona `user_id` bilan `None` qaytarishi

**Use case (in-memory fake repo):** mavjud
`app/infrastructure/repositories/in_memory_saved_places.py` qayta ishlatiladi.

**Handler (mavjud fake Message / CallbackQuery uslubida):**
- to'liq qo'shish oqimi, to'rt qadam
- `/cancel` har qadamda
- dublikat ogohlantirishning Ha va Yo'q ikkala shoxi
- begona joyni o'chirishga urinish

**O'zgarishsiz qoladi:** `test_coordinates`, `test_settings`, `test_settings_handlers`,
`test_start_handlers`, `test_telegram_keyboards`.

## Fayl xaritasi

**Yangi:**

| Fayl | Taxminiy hajm |
|---|---|
| `app/domain/entities/place.py` (`Place`) — eski OSM `Place` o'rniga qayta yoziladi | 20 |
| `app/domain/interfaces/places.py` (`PlaceRepository`) — eski `PlacesProvider` o'rniga qayta yoziladi | 40 |
| `app/application/name_normalization.py` | 40 |
| `app/application/use_cases/places.py` | 90 |
| `app/infrastructure/database/sqlite_places.py` | 180 |
| `app/presentation/telegram/handlers/add_place.py` | 150 |
| `app/presentation/telegram/handlers/find_place.py` | 130 |
| `app/presentation/telegram/handlers/my_places.py` | 120 |

Uchta handler 516 satrli `handlers/saved_places.py` ning o'rnini bosadi.

**Butunlay o'chadi:** `app/infrastructure/providers/osm/` (butun paket),
`app/application/use_cases/search_location.py`, `.../nearby_places.py`,
`app/application/query_normalization.py` (mazmuni `name_normalization.py` ga ko'chgach),
`app/domain/interfaces/geocoding.py`, `app/domain/interfaces/saved_places.py`,
`app/domain/entities/location.py`, `app/domain/entities/saved_place.py`,
`app/infrastructure/database/sqlite_saved_places.py`,
`app/presentation/telegram/handlers/search.py`, `.../location.py`, `.../saved_places.py`,
`app/presentation/telegram/selection_store.py` dagi `InMemoryLocationSelectionStore` va
`InMemoryAddLocationFlowStore` (`InMemoryUserSettingsStore` esa qoladi),
`tests/providers/`, `tests/integration/`.

**Qoladi:** `Coordinates` + `distance_to`, `PlaceCategory`, `UserSettings` va sozlamalar
featuresi, `errors.py`, `location_input.py`, formatter va keyboard uslubi.

`tests/unit/test_telegram_formatters.py` va `tests/unit/test_handler_resilience.py`
qisman qayta yoziladi: OSM va eski handler'larga tegishli testlari o'chadi, `Place`
formatlash va yangi guard testlari o'rniga keladi.

## Bosqichlar

Har bosqich oxirida suite yashil bo'ladi va alohida commit qilinadi.

| # | Bosqich | Natija |
|---|---|---|
| 1 | Domen + repo: `Place`, `PlaceRepository`, `sqlite_places.py`, normalization | Yangi qatlam testlari o'tadi, eski kod tegilmagan |
| 2 | Use case'lar + in-memory fake | Application qatlami tayyor |
| 3 | Handler'lar: `add_place` / `find_place` / `my_places` + FSM + keyboard'lar | Yangi bot ishlaydi |
| 4 | Wiring: `bot.py`, `main.py`, `settings.py` yangi qatlamga o'tadi | Eski handler'lar router'dan chiqadi |
| 5 | O'chirish: OSM paketi, eski use case / entity / handler / testlar, README | Suite yashil, o'lik kod yo'q |

## Doiradan tashqarida

Bu dizayn quyidagilarni qamramaydi — auditda topilgan, keyingi ishga qoldirilgan:

- SQLite sync chaqiruvlari async handler'dan (event loop bloklanadi) → `aiosqlite`
- Redis FSM backend (hozircha xotira)
- Spam/moderatsiya: admin roli, joyni "noto'g'ri" deb belgilash
- Reyting yoki tasdiqlash ("men ham shu yerda bo'ldim")
- Til aralashmasi: `format_search_results` sarlavhasi hali ruscha
- `set_my_commands` / `/help`
