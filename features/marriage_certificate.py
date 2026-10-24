"""
Свидетельство о браке от «Дворца бракосочетаний „Марушка“».

Рисуется один раз сразу после свадьбы: имена, @ники, дата, группа,
номер свидетельства (номер брака), подпись регистратора, печать и
логотип Марушки. На выходе картинка: видна в чате, сохраняется долгим нажатием.

Шрифты лежат в assets/marriage: в контейнере своих шрифтов нет.
"""

import io
import random
import re
import unicodedata
from datetime import datetime
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ASSETS = Path(__file__).resolve().parent.parent / "assets" / "marriage"

WIDTH, HEIGHT = 2480, 1754          # пропорции A4, альбомная

# Белая бумага, тёмно-сливовые чернила и фиолетовые акценты под печать
BG_TOP = (255, 255, 255)
BG_BOTTOM = (246, 242, 252)
GLOW = (236, 226, 252)
SILVER = (46, 28, 78)               # основной текст и рамка
SILVER_DIM = (118, 102, 150)        # второстепенный текст
VIOLET = (124, 72, 214)
VIOLET_DIM = (186, 160, 230)

# Меняется при каждой смене оформления: сохранённые в Telegram картинки больше не годятся
VERSION = 4

MONTHS = ("января", "февраля", "марта", "апреля", "мая", "июня", "июля",
          "августа", "сентября", "октября", "ноября", "декабря")

MAX_NAME = 28
MAX_GROUP = 40


@lru_cache(maxsize=None)
def _font(name: str, size: int, weight: int | None = None) -> ImageFont.FreeTypeFont:
    font = ImageFont.truetype(str(ASSETS / name), size)
    if weight is not None:
        try:
            font.set_variation_by_axes([weight])
        except Exception:
            pass
    return font


@lru_cache(maxsize=None)
def _asset(name: str) -> Image.Image:
    return Image.open(ASSETS / name).convert("RGBA")


def date_ru(moment: datetime) -> str:
    return f"{moment.day} {MONTHS[moment.month - 1]} {moment.year} года"


def number_text(number: int) -> str:
    return f"№ МР-{number:06d}"


# Буквы-«двойники» из ников: малые капители (ᴍᴀᴋsɪᴍ), греческие и чероки — NFKC их не трогает
_LOOKALIKE = str.maketrans({
    "ᴀ": "a", "ʙ": "b", "ᴄ": "c", "ᴅ": "d", "ᴇ": "e", "ꜰ": "f", "ɢ": "g", "ʜ": "h", "ɪ": "i", "ᴊ": "j",
    "ᴋ": "k", "ʟ": "l", "ᴍ": "m", "ɴ": "n", "ᴏ": "o", "ᴘ": "p", "ʀ": "r", "ꜱ": "s", "ᴛ": "t", "ᴜ": "u",
    "ᴠ": "v", "ᴡ": "w", "ʏ": "y", "ᴢ": "z",
    "Α": "A", "Β": "B", "Ε": "E", "Ζ": "Z", "Η": "H", "Ι": "I", "Κ": "K", "Μ": "M", "Ν": "N", "Ο": "O",
    "Ρ": "P", "Τ": "T", "Υ": "Y", "Χ": "X", "α": "a", "ε": "e", "ι": "i", "κ": "k", "ν": "v", "ο": "o",
    "ρ": "p", "τ": "t", "υ": "u", "χ": "x",
    "Ꭺ": "A", "Ᏼ": "B", "Ꮯ": "C", "Ꭰ": "D", "Ꭼ": "E", "Ꮐ": "G", "Ꮋ": "H", "Ꭻ": "J", "Ꮶ": "K", "Ꮮ": "L",
    "Ꮇ": "M", "Ꮲ": "P", "Ꮪ": "S", "Ꭲ": "T", "Ꮩ": "V", "Ꮃ": "W", "Ꮓ": "Z",
    # «ᗪIᗩᗰOᑎᗪ» — значки канадского письма вместо латиницы
    "ᗩ": "A", "ᗷ": "B", "ᑕ": "C", "ᗪ": "D", "ᕮ": "E", "ᖴ": "F", "ᘜ": "G", "ᕼ": "H", "ᒍ": "J", "ᛕ": "K",
    "ᒪ": "L", "ᗰ": "M", "ᑎ": "N", "ᑭ": "P", "ᑫ": "Q", "ᖇ": "R", "ᔕ": "S", "ᑌ": "U", "ᐯ": "V", "ᗯ": "W",
    "᙭": "X", "ᖻ": "Y", "ᘔ": "Z",
})
# Кружки и 💎 вместо «O» в узорных названиях: «DIAM◯ND», «DIAM💎ND» (так и написан «Диамант»)
_ROUND = set("◯○⭕〇●◉◎⊙❍⚪⚫🔘💎")


