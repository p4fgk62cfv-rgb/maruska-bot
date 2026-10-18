"""
«Гармония»: распознавание, процент пары на день, фразы по уровням.
Запуск:  python test_harmony.py
"""

import os
import pathlib
import random
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://x:y@127.0.0.1:1/z")

from features.harmony import TIERS, comment_for, format_harmony, harmony_percent, hearts, is_harmony_request  # noqa: E402

errors, checks = [], 0


def check(ok, what):
    global checks
    checks += 1
    if not ok:
        errors.append(what)


for text in ("гармония", "Гармония!", "гармония @kate", "/гармония", "гармонию"):
    check(is_harmony_request(text), f"запрос «{text}»")
for text in ("гармония между нами", "у нас гармония", "гарм", "", None):
    check(not is_harmony_request(text), f"не запрос «{text}»")

values = [harmony_percent(-1, a, b, "2026-10-19") for a in range(1, 60) for b in range(100, 120)]
check(all(0 <= v <= 100 for v in values), "процент в пределах 0–100")
check(max(values) - min(values) > 80, "проценты разные у разных пар")
check(harmony_percent(-1, 5, 9, "d") == harmony_percent(-1, 9, 5, "d"), "порядок двоих не важен")
check(harmony_percent(-1, 5, 9, "d") != harmony_percent(-1, 5, 9, "e"), "на другой день — другой процент")

for floor, phrases in TIERS:
    check(comment_for(floor + 0.1, random.Random(0)) in phrases, f"уровень {floor}%")
check(comment_for(100, random.Random(0)) in TIERS[0][1], "100% — самая тёплая фраза")
phrases = [p for _, group in TIERS for p in group]
check(len(phrases) >= 150 and len(set(phrases)) == len(phrases), f"много фраз и без дублей: {len(phrases)}")
check(all(len(group) >= 20 for _, group in TIERS), "в каждом уровне не меньше 20 фраз")
said = [comment_for(97, chat_id=-777) for _ in range(len(TIERS[0][1]))]
check(len(set(said)) == len(said), "в одном чате фразы не повторяются, пока не переберутся все")

check(hearts(65.7) == "❤️" * 7 + "🤍" * 3, "сердечки")

text = format_harmony("Аня", "<b>Вася</b>", 65.7, random.Random(1))
check("Аня</b> + <b>&lt;b&gt;Вася" in text and "<b>65,7%</b>" in text, f"оформление: {text}")

if errors:
    print(f"❌ {len(errors)} из {checks} проверок не прошли:")
    print("\n".join("  " + e for e in errors))
    sys.exit(1)

print(f"✅ Все {checks} проверок гармонии прошли.")
