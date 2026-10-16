"""
Картинки для игр в чате: доска шашек, поля морского боя, камень-ножницы-бумага,
монетка и обложки столов. Рисуются на лету (Pillow) — в JPEG для Telegram.

Иконки — Microsoft Fluent Emoji 3D (MIT), шрифт — Rubik (OFL), см. assets/table/LICENSE.md.
"""

import io
import math
import random
import re
import unicodedata
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent.parent / "assets"
FONT = ROOT / "fonts" / "Rubik-Bold.ttf"

GOLD = (246, 196, 82)
CREAM = (250, 240, 214)
INK = (40, 22, 12)


@lru_cache(maxsize=32)
def font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONT), size)


@lru_cache(maxsize=64)
def icon(name: str, size: int) -> Image.Image:
    im = Image.open(ROOT / "table" / f"{name}.png").convert("RGBA")
    return im.resize((size, size), Image.LANCZOS)


def to_jpeg(im: Image.Image) -> bytes:
    out = io.BytesIO()
    im.convert("RGB").save(out, "JPEG", quality=88, optimize=True)
    return out.getvalue()


def gradient(size: tuple[int, int], top: tuple, bottom: tuple) -> Image.Image:
    w, h = size
    base = Image.new("RGB", (1, h))
    for y in range(h):
        t = y / max(1, h - 1)
        base.putpixel((0, y), tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3)))
    return base.resize((w, h))


def radial(size: int, inner: tuple, outer: tuple) -> Image.Image:
    im = Image.new("RGB", (size, size))
    px = im.load()
    c = (size - 1) / 2
    for y in range(size):
        for x in range(size):
            t = min(1.0, math.hypot(x - c, y - c) / c)
            px[x, y] = tuple(int(inner[i] + (outer[i] - inner[i]) * t) for i in range(3))
    return im


# Что умеет шрифт: латиница, кириллица, цифры, обычная пунктуация
_DRAWABLE = re.compile(r"[^\u0020-\u024F\u0400-\u04FF\u2010-\u2027\u2116]")


def drawable(text: str) -> str:
    """Ник для картинки: «𝑳𝒆𝒔𝒚𝒂 🦋» → «Lesya». Эмодзи и узоры шрифт рисует квадратиками — убираем."""
    text = unicodedata.normalize("NFKC", text)
    text = "".join(ch for ch in text if unicodedata.category(ch) not in ("Mn", "Me", "Cf") and not 0xFE00 <= ord(ch) <= 0xFE0F)
    text = " ".join(_DRAWABLE.sub(" ", text).split())
    return text or "Игрок"


def fit_text(draw: ImageDraw.ImageDraw, text: str, size: int, width: int) -> tuple[str, ImageFont.FreeTypeFont]:
    text = drawable(text)
    f = font(size)
    while draw.textlength(text, font=f) > width and size > 14:
        size -= 2
        f = font(size)
    while draw.textlength(text, font=f) > width and len(text) > 2:
        text = text[:-2] + "…"
    return text, f


def shadow_text(draw, xy, text, f, fill=CREAM, anchor="mm", shadow=(0, 0, 0)):
    x, y = xy
    draw.text((x + 2, y + 3), text, font=f, fill=shadow, anchor=anchor)
    draw.text((x, y), text, font=f, fill=fill, anchor=anchor)


