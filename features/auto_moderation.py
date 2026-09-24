"""Runtime enforcement for Control Center moderation rules.

The panel writes per-group rules to PostgreSQL. This router applies the
rules to incoming group messages. Defaults are OFF; enabling a rule in the
panel is an explicit admin action.
"""
import re
import time
from collections import defaultdict, deque

from aiogram import Router
from aiogram.types import Message

from botcontext import display_name_of
from settings.handler import ADMIN_STATUSES, is_owner
from webapp.admin_store import audit, get_rules

router = Router(name="auto_moderation")

WINDOW = 10
MAX_TRACKED_USERS = 10000
_recent: dict[tuple[int,int], deque[float]] = defaultdict(deque)
_last_violation: dict[tuple[int,int,str], float] = {}
_LINK_RE = re.compile(r"(?:https?://|www\.|t\.me/|telegram\.me/|@)[^\s]+", re.I)

async def _is_admin(message: Message) -> bool:
    if not message.from_user:
        return True
    if is_owner(message.from_user.id):
        return True
    try:
        member = await message.bot.get_chat_member(message.chat.id, message.from_user.id)
        return member.status in ADMIN_STATUSES
    except Exception:
        return False

async def _punish(message: Message, rule: str, reason: str):
    key=(message.chat.id, message.from_user.id, rule)
    now=time.monotonic()
    if now-_last_violation.get(key,0)<3:
        return
    _last_violation[key]=now
    try:
        await message.delete()
    except Exception:
        pass
    rules=await get_rules(message.chat.id)
    punish=str(rules.get(f"{rule}_action", "delete"))
    if punish in {"mute", "ban"}:
        try:
            from features.moderation import mute, ban
            if punish=="mute":
                await mute(message.bot,message.chat.id,message.from_user.id,int(rules.get(f"{rule}_minutes",60)))
            else:
                await ban(message.bot,message.chat.id,message.from_user.id)
        except Exception:
            punish="delete"
    await audit(message.from_user.id, "auto_moderation", "moderation", chat_id=message.chat.id,
                 target_user_id=message.from_user.id, details={"rule":rule,"reason":reason,"action":punish})

@router.message()
async def auto_moderate(message: Message):
    if message.chat.type not in ("group","supergroup") or not message.from_user or message.from_user.is_bot:
        return
    if await _is_admin(message):
        return
    config=await get_rules(message.chat.id)
    if not config:
        return
    text=message.text or message.caption or ""
    key=(message.chat.id,message.from_user.id)
    now=time.monotonic()
    q=_recent[key]
    q.append(now)
    while q and now-q[0]>WINDOW:q.popleft()
    if config.get("anti_flood") and len(q)>=int(config.get("anti_flood_limit",10)):
        await _punish(message,"anti_flood",f"{len(q)} messages/{WINDOW}s")
        return
    if config.get("links") and _LINK_RE.search(text):
        allowed=[str(x).lower() for x in config.get("allowed_domains",[]) if str(x).strip()]
        if not any(domain in text.lower() for domain in allowed):
            await _punish(message,"links","link detected")
            return
    if config.get("stop_words"):
        words=[str(x).strip().lower() for x in config.get("stop_words_list",[]) if str(x).strip()]
        lower=text.lower()
        if any(word in lower for word in words):
            await _punish(message,"stop_words","stop word detected")
            return
    if len(_recent)>MAX_TRACKED_USERS:
        for stale in list(_recent)[:1000]:_recent.pop(stale,None)
