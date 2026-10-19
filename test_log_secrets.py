"""
Ключи не попадают в логи: адреса запросов с key=, token= и токен бота прячутся.
Запуск:  python test_log_secrets.py
"""

import io
import logging
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))

import logging_setup  # noqa: E402

errors = []

line = ('HTTP Request: GET https://pixabay.com/api/?key=11111111-fakefakefakefakefake0&q=money&page=3 '
        '"HTTP/1.1 200 OK"')
clean = logging_setup.redact(line)
if "11111111" in clean or "key=***&q=money" not in clean:
    errors.append(f"pixabay: {clean}")
for text, secret in [
    ("GET https://x.io/v1?api_key=SECRET123", "SECRET123"),
    ("GET https://x.io/v1?a=1&token=abc.def", "abc.def"),
    ("POST https://api.telegram.org/bot8867373661:AAH_secret-Token/sendMessage", "AAH_secret"),
]:
    if secret in logging_setup.redact(text):
        errors.append(f"не спрятано: {text}")
if logging_setup.redact("обычный текст про ключи и токены") != "обычный текст про ключи и токены":
    errors.append("обычный текст не трогаем")

# Через настоящий логгер: и вывод, и кольцо для панели
logging_setup.setup()
stream = io.StringIO()
logging.getLogger().handlers[0].stream = stream
logging.getLogger("httpx").info("HTTP Request: GET %s %s", "https://pixabay.com/api/?key=SECRETKEY&q=cat", '"HTTP/1.1 200 OK"')
if "SECRETKEY" in stream.getvalue() or "key=***" not in stream.getvalue():
    errors.append(f"в выводе: {stream.getvalue()}")
if any("SECRETKEY" in r["message"] for r in logging_setup.ring.records):
    errors.append("в логах панели")

if errors:
    print("❌ " + "\n❌ ".join(errors))
    sys.exit(1)
print("✅ Ключи в логах спрятаны.")