def paste_shadowed(canvas: Image.Image, sprite: Image.Image, xy: tuple[int, int], blur: int = 8, offset: int = 6) -> None:
    alpha = sprite.getchannel("A")
    shade = Image.new("RGBA", sprite.size, (0, 0, 0, 0))
    shade.putalpha(alpha.point(lambda a: int(a * 0.45)))
    shade = shade.filter(ImageFilter.GaussianBlur(blur))
    canvas.alpha_composite(shade, (xy[0] + offset // 2, xy[1] + offset))
    canvas.alpha_composite(sprite, xy)


# =========================================================
# ШАШКИ
# =========================================================

CELL = 84
BORDER = 44
HEADER = 96


@lru_cache(maxsize=1)
def _wood_board() -> Image.Image:
    rnd = random.Random(42)
    size = CELL * 8 + BORDER * 2
    frame = gradient((size, size), (122, 66, 30), (78, 38, 16)).convert("RGBA")
    streaks = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    sd = ImageDraw.Draw(streaks)
    for _ in range(220):
        y = rnd.randrange(size)
        sd.line([(0, y), (size, y + rnd.randint(-6, 6))], fill=(50, 22, 6, rnd.randint(14, 34)), width=1)
    frame.alpha_composite(streaks)
    board = Image.new("RGBA", (CELL * 8, CELL * 8))
    d = ImageDraw.Draw(board)
    light, dark = (238, 212, 168), (126, 76, 42)
    for r in range(8):
        for c in range(8):
            base = dark if (r + c) % 2 else light
            cell = gradient((CELL, CELL), tuple(min(255, v + 10) for v in base), tuple(max(0, v - 10) for v in base))
            board.paste(cell, (c * CELL, r * CELL))
    grain = Image.new("RGBA", board.size, (0, 0, 0, 0))
    gd = ImageDraw.Draw(grain)
    for _ in range(140):
        y = rnd.randrange(CELL * 8)
        gd.line([(0, y), (CELL * 8, y + rnd.randint(-4, 4))], fill=(70, 35, 10, rnd.randint(6, 16)), width=1)
    board.alpha_composite(grain)
    frame.alpha_composite(board, (BORDER, BORDER))
    d = ImageDraw.Draw(frame)
    d.rectangle([BORDER - 4, BORDER - 4, BORDER + CELL * 8 + 3, BORDER + CELL * 8 + 3], outline=GOLD, width=3)
    f = font(22)
    for i in range(8):
        mid = BORDER + i * CELL + CELL // 2
        letter = "abcdefgh"[i]
        num = str(8 - i)
        for y in (BORDER // 2, size - BORDER // 2):
            d.text((mid, y), letter, font=f, fill=(250, 226, 170), anchor="mm")
        for x in (BORDER // 2, size - BORDER // 2):
            d.text((x, mid), num, font=f, fill=(250, 226, 170), anchor="mm")
    return frame


@lru_cache(maxsize=4)
def _piece(color: str, king: bool) -> Image.Image:
    size = CELL - 14
    big = size * 3
    if color == "w":
        disc = radial(big, (255, 250, 240), (205, 190, 165))
        rim, ring = (170, 150, 120), (225, 212, 190)
    else:
        disc = radial(big, (95, 70, 60), (25, 15, 12))
        rim, ring = (10, 6, 5), (70, 50, 42)
    mask = Image.new("L", (big, big), 0)
    ImageDraw.Draw(mask).ellipse([0, 0, big - 1, big - 1], fill=255)
    im = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    im.paste(disc, (0, 0), mask)
    d = ImageDraw.Draw(im)
    d.ellipse([0, 0, big - 1, big - 1], outline=rim, width=9)
    d.ellipse([big * 0.2, big * 0.2, big * 0.8, big * 0.8], outline=ring, width=8)
    d.ellipse([big * 0.32, big * 0.32, big * 0.68, big * 0.68], outline=ring, width=5)
    im = im.resize((size, size), Image.LANCZOS)
    if king:
        crown = icon("crown", int(size * 0.62))
        im.alpha_composite(crown, ((size - crown.width) // 2, (size - crown.height) // 2 - 2))
    return im


def checkers_image(board: list[str], names: tuple[str, str], counts: tuple[int, int], turn: str | None,
                   selected: int | None = None, targets=(), captured=(), last=None, result: str | None = None) -> bytes:
    """names/counts — (белые, чёрные); turn — 'w'/'b' или None, если партия окончена."""
    wood = _wood_board()
    size = wood.width
    im = Image.new("RGBA", (size, size + HEADER), (40, 20, 10, 255))
    im.paste(gradient((size, HEADER), (64, 32, 14), (36, 18, 8)), (0, 0))
    im.alpha_composite(wood, (0, HEADER))
    d = ImageDraw.Draw(im)

    # Шапка: белые слева, чёрные справа, ход — золотой рамкой
    for i, side in enumerate(("w", "b")):
        x0 = 16 if i == 0 else size // 2 + 8
        box = [x0, 14, x0 + size // 2 - 24, HEADER - 14]
        on = turn == side
        d.rounded_rectangle(box, radius=16, fill=(90, 48, 20) if on else (52, 28, 12), outline=GOLD if on else (110, 70, 40), width=3 if on else 1)
        piece = _piece(side, False).resize((46, 46), Image.LANCZOS)
        im.alpha_composite(piece, (x0 + 12, (HEADER - 46) // 2))
        name, f = fit_text(d, names[i], 26, size // 2 - 150)
        d.text((x0 + 70, HEADER // 2 - 12), name, font=f, fill=CREAM, anchor="lm")
        d.text((x0 + 70, HEADER // 2 + 16), f"шашек: {counts[i]}", font=font(19), fill=(220, 190, 140), anchor="lm")

    def cell_box(pos: int) -> tuple[int, int]:
        r, c = divmod(pos, 8)
        return BORDER + c * CELL, HEADER + BORDER + r * CELL

    overlay = Image.new("RGBA", im.size, (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    if last:
        for pos in last:
            x, y = cell_box(pos)
            od.rectangle([x, y, x + CELL - 1, y + CELL - 1], fill=(255, 210, 80, 70))
    im.alpha_composite(overlay)

    for pos, piece in enumerate(board):
        if not piece:
            continue
        x, y = cell_box(pos)
        sprite = _piece(piece.lower(), piece.isupper())
        paste_shadowed(im, sprite, (x + 7, y + 7), blur=4, offset=4)
        if pos in captured:
            boom = icon("boom", CELL - 20)
            im.alpha_composite(boom, (x + 10, y + 10))

    d = ImageDraw.Draw(im)
    if selected is not None:
        x, y = cell_box(selected)
        d.ellipse([x + 3, y + 3, x + CELL - 4, y + CELL - 4], outline=(255, 214, 60), width=5)
    for pos in targets:
        x, y = cell_box(pos)
        cx, cy = x + CELL // 2, y + CELL // 2
        d.ellipse([cx - 13, cy - 13, cx + 13, cy + 13], fill=(90, 220, 120), outline=(20, 90, 40), width=3)

    if result:
        veil = Image.new("RGBA", im.size, (0, 0, 0, 120))
        im.alpha_composite(veil)
        d = ImageDraw.Draw(im)
        trophy = icon("trophy" if "Ничья" not in result else "handshake", 180)
        paste_shadowed(im, trophy, ((size - 180) // 2, HEADER + size // 2 - 150))
        text, f = fit_text(d, result, 46, size - 60)
        shadow_text(d, (size // 2, HEADER + size // 2 + 70), text, f, fill=GOLD)
    return to_jpeg(im)


# =========================================================
# МОРСКОЙ БОЙ
# =========================================================

SEA_CELL = 52
SEA_PAD = 34
LETTERS = "АБВГДЕЖЗ"


def _sea_board(sea, size: int, reveal: bool, active: bool, title: str, alive: int) -> Image.Image:
    grid = SEA_CELL * size
    w = grid + SEA_PAD + 16
    h = grid + SEA_PAD + 70
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([0, 0, w - 1, h - 1], radius=22, fill=(8, 34, 64, 255),
                        outline=GOLD if active else (60, 110, 160), width=4 if active else 2)
    name, f = fit_text(d, title, 26, w - 150)
    d.text((18, 32), name, font=f, fill=CREAM, anchor="lm")
    ship = icon("ship", 34)
    im.alpha_composite(ship, (w - 92, 15))
    d.text((w - 52, 32), f"×{alive}", font=font(24), fill=GOLD, anchor="lm")
    ox, oy = SEA_PAD, 64
    water = gradient((grid, grid), (40, 140, 210), (12, 70, 140)).convert("RGBA")
    im.alpha_composite(water, (ox, oy))
    d = ImageDraw.Draw(im)
    for i in range(size + 1):
        d.line([(ox + i * SEA_CELL, oy), (ox + i * SEA_CELL, oy + grid)], fill=(160, 210, 245), width=1)
        d.line([(ox, oy + i * SEA_CELL), (ox + grid, oy + i * SEA_CELL)], fill=(160, 210, 245), width=1)
    for i in range(size):
        d.text((ox + i * SEA_CELL + SEA_CELL // 2, oy - 12), LETTERS[i], font=font(18), fill=(190, 220, 245), anchor="mm")
        d.text((ox - 16, oy + i * SEA_CELL + SEA_CELL // 2), str(i + 1), font=font(18), fill=(190, 220, 245), anchor="mm")

    def box(pos):
        r, c = divmod(pos, size)
        return ox + c * SEA_CELL, oy + r * SEA_CELL

    for ship_cells in sea.ships:
        sunk = ship_cells <= sea.shots
        if not (sunk or reveal):
            continue
        cells = sorted(ship_cells)
        x0, y0 = box(cells[0])
        x1, y1 = box(cells[-1])
        hull = (70, 78, 92) if sunk else (176, 186, 200)
        d.rounded_rectangle([x0 + 6, y0 + 6, x1 + SEA_CELL - 6, y1 + SEA_CELL - 6], radius=16, fill=hull, outline=(30, 34, 44), width=2)
    for pos in sea.shots:
        x, y = box(pos)
        ship_cells = sea.ship_at(pos)
        if ship_cells:
            sprite = icon("fire" if ship_cells <= sea.shots else "boom", SEA_CELL - 10)
            im.alpha_composite(sprite, (x + 5, y + 5))
        else:
            cx, cy = x + SEA_CELL // 2, y + SEA_CELL // 2
            d.ellipse([cx - 6, cy - 6, cx + 6, cy + 6], fill=(230, 244, 255))
            d.ellipse([cx - 14, cy - 14, cx + 14, cy + 14], outline=(200, 230, 250), width=2)
    return im


def sea_image(seas, names: tuple[str, str], target: int | None, reveal: bool = False, result: str | None = None) -> bytes:
    """seas — флоты игроков 0 и 1; target — по чьему полю сейчас стреляют."""
    boards = [_sea_board(seas[i], 8, reveal, target == i, names[i], seas[i].alive()) for i in range(2)]
    gap = 24
    w = boards[0].width * 2 + gap + 40
    h = boards[0].height + 40
    im = gradient((w, h), (6, 26, 52), (2, 12, 28)).convert("RGBA")
    for i, b in enumerate(boards):
        im.alpha_composite(b, (20 + i * (b.width + gap), 20))
    if result:
        veil = Image.new("RGBA", im.size, (0, 0, 0, 130))
        im.alpha_composite(veil)
        d = ImageDraw.Draw(im)
        trophy = icon("trophy", 170)
        paste_shadowed(im, trophy, ((w - 170) // 2, h // 2 - 150))
        text, f = fit_text(d, result, 44, w - 80)
        shadow_text(d, (w // 2, h // 2 + 70), text, f, fill=GOLD)
    return to_jpeg(im)


# =========================================================
# КАМЕНЬ-НОЖНИЦЫ-БУМАГА, МОНЕТКА, ОБЛОЖКИ
# =========================================================

W, H = 960, 540


def _card(top: tuple, bottom: tuple) -> Image.Image:
    im = gradient((W, H), top, bottom).convert("RGBA")
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse([W // 2 - 360, -220, W // 2 + 360, 300], fill=(255, 210, 120, 60))
    im.alpha_composite(glow.filter(ImageFilter.GaussianBlur(60)))
    return im


HANDS = {"rock": "rock", "paper": "paper", "scissors": "scissors"}
RPS_RU = {"rock": "Камень", "paper": "Бумага", "scissors": "Ножницы"}


def rps_image(names: tuple[str, str], picks: tuple[str | None, str | None], result: str | None = None,
              winner: int | None = None) -> bytes:
    """picks — None, пока выбор скрыт (рисуется знак вопроса)."""
    im = _card((58, 20, 92), (14, 8, 30))
    d = ImageDraw.Draw(im)
    for i in range(2):
        cx = W // 4 if i == 0 else W * 3 // 4
        pick = picks[i]
        if pick:
            hand = icon(HANDS[pick], 250)
            if i == 1:
                hand = hand.transpose(Image.FLIP_LEFT_RIGHT)
            paste_shadowed(im, hand, (cx - 125, 110))
            d = ImageDraw.Draw(im)
            d.text((cx, 392), RPS_RU[pick], font=font(30), fill=(230, 210, 255), anchor="mm")
        else:
            d.ellipse([cx - 110, 130, cx + 110, 350], fill=(80, 50, 120), outline=(150, 110, 210), width=4)
            d.text((cx, 240), "?", font=font(140), fill=(200, 170, 250), anchor="mm")
        name, f = fit_text(d, names[i], 36, W // 2 - 60)
        shadow_text(d, (cx, 450), name, f, fill=GOLD if winner == i else CREAM)
        if winner == i:
            crown = icon("crown", 90)
            paste_shadowed(im, crown, (cx - 45, 22))
            d = ImageDraw.Draw(im)
    shadow_text(d, (W // 2, 240), "VS", font(72), fill=GOLD)
    if result:
        text, f = fit_text(d, result, 38, W - 80)
        shadow_text(d, (W // 2, 505), text, f, fill=GOLD)
    return to_jpeg(im)


@lru_cache(maxsize=2)
def _coin_face(heads: bool, size: int = 300) -> Image.Image:
    if not heads:
        return icon("coin", size)
    big = size * 2
    disc = radial(big, (255, 226, 120), (214, 150, 30))
    mask = Image.new("L", (big, big), 0)
    ImageDraw.Draw(mask).ellipse([8, 8, big - 9, big - 9], fill=255)
    im = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    im.paste(disc, (0, 0), mask)
    d = ImageDraw.Draw(im)
    d.ellipse([8, 8, big - 9, big - 9], outline=(176, 110, 18), width=22)
    d.ellipse([60, 60, big - 61, big - 61], outline=(240, 190, 70), width=8)
    eagle = icon("eagle", int(big * 0.62))
    im.alpha_composite(eagle, ((big - eagle.width) // 2, (big - eagle.height) // 2))
    return im.resize((size, size), Image.LANCZOS)


def coin_image(title: str, heads: bool | None, subtitle: str = "") -> bytes:
    """heads=None — монетка в полёте (обе стороны)."""
    im = _card((24, 60, 46), (6, 22, 16))
    d = ImageDraw.Draw(im)
    if heads is None:
        a = _coin_face(True, 230).rotate(-14, resample=Image.BICUBIC)
        b = _coin_face(False, 230).rotate(12, resample=Image.BICUBIC)
        paste_shadowed(im, a, (W // 2 - 260, 120))
        paste_shadowed(im, b, (W // 2 + 30, 120))
    else:
        face = _coin_face(heads, 300)
        paste_shadowed(im, face, ((W - 300) // 2, 70))
    d = ImageDraw.Draw(im)
    text, f = fit_text(d, title, 48, W - 80)
    shadow_text(d, (W // 2, 425), text, f, fill=GOLD)
    if subtitle:
        text, f = fit_text(d, subtitle, 30, W - 80)
        shadow_text(d, (W // 2, 485), text, f)
    return to_jpeg(im)


COVERS = {
    "checkers": ("Шашки", ((96, 52, 22), (36, 18, 8)), ("crown", "trophy")),
    "sea": ("Морской бой", ((16, 70, 130), (4, 18, 40)), ("ship", "boom")),
    "rps": ("Камень, ножницы, бумага", ((70, 26, 110), (16, 8, 34)), ("rock", "scissors", "paper")),
}


def cover_image(kind: str, line: str, stake: int = 0) -> bytes:
    title, colors, icons = COVERS[kind]
    im = _card(*colors)
    d = ImageDraw.Draw(im)
    n = len(icons)
    step = 230
    x0 = W // 2 - step * (n - 1) // 2
    for i, name in enumerate(icons):
        sprite = icon(name, 190)
        paste_shadowed(im, sprite, (x0 + i * step - 95, 60))
    d = ImageDraw.Draw(im)
    text, f = fit_text(d, title, 60, W - 80)
    shadow_text(d, (W // 2, 330), text, f, fill=GOLD)
    text, f = fit_text(d, line, 32, W - 80)
    shadow_text(d, (W // 2, 400), text, f)
    if stake:
        gem = icon("diamond", 54)
        label = f"Ставка: {stake}"
        lw = d.textlength(label, font=font(36))
        x = int(W // 2 - (lw + 64) // 2)
        im.alpha_composite(gem, (x, 440))
        d = ImageDraw.Draw(im)
        shadow_text(d, (x + 64, 468), label, font(36), fill=(150, 220, 255), anchor="lm")
    return to_jpeg(im)
