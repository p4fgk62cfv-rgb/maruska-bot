# Control Center architecture

Telegram Mini App
        │
        ▼
webapp/static/admin.html
        │
        ├── css/theme.css
        ├── js/api.js
        └── js/app.js
        │
        ▼
webapp/admin.py
        │
        ├── Telegram Mini App auth
        ├── group access checks
        ├── RBAC
        ├── audit
        ├── moderation
        ├── economy
        ├── Gifts
        └── analytics
        │
        ├───────────────┐
        ▼               ▼
admin_store.py    telegram_gifts.py
        │               │
        ▼               ▼
 PostgreSQL       Telegram Bot API
        │
        ├── admin_roles
        ├── admin_audit_log
        ├── telegram_gifts_catalog
        ├── telegram_gift_transactions
        ├── admin_broadcast_history
        ├── admin_moderation_rules
        └── admin_action_overrides