def plain_letter(ch: str) -> str:
    """Буква за значком, которого нет в шрифтах: «🅾», «🇴» → «O», «ᴏ» → «o»; иначе — пусто."""
    mapped = ch.translate(_LOOKALIKE)
    if mapped != ch:
        return mapped
    try:
        name = unicodedata.name(ch)
    except ValueError:
        return ""
    found = re.search(r"\b(LATIN|CYRILLIC) (CAPITAL|SMALL) LETTER ([A-Z]+)\b", name)
    if found:
        script, case, letter = found.groups()
    elif found := re.search(r"SYMBOL LETTER ([A-Z])$", name):
        # «🇴» — REGIONAL INDICATOR SYMBOL LETTER O
        script, case, letter = "LATIN", "CAPITAL", found.group(1)
    elif found := re.search(r"LETTER SMALL CAPITAL ([A-Z])$", name):
        script, case, letter = "LATIN", "SMALL", found.group(1)
    else:
        return ""
    try:
        return unicodedata.lookup(f"{script} {case} LETTER {letter}")
    except KeyError:
        return ""


# В русском имени латинские двойники — русские буквы: «Ꭼленка» → «Еленка», а не «Eленка»
_TO_CYRILLIC = str.maketrans("ABEKMHOPCTXaeopcxyk", "АВЕКМНОРСТХаеорсхук")


def _cyrillic_words(text: str) -> str:
    def word(w: str) -> str:
        cyr = sum("\u0400" <= ch <= "\u04ff" for ch in w)
        lat = sum(ch.isascii() and ch.isalpha() for ch in w)
        return w.translate(_TO_CYRILLIC) if cyr and cyr >= lat else w
    return " ".join(word(w) for w in text.split(" "))


def clean_name(text: str | None, fallback: str = "Супруг") -> str:
    """
    Имя для шрифта: «жирные» и прочие стилизованные буквы Telegram (𝐋𝐞𝐬𝐲𝐚, ᴍᴀᴋsɪᴍ, Ꭼленка)
    превращаются в обычные, эмодзи и знаки, которых нет в шрифте, убираются.
    """
    source = unicodedata.normalize("NFKC", text or "")
    text = _cyrillic_words(source.translate(_LOOKALIKE))
    kept = []
    for ch in text:
        code = ord(ch)
        if ch.isspace():
            kept.append(" ")
        elif (ch.isalnum() and (code < 0x0250 or 0x0400 <= code <= 0x04FF)) or ch in "-'.&_":
            kept.append(ch)
    cleaned = " ".join("".join(kept).split()).strip(" -'._")
    # «STANISLAV» каллиграфией не читается — пишем как обычное имя; «ᴍᴀᴋsɪᴍ» (капители) — тоже с большой
    if len(cleaned) > 3 and cleaned.isupper() or cleaned.islower() and source.translate(_LOOKALIKE) != source:
        cleaned = cleaned.title()
    return cleaned or fallback


_NOTDEF = "\U0010fffd"


@lru_cache(maxsize=4096)
def _has_glyph(font_name: str, ch: str) -> bool:
    """Есть ли буква в шрифте: без неё Pillow рисует квадратик — тот же, что для заведомо пустого знака."""
    font = _font(font_name, 48)

    def mask(c: str) -> bytes:
        image = Image.new("L", (120, 120))
        ImageDraw.Draw(image).text((20, 20), c, font=font, fill=255)
        return image.tobytes()

    return mask(ch) != mask(_NOTDEF)


