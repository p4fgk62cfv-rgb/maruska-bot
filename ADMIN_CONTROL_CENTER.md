# 💜 Maruska Control Center

Полноценная мобильная админ-панель для Telegram-групп и функций Маруськи.

## Что реализовано

### Command Center
- состояние группы;
- быстрые действия;
- блок «Требует внимания»;
- сводная статистика;
- последние события.

### 🛡 Модерация
- mute / unmute / ban / unban / kick;
- закрытие чата;
- persistent per-group rules;
- Anti-Flood;
- контроль ссылок;
- Stop Words;
- автоматическое удаление нарушений;
- опциональный auto-mute / auto-ban;
- журнал автоматических срабатываний.

Правила по умолчанию выключены. Их включение в панели является явным действием администратора.

### 👥 Участники
- поиск;
- профиль;
- Diamonds / XP / Karma;
- быстрые moderation actions;
- изменение баланса;
- Telegram Gift из карточки пользователя.

### 🎬 Actions
- каталог текущих Actions;
- включение/выключение Action отдельно для группы;
- per-group cooldown override;
- сохранение overrides в PostgreSQL.

> Важно: основной каталог Actions остаётся кодовым источником истины. Панель не мутирует `catalog_data.py` на лету. Она хранит безопасные runtime overrides.

### 💎 Economy
- сводка Diamonds;
- история транзакций;
- XP / Karma через существующие сервисы;
- административные корректировки с аудитом.

### 🎁 Telegram Gifts
- получение актуального каталога через `getAvailableGifts`;
- баланс Stars через `getMyStarBalance`;
- синхронизация каталога в PostgreSQL;
- внутренняя цена в Diamonds;
- включение/выключение подарка;
- отправка реального Gift через `sendGift`;
- автоматический refund Diamonds, если Telegram не принял подарок;
- история gift transactions.

Telegram Bot API 10.1 предоставляет эти методы непосредственно для ботов.

### 📊 Analytics
- дневная динамика;
- ключевые метрики;
- последние системные события.

### 📢 Broadcasts
- безопасная рассылка по выбранной группе;
- история отправок;
- количество успешных/неуспешных отправок.

### 📜 Audit Log
Все критические административные операции сохраняются в PostgreSQL:
- изменения баланса;
- XP;
- настройки;
- moderation;
- роли;
- Gifts;
- Actions;
- рассылки;
- автоматическая модерация.

Лог переживает перезапуск Railway.

### 👑 RBAC
Роли:
- owner;
- super_admin;
- moderator;
- economy;
- game;
- content;
- analytics.

Проверка роли выполняется на сервере, а не только в JavaScript.

### 🔐 Безопасность
- Telegram Mini App `initData` HMAC verification;
- проверка реального админства;
- проверка доступа к конкретной группе;
- проверка принадлежности target user к выбранной группе;
- серверная проверка ролей;
- owner-only системные endpoints;
- аудит опасных действий.

## Дизайн

Стиль: **Premium Dark / Purple Control Center**.

Мобильная навигация:

`Главная · Модерация · Люди · Маруська · Экономика`

Остальные разделы доступны через боковое меню:

`Gifts · Analytics · Broadcasts · Journal · Settings · Admins`

На desktop автоматически появляется постоянный sidebar.

## Новые persistent таблицы

При старте проекта автоматически создаются:

- `admin_roles`
- `admin_audit_log`
- `telegram_gifts_catalog`
- `telegram_gift_transactions`
- `admin_broadcast_history`
- `admin_moderation_rules`
- `admin_action_overrides`

Миграции идемпотентные: повторный запуск безопасен.

## Переменные окружения

Скопируй `.env.example` и заполни:

```text
BOT_TOKEN=
DATABASE_URL=
OWNER_IDS=
PUBLIC_URL=
RAILWAY_PUBLIC_DOMAIN=
CONTEXT_MESSAGES=8
GEMINI_API_KEY=
UNSPLASH_ACCESS_KEY=
PIXABAY_API_KEY=
```

`OWNER_IDS` — Telegram ID владельцев через запятую, если это поддерживает текущая конфигурация проекта.

## Запуск

```bash
pip install -r requirements.txt
python bot.py
```

Для Railway используется существующий `Procfile`/`Dockerfile` проекта.

## Mini App

Панель доступна по:

```text
/admin
```

Статика новой панели:

```text
webapp/static/admin.html
webapp/static/admin/css/theme.css
webapp/static/admin/js/api.js
webapp/static/admin/js/app.js
```

## Проверка

Минимальная проверка панели:

```bash
python test_webapp.py
node --check webapp/static/admin/js/app.js
```

Также рекомендуется прогнать существующие проверки проекта:

```bash
python test_actions.py
python test_crocodile.py
python test_economy.py
python test_features.py
python test_extras.py
python test_settings.py
python test_webapp.py
```

## Важное поведение Telegram Gifts

Внутренние Diamonds — это экономика Маруськи. Telegram Stars — отдельный баланс бота.

При отправке подарка:

`Diamonds пользователя → резерв/списание → Telegram sendGift → успех`

Если `sendGift` возвращает ошибку, Diamonds возвращаются пользователю, а операция помечается как `failed`.

Подарок отправляется только пользователю, который присутствует в выбранной группе.

## Что сознательно не делается

Панель не редактирует исходный Python-каталог Actions и не подменяет Telegram UI. Telegram остаётся источником реальных прав и Gift-каталога, а Control Center управляет дополнительной логикой Маруськи.
