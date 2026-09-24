"""Persistent storage for Maruska Control Center.

All data here is deliberately PostgreSQL-backed: admin actions, roles,
gift catalog, gift transactions, broadcast history and moderation rules
must survive Railway restarts.
"""
import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text
from database.database import session_scope, utcnow


SCHEMA_SQL = (
    """
    CREATE TABLE IF NOT EXISTS admin_roles (
        chat_id BIGINT NOT NULL,
        telegram_id BIGINT NOT NULL,
        role VARCHAR(32) NOT NULL,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (chat_id, telegram_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS admin_audit_log (
        id BIGSERIAL PRIMARY KEY,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        admin_id BIGINT NOT NULL,
        chat_id BIGINT,
        target_user_id BIGINT,
        action VARCHAR(80) NOT NULL,
        category VARCHAR(40) NOT NULL,
        details JSONB NOT NULL DEFAULT '{}'::jsonb,
        result VARCHAR(20) NOT NULL DEFAULT 'success'
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_admin_audit_created ON admin_audit_log(created_at DESC)",
    "CREATE INDEX IF NOT EXISTS ix_admin_audit_chat ON admin_audit_log(chat_id, created_at DESC)",
    "CREATE INDEX IF NOT EXISTS ix_admin_audit_target ON admin_audit_log(target_user_id, created_at DESC)",
    """
    CREATE TABLE IF NOT EXISTS telegram_gifts_catalog (
        gift_id VARCHAR(255) PRIMARY KEY,
        star_count INTEGER NOT NULL,
        upgrade_star_count INTEGER NOT NULL DEFAULT 0,
        is_premium BOOLEAN NOT NULL DEFAULT FALSE,
        total_count INTEGER,
        remaining_count INTEGER,
        personal_total_count INTEGER,
        personal_remaining_count INTEGER,
        sticker JSONB,
        internal_price BIGINT NOT NULL DEFAULT 0,
        enabled BOOLEAN NOT NULL DEFAULT TRUE,
        synced_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS telegram_gift_transactions (
        id BIGSERIAL PRIMARY KEY,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        admin_id BIGINT NOT NULL,
        chat_id BIGINT,
        target_user_id BIGINT NOT NULL,
        gift_id VARCHAR(255) NOT NULL,
        diamond_cost BIGINT NOT NULL,
        star_cost INTEGER NOT NULL,
        status VARCHAR(24) NOT NULL,
        telegram_response JSONB
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_gift_tx_created ON telegram_gift_transactions(created_at DESC)",
    "CREATE INDEX IF NOT EXISTS ix_gift_tx_target ON telegram_gift_transactions(target_user_id, created_at DESC)",
    """
    CREATE TABLE IF NOT EXISTS admin_broadcast_history (
        id BIGSERIAL PRIMARY KEY,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        admin_id BIGINT NOT NULL,
        chat_id BIGINT,
        text TEXT NOT NULL,
        sent INTEGER NOT NULL DEFAULT 0,
        failed INTEGER NOT NULL DEFAULT 0,
        status VARCHAR(24) NOT NULL DEFAULT 'completed'
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS admin_moderation_rules (
        chat_id BIGINT PRIMARY KEY,
        config JSONB NOT NULL DEFAULT '{}'::jsonb,
        updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_by BIGINT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS admin_action_overrides (
        chat_id BIGINT NOT NULL,
        action_key VARCHAR(120) NOT NULL,
        enabled BOOLEAN NOT NULL DEFAULT TRUE,
        cooldown_seconds INTEGER NOT NULL DEFAULT 0,
        aliases JSONB NOT NULL DEFAULT '[]'::jsonb,
        updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (chat_id, action_key)
    )
    """,
)


async def ensure_schema() -> None:
    async with session_scope() as session:
        for statement in SCHEMA_SQL:
            await session.execute(text(statement))
        await session.commit()


async def audit(admin_id: int, action: str, category: str, *, chat_id: int | None = None,
                target_user_id: int | None = None, details: dict | None = None,
                result: str = "success") -> None:
    async with session_scope() as session:
        await session.execute(text("""
            INSERT INTO admin_audit_log
            (admin_id, chat_id, target_user_id, action, category, details, result)
            VALUES (:admin_id, :chat_id, :target, :action, :category, CAST(:details AS JSONB), :result)
        """), {
            "admin_id": admin_id, "chat_id": chat_id, "target": target_user_id,
            "action": action, "category": category,
            "details": json.dumps(details or {}, ensure_ascii=False), "result": result,
        })
        await session.commit()


async def audit_list(*, chat_id: int | None = None, category: str | None = None,
                     target_user_id: int | None = None, limit: int = 100) -> list[dict]:
    clauses = []
    params: dict[str, Any] = {"limit": max(1, min(limit, 300))}
    if chat_id is not None:
        clauses.append("chat_id = :chat_id")
        params["chat_id"] = chat_id
    if category:
        clauses.append("category = :category")
        params["category"] = category
    if target_user_id is not None:
        clauses.append("target_user_id = :target")
        params["target"] = target_user_id
    where = "WHERE " + " AND ".join(clauses) if clauses else ""
    async with session_scope() as session:
        rows = (await session.execute(text(f"""
            SELECT id, created_at, admin_id, chat_id, target_user_id,
                   action, category, details, result
            FROM admin_audit_log {where}
            ORDER BY created_at DESC LIMIT :limit
        """), params)).mappings().all()
    return [dict(row) for row in rows]


ROLE_PERMISSIONS = {
    "owner": {"*"},
    "super_admin": {"*"},
    "moderator": {"dashboard", "users", "moderation", "journal"},
    "economy": {"dashboard", "users", "economy", "gifts", "journal"},
    "game": {"dashboard", "users", "games", "journal"},
    "content": {"dashboard", "users", "maruska", "actions", "journal"},
    "analytics": {"dashboard", "analytics", "journal"},
}


async def get_role(chat_id: int, telegram_id: int) -> str | None:
    async with session_scope() as session:
        value = await session.scalar(text(
            "SELECT role FROM admin_roles WHERE chat_id=:chat AND telegram_id=:user"
        ), {"chat": chat_id, "user": telegram_id})
    return value


async def set_role(chat_id: int, telegram_id: int, role: str) -> None:
    async with session_scope() as session:
        await session.execute(text("""
            INSERT INTO admin_roles(chat_id, telegram_id, role)
            VALUES (:chat, :user, :role)
            ON CONFLICT (chat_id, telegram_id)
            DO UPDATE SET role=EXCLUDED.role, updated_at=CURRENT_TIMESTAMP
        """), {"chat": chat_id, "user": telegram_id, "role": role})
        await session.commit()


async def list_roles(chat_id: int) -> list[dict]:
    async with session_scope() as session:
        rows = (await session.execute(text("""
            SELECT chat_id, telegram_id, role, created_at, updated_at
            FROM admin_roles WHERE chat_id=:chat ORDER BY role, telegram_id
        """), {"chat": chat_id})).mappings().all()
    return [dict(row) for row in rows]


async def get_rules(chat_id: int) -> dict:
    async with session_scope() as session:
        row = (await session.execute(text(
            "SELECT config FROM admin_moderation_rules WHERE chat_id=:chat"
        ), {"chat": chat_id})).scalar_one_or_none()
    return row or {}


async def set_rules(chat_id: int, config: dict, admin_id: int) -> None:
    async with session_scope() as session:
        await session.execute(text("""
            INSERT INTO admin_moderation_rules(chat_id, config, updated_at, updated_by)
            VALUES (:chat, CAST(:config AS JSONB), CURRENT_TIMESTAMP, :admin)
            ON CONFLICT(chat_id) DO UPDATE SET
              config=EXCLUDED.config, updated_at=CURRENT_TIMESTAMP, updated_by=EXCLUDED.updated_by
        """), {"chat": chat_id, "config": json.dumps(config, ensure_ascii=False), "admin": admin_id})
        await session.commit()


async def set_action_override(chat_id: int, action_key: str, *, enabled: bool,
                              cooldown_seconds: int = 0, aliases: list[str] | None = None) -> None:
    async with session_scope() as session:
        await session.execute(text("""
            INSERT INTO admin_action_overrides(chat_id, action_key, enabled, cooldown_seconds, aliases)
            VALUES (:chat, :key, :enabled, :cooldown, CAST(:aliases AS JSONB))
            ON CONFLICT(chat_id, action_key) DO UPDATE SET
              enabled=EXCLUDED.enabled,
              cooldown_seconds=EXCLUDED.cooldown_seconds,
              aliases=EXCLUDED.aliases,
              updated_at=CURRENT_TIMESTAMP
        """), {
            "chat": chat_id, "key": action_key, "enabled": enabled,
            "cooldown": max(0, min(int(cooldown_seconds), 86400)),
            "aliases": json.dumps(aliases or [], ensure_ascii=False),
        })
        await session.commit()


async def action_overrides(chat_id: int) -> dict[str, dict]:
    async with session_scope() as session:
        rows = (await session.execute(text("""
            SELECT action_key, enabled, cooldown_seconds, aliases
            FROM admin_action_overrides WHERE chat_id=:chat
        """), {"chat": chat_id})).mappings().all()
    return {row["action_key"]: dict(row) for row in rows}


async def action_override(chat_id: int, action_key: str) -> dict | None:
    async with session_scope() as session:
        row = (await session.execute(text("""
            SELECT enabled, cooldown_seconds, aliases
            FROM admin_action_overrides WHERE chat_id=:chat AND action_key=:key
        """), {"chat": chat_id, "key": action_key})).mappings().first()
    return dict(row) if row else None


async def sync_gifts(items: list[dict]) -> None:
    async with session_scope() as session:
        for gift in items:
            await session.execute(text("""
                INSERT INTO telegram_gifts_catalog
                (gift_id, star_count, upgrade_star_count, is_premium, total_count,
                 remaining_count, personal_total_count, personal_remaining_count, sticker, synced_at)
                VALUES (:id, :stars, :upgrade, :premium, :total, :remaining,
                        :ptotal, :premaining, CAST(:sticker AS JSONB), CURRENT_TIMESTAMP)
                ON CONFLICT(gift_id) DO UPDATE SET
                  star_count=EXCLUDED.star_count,
                  upgrade_star_count=EXCLUDED.upgrade_star_count,
                  is_premium=EXCLUDED.is_premium,
                  total_count=EXCLUDED.total_count,
                  remaining_count=EXCLUDED.remaining_count,
                  personal_total_count=EXCLUDED.personal_total_count,
                  personal_remaining_count=EXCLUDED.personal_remaining_count,
                  sticker=EXCLUDED.sticker,
                  synced_at=CURRENT_TIMESTAMP
            """), {
                "id": gift["id"], "stars": gift["star_count"],
                "upgrade": gift.get("upgrade_star_count", 0),
                "premium": gift.get("is_premium", False),
                "total": gift.get("total_count"), "remaining": gift.get("remaining_count"),
                "ptotal": gift.get("personal_total_count"),
                "premaining": gift.get("personal_remaining_count"),
                "sticker": json.dumps(gift.get("sticker") or {}, ensure_ascii=False),
            })
        await session.commit()


async def gifts_list() -> list[dict]:
    async with session_scope() as session:
        rows = (await session.execute(text("""
            SELECT gift_id, star_count, upgrade_star_count, is_premium, total_count,
                   remaining_count, personal_total_count, personal_remaining_count,
                   sticker, internal_price, enabled, synced_at
            FROM telegram_gifts_catalog ORDER BY star_count, gift_id
        """))).mappings().all()
    return [dict(row) for row in rows]


async def set_gift_price(gift_id: str, price: int, enabled: bool | None = None) -> None:
    async with session_scope() as session:
        if enabled is None:
            await session.execute(text(
                "UPDATE telegram_gifts_catalog SET internal_price=:price WHERE gift_id=:id"
            ), {"price": max(0, price), "id": gift_id})
        else:
            await session.execute(text("""
                UPDATE telegram_gifts_catalog SET internal_price=:price, enabled=:enabled WHERE gift_id=:id
            """), {"price": max(0, price), "enabled": enabled, "id": gift_id})
        await session.commit()


async def create_gift_tx(admin_id: int, target_user_id: int, gift_id: str, diamond_cost: int,
                         star_cost: int, *, chat_id: int | None = None, status: str = "pending",
                         response: dict | None = None) -> int:
    async with session_scope() as session:
        result = await session.execute(text("""
            INSERT INTO telegram_gift_transactions
            (admin_id, chat_id, target_user_id, gift_id, diamond_cost, star_cost, status, telegram_response)
            VALUES (:admin, :chat, :target, :gift, :diamonds, :stars, :status, CAST(:response AS JSONB))
            RETURNING id
        """), {
            "admin": admin_id, "chat": chat_id, "target": target_user_id,
            "gift": gift_id, "diamonds": diamond_cost, "stars": star_cost,
            "status": status, "response": json.dumps(response or {}, ensure_ascii=False),
        })
        tx_id = result.scalar_one()
        await session.commit()
    return int(tx_id)


async def update_gift_tx(tx_id: int, status: str, response: dict | None = None) -> None:
    async with session_scope() as session:
        await session.execute(text("""
            UPDATE telegram_gift_transactions
            SET status=:status, telegram_response=CAST(:response AS JSONB)
            WHERE id=:id
        """), {"id": tx_id, "status": status,
               "response": json.dumps(response or {}, ensure_ascii=False)})
        await session.commit()


async def gift_transactions(limit: int = 50) -> list[dict]:
    async with session_scope() as session:
        rows = (await session.execute(text("""
            SELECT id, created_at, admin_id, chat_id, target_user_id,
                   gift_id, diamond_cost, star_cost, status
            FROM telegram_gift_transactions
            ORDER BY created_at DESC LIMIT :limit
        """), {"limit": max(1, min(limit, 200))})).mappings().all()
    return [dict(row) for row in rows]


async def broadcast_history(limit: int = 50) -> list[dict]:
    async with session_scope() as session:
        rows = (await session.execute(text("""
            SELECT id, created_at, admin_id, chat_id, text, sent, failed, status
            FROM admin_broadcast_history ORDER BY created_at DESC LIMIT :limit
        """), {"limit": max(1, min(limit, 200))})).mappings().all()
    return [dict(row) for row in rows]


async def save_broadcast(admin_id: int, chat_id: int | None, message: str,
                         sent: int, failed: int, status: str = "completed") -> None:
    async with session_scope() as session:
        await session.execute(text("""
            INSERT INTO admin_broadcast_history(admin_id, chat_id, text, sent, failed, status)
            VALUES (:admin, :chat, :text, :sent, :failed, :status)
        """), {"admin": admin_id, "chat": chat_id, "text": message,
               "sent": sent, "failed": failed, "status": status})
        await session.commit()