def fit_font(text: str, font_name: str) -> str:
    """Только то, что шрифт умеет нарисовать: «Ѐ» → «Е» (буква без значка), «🅾»/«🇴»/«ᴏ» → «O»,
    кружок между буквами («DIAM◯ND») → «O», узоры («꧁», «ᬊ») — убираются."""
    chars = [ch for ch in unicodedata.normalize("NFKC", text or "") if ch not in "\ufe0f\u200d"]
    out = []
    for i, ch in enumerate(chars):
        if ch in _ROUND:
            near = [c for c in chars[max(0, i - 1):i] + chars[i + 1:i + 2] if c.isalpha()]
            if near:
                out.append("O" if any(c.isupper() for c in near) else "o")
            continue
        if ch.isspace() or _has_glyph(font_name, ch):
            out.append(ch)
            continue
        for candidate in (unicodedata.normalize("NFKD", ch)[:1], plain_letter(ch)):
            if candidate and not unicodedata.combining(candidate) and _has_glyph(font_name, candidate):
                # Капитель среди заглавных — заглавная: «DIAMᴏND» → «DIAMOND»
                near = [c for c in chars[max(0, i - 1):i] + chars[i + 1:i + 2] if c.isalpha()]
                if candidate.islower() and near and all(c.isupper() for c in near):
                    candidate = candidate.upper()
                out.append(candidate)
                break
    return " ".join("".join(out).split())


def _short(text: str, limit: int) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _background() -> Image.Image:
    """Белая бумага с лёгким сиреневым свечением в центре и звёздной пылью."""
    image = Image.new("RGB", (WIDTH, HEIGHT), BG_BOTTOM)
    draw = ImageDraw.Draw(image)
    for y in range(HEIGHT):
        t = y / HEIGHT
        draw.line([(0, y), (WIDTH, y)], fill=tuple(int(BG_TOP[i] * (1 - t) + BG_BOTTOM[i] * t) for i in range(3)))

    glow = Image.new("L", (WIDTH, HEIGHT), 0)
    ImageDraw.Draw(glow).ellipse((WIDTH * 0.18, HEIGHT * 0.12, WIDTH * 0.82, HEIGHT * 0.92), fill=120)
    glow = glow.filter(ImageFilter.GaussianBlur(260))
    image.paste(Image.new("RGB", (WIDTH, HEIGHT), GLOW), (0, 0), glow)

    # Звёздная пыль — одна и та же на всех свидетельствах
    rng = random.Random(7)
    dust = ImageDraw.Draw(image)
    for _ in range(420):
        x, y = rng.randrange(WIDTH), rng.randrange(HEIGHT)
        r = rng.choice((1, 1, 1, 2))
        level = rng.randrange(200, 235)
        dust.ellipse((x - r, y - r, x + r, y + r), fill=(level, level - 14, 250))
    return image


def _sparkle(draw: ImageDraw.ImageDraw, x: float, y: float, size: float, color) -> None:
    """Четырёхлучевая звёздочка, как на логотипе."""
    thin = size * 0.18
    draw.polygon([(x, y - size), (x + thin, y - thin), (x + size, y), (x + thin, y + thin),
                  (x, y + size), (x - thin, y + thin), (x - size, y), (x - thin, y - thin)], fill=color)


def _corner(draw: ImageDraw.ImageDraw, cx: float, cy: float, sx: int, sy: int) -> None:
    """Завиток в углу рамки: две дуги-спирали и звёздочка."""
    for radius, width, color in ((120, 5, SILVER), (80, 3, SILVER_DIM), (44, 3, VIOLET)):
        box = (cx - radius, cy - radius, cx + radius, cy + radius)
        start = {(1, 1): 0, (-1, 1): 90, (-1, -1): 180, (1, -1): 270}[(sx, sy)]
        draw.arc(box, start, start + 90, fill=color, width=width)
    _sparkle(draw, cx, cy, 30, SILVER)
    for step in range(1, 4):
        _sparkle(draw, cx + sx * (150 + step * 46), cy, 8 - step, SILVER_DIM)
        _sparkle(draw, cx, cy + sy * (150 + step * 46), 8 - step, SILVER_DIM)


