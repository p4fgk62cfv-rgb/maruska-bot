"""
«Мара, покажи меня»: подписей много, и недавние не повторяются.
Запуск:  python test_show_me_captions.py
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))

from actions.show_me import CAPTIONS, RECENT_CAPTIONS, pick_caption  # noqa: E402

errors = []


def check(name, ok):
    print(("OK   " if ok else "FAIL ") + name)
    if not ok:
        errors.append(name)


check("подписей не меньше 60", len(CAPTIONS) >= 60)
check("подписи без дублей", len(set(CAPTIONS)) == len(CAPTIONS))
check("в каждой подписи есть имя", all("{name}" in c for c in CAPTIONS))
check("без «(а)»", not any("(а)" in c for c in CAPTIONS))

picked = [pick_caption("Вася") for _ in range(RECENT_CAPTIONS + 1)]
check("подряд без повторов", len(set(picked)) == len(picked))
check("имя подставлено", all("Вася" in p for p in picked))

if errors:
    sys.exit(1)
print("Всё ок")