def _frame(draw: ImageDraw.ImageDraw) -> None:
    m = 70
    draw.rectangle((m, m, WIDTH - m, HEIGHT - m), outline=SILVER, width=6)
    draw.rectangle((m + 22, m + 22, WIDTH - m - 22, HEIGHT - m - 22), outline=VIOLET_DIM, width=3)
    draw.rectangle((m + 36, m + 36, WIDTH - m - 36, HEIGHT - m - 36), outline=SILVER_DIM, width=2)

    # Бусины по периметру, как на печати
    inner = m + 22
    for x in range(inner + 60, WIDTH - inner - 40, 56):
        for y in (inner, HEIGHT - inner):
            draw.ellipse((x - 4, y - 4, x + 4, y + 4), fill=SILVER_DIM)
    for y in range(inner + 60, HEIGHT - inner - 40, 56):
        for x in (inner, WIDTH - inner):
            draw.ellipse((x - 4, y - 4, x + 4, y + 4), fill=SILVER_DIM)

    c = m + 36
    _corner(draw, c, c, 1, 1)
    _corner(draw, WIDTH - c, c, -1, 1)
    _corner(draw, WIDTH - c, HEIGHT - c, -1, -1)
    _corner(draw, c, HEIGHT - c, 1, -1)


def _centered(draw: ImageDraw.ImageDraw, y: float, text: str, font, fill, spacing: int = 0) -> float:
    """Текст по центру; spacing — разрядка между буквами. Возвращает нижнюю границу."""
    if spacing:
        widths = [draw.textlength(ch, font=font) for ch in text]
        total = sum(widths) + spacing * (len(text) - 1)
        x = (WIDTH - total) / 2
        for ch, w in zip(text, widths):
            draw.text((x, y), ch, font=font, fill=fill)
            x += w + spacing
    else:
        draw.text((WIDTH / 2, y), text, font=font, fill=fill, anchor="ma")
    bbox = draw.textbbox((WIDTH / 2, y), text, font=font, anchor="ma")
    return bbox[3]


def _fit(draw: ImageDraw.ImageDraw, text: str, name: str, size: int, max_width: int) -> ImageFont.FreeTypeFont:
    while size > 40:
        font = _font(name, size)
        if draw.textlength(text, font=font) <= max_width:
            return font
        size -= 6
    return _font(name, size)


def _divider(draw: ImageDraw.ImageDraw, y: float, half: int = 420) -> None:
    cx = WIDTH / 2
    draw.line((cx - half, y, cx - 40, y), fill=SILVER_DIM, width=3)
    draw.line((cx + 40, y, cx + half, y), fill=SILVER_DIM, width=3)
    _sparkle(draw, cx, y, 22, SILVER)
    _sparkle(draw, cx - half - 18, y, 9, VIOLET)
    _sparkle(draw, cx + half + 18, y, 9, VIOLET)


def _paste(base: Image.Image, overlay: Image.Image, box_width: int, center: tuple[float, float],
           angle: float = 0, opacity: float = 1.0) -> None:
    img = overlay.copy()
    img.thumbnail((box_width, box_width * 4))
    if angle:
        img = img.rotate(angle, resample=Image.BICUBIC, expand=True)
    if opacity < 1:
        alpha = img.getchannel("A").point(lambda v: int(v * opacity))
        img.putalpha(alpha)
    x = int(center[0] - img.width / 2)
    y = int(center[1] - img.height / 2)
    base.paste(img, (x, y), img)


def render(number: int, name1: str, name2: str, tag1: str | None, tag2: str | None,
           since: datetime, group: str | None = None) -> Image.Image:
    image = _background()
    draw = ImageDraw.Draw(image)
    _frame(draw)

    # Логотип Марушки сверху
    _paste(image, _asset("logo.png"), 620, (WIDTH / 2, 255))

    y = 425
    y = _centered(draw, y, "ДВОРЕЦ БРАКОСОЧЕТАНИЙ «МАРУШКА»", _font("CormorantSC-Regular.ttf", 48), SILVER_DIM, spacing=6)
    y = _centered(draw, y + 18, "СВИДЕТЕЛЬСТВО", _font("CormorantSC-Bold.ttf", 108), SILVER, spacing=14)
    y = _centered(draw, y + 4, "о заключении брака", _font("CormorantGaramond.ttf", 56, 500), VIOLET)
    _divider(draw, y + 36)

    y = _centered(draw, y + 66, "Настоящим удостоверяется, что", _font("CormorantGaramond.ttf", 46, 500), SILVER_DIM)

    # Имена супругов каллиграфией
    script = "MarckScript-Regular.ttf"
    name1 = _short(fit_font(clean_name(name1, (tag1 or "").lstrip("@") or "Супруг"), script) or "Супруг", MAX_NAME)
    name2 = _short(fit_font(clean_name(name2, (tag2 or "").lstrip("@") or "Супруг"), script) or "Супруг", MAX_NAME)
    names = f"{name1}  &  {name2}"
    font = _fit(draw, names, "MarckScript-Regular.ttf", 136, WIDTH - 560)
    y = _centered(draw, y + 10, names, font, SILVER)

    tags = "   ·   ".join(fit_font(t, "CormorantGaramond.ttf") for t in (tag1, tag2) if t)
    if tags:
        y = _centered(draw, y + 12, tags, _font("CormorantGaramond.ttf", 42, 500), VIOLET)

    body = _font("CormorantGaramond.ttf", 48, 500)
    y = _centered(draw, y + 28, f"вступили в законный брак {date_ru(since)}", body, SILVER)
    # Названия групп бывают в узорах («꧁ 𝑫𝑰𝑨𝑴𝑶𝑵𝑫 ꧂»): остаются только буквы, которые есть в шрифте
    group = fit_font(group or "", "CormorantGaramond.ttf").strip(" -_.·")
    if group:
        y = _centered(draw, y + 8, f"в чате «{_short(group, MAX_GROUP)}»", body, SILVER_DIM)
    y = _centered(draw, y + 8, "и отныне считаются супругами во всех чатах Марушки.", body, SILVER_DIM)

    # Низ: подпись регистратора слева, номер по центру, печать справа
    bottom = HEIGHT - 215
    left_x = 560
    draw.text((left_x, bottom - 22), "Марушка", font=_font("MarckScript-Regular.ttf", 88), fill=SILVER, anchor="ms")
    draw.line((left_x - 230, bottom, left_x + 230, bottom), fill=SILVER_DIM, width=3)
    draw.text((left_x, bottom + 20), "Регистратор Дворца", font=_font("CormorantSC-Regular.ttf", 40), fill=SILVER_DIM, anchor="ma")

    small = _font("CormorantSC-Regular.ttf", 42)
    draw.text((WIDTH / 2, bottom - 4), number_text(number), font=_font("CormorantSC-Bold.ttf", 56), fill=SILVER, anchor="ms")
    draw.text((WIDTH / 2, bottom + 20), f"выдано {since:%d.%m.%Y}", font=small, fill=SILVER_DIM, anchor="ma")

    _paste(image, _asset("seal.png"), 340, (WIDTH - 620, bottom - 60), angle=-12, opacity=0.92)
    return image


def _from(cert: dict) -> Image.Image:
    return render(int(cert["number"]), cert["name1"], cert["name2"], cert.get("tag1"), cert.get("tag2"),
                  datetime.fromisoformat(cert["since"]), cert.get("group"))


def jpeg_bytes(cert: dict) -> bytes:
    """Свидетельство картинкой — чтобы было видно прямо в чате."""
    out = io.BytesIO()
    _from(cert).save(out, "JPEG", quality=90, optimize=True)
    return out.getvalue()


