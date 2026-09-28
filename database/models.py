from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    String,
    Text,
    DateTime,
    UniqueConstraint,
    Boolean,
    Float,
)

from sqlalchemy.orm import Mapped, mapped_column

from database.database import Base, utcnow


class User(Base):
    # dm_ok: человек сам писал боту в личку — значит, ему можно
    # отправить рассылку. Telegram не даёт ботам писать первыми.
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )

    telegram_id: Mapped[int] = mapped_column(
        BigInteger,
        unique=True,
        index=True,
    )

    username: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    first_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    gender: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow,
    )

    dm_ok: Mapped[bool] = mapped_column(Boolean, default=False)


class MessageMemory(Base):
    __tablename__ = "message_memory"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )

    chat_id: Mapped[int] = mapped_column(
        BigInteger,
        index=True,
    )

    telegram_user_id: Mapped[int] = mapped_column(
        BigInteger,
        index=True,
    )

    username: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    message: Mapped[str] = mapped_column(
        Text,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow,
        index=True,
    )


class UserProfile(Base):
    __tablename__ = "user_profiles"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )

    telegram_id: Mapped[int] = mapped_column(
        BigInteger,
        unique=True,
        index=True,
    )

    display_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    karma: Mapped[int] = mapped_column(
        default=0,
        index=True,
    )

    coins: Mapped[int] = mapped_column(
        default=0,
    )

    messages_count: Mapped[int] = mapped_column(
        default=0,
    )

    games_played: Mapped[int] = mapped_column(
        default=0,
    )

    games_won: Mapped[int] = mapped_column(
        default=0,
    )

    # Опыт и уровень
    xp: Mapped[int] = mapped_column(default=0, index=True)

    level: Mapped[int] = mapped_column(default=1)

    # Сколько опыта набрано за сообщения сегодня (потолок от флуда)
    xp_today: Mapped[int] = mapped_column(default=0)

    xp_day: Mapped[str | None] = mapped_column(
        String(10),
        nullable=True,
    )

    bonus_days: Mapped[int] = mapped_column(default=0)

    gifts_sent: Mapped[int] = mapped_column(default=0)

    likes_received: Mapped[int] = mapped_column(default=0)

    # Ежедневный бонус: когда забирали последний раз и какая серия
    last_bonus_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    bonus_streak: Mapped[int] = mapped_column(
        default=0,
    )

    best_streak: Mapped[int] = mapped_column(
        default=0,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow,
    )


class UserFact(Base):
    __tablename__ = "user_facts"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )

    telegram_id: Mapped[int] = mapped_column(
        BigInteger,
        index=True,
    )

    fact: Mapped[str] = mapped_column(
        Text,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow,
    )


class GroupMember(Base):
    __tablename__ = "group_members"

    __table_args__ = (
        UniqueConstraint(
            "chat_id",
            "telegram_id",
            name="uq_group_member",
        ),
    )

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )

    chat_id: Mapped[int] = mapped_column(
        BigInteger,
        index=True,
    )

    telegram_id: Mapped[int] = mapped_column(
        BigInteger,
        index=True,
    )

    display_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    messages_count: Mapped[int] = mapped_column(
        default=0,
    )

    games_played: Mapped[int] = mapped_column(
        default=0,
    )

    games_won: Mapped[int] = mapped_column(
        default=0,
    )

    # Активность за текущую неделю — для итогов
    week_messages: Mapped[int] = mapped_column(default=0)

    week_start: Mapped[str | None] = mapped_column(
        String(10),
        nullable=True,
    )

    actions_count: Mapped[int] = mapped_column(default=0)

    ai_count: Mapped[int] = mapped_column(default=0)

    vip: Mapped[bool] = mapped_column(Boolean, default=False)

    left_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    joined_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow,
    )


class RatingVote(Base):
    __tablename__ = "rating_votes"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )

    giver_telegram_id: Mapped[int] = mapped_column(
        BigInteger,
        index=True,
    )

    target_telegram_id: Mapped[int] = mapped_column(
        BigInteger,
        index=True,
    )

    amount: Mapped[int] = mapped_column(
        default=1,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow,
        index=True,
    )


class ActionImage(Base):
    """
    Фотографии для действий.

    Один action = отдельная коллекция фотографий.

    used=False — не использовалась в текущем цикле.
    used=True  — уже использовалась.

    telegram_file_id кэширует file_id после первой отправки,
    чтобы Telegram не скачивал картинку заново каждый раз.
    """

    __tablename__ = "action_images"

    __table_args__ = (
        UniqueConstraint(
            "action",
            "photo_id",
            name="uq_action_photo",
        ),
    )

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )

    action: Mapped[str] = mapped_column(
        String(100),
        index=True,
    )

    photo_id: Mapped[str] = mapped_column(
        String(100),
    )

    image_url: Mapped[str] = mapped_column(
        Text,
    )

    # Версия поменьше на случай, если основная слишком тяжёлая.
    fallback_url: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    telegram_file_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    provider: Mapped[str] = mapped_column(
        String(20),
        default="pixabay",
        index=True,
    )

    # Атрибуция нужна только источникам, которые её требуют
    # (Unsplash). Для Pixabay остаётся пустой.
    photographer_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    photographer_url: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # Страница фото у источника. Нужна только для атрибуции Unsplash.
    unsplash_url: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    source_page: Mapped[int] = mapped_column(
        default=1,
    )

    used: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        index=True,
    )

    used_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow,
    )


class GameRound(Base):
    """
    Раунд игры в чате. В один момент в чате активен максимум один.

    status:
        waiting  — ждём, пока ведущий возьмёт слово
        playing  — слово взято, идёт отгадывание
        finished — кто-то угадал
        cancelled — ведущий сдался или раунд остановили
    """

    __tablename__ = "game_rounds"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )

    chat_id: Mapped[int] = mapped_column(
        BigInteger,
        index=True,
    )

    game: Mapped[str] = mapped_column(
        String(30),
        default="crocodile",
        index=True,
    )

    host_telegram_id: Mapped[int] = mapped_column(
        BigInteger,
        index=True,
    )

    host_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    word: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    level: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
    )

    # Разовый ключ раунда: по нему Mini App понимает,
    # какой раунд открыт, и кто имеет право рисовать.
    token: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        index=True,
    )

    status: Mapped[str] = mapped_column(
        String(20),
        default="waiting",
        index=True,
    )

    message_id: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
    )

    # Сколько лайков собрал рисунок этого раунда
    likes: Mapped[int] = mapped_column(default=0)

    winner_telegram_id: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
    )

    winner_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    started_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow,
        index=True,
    )

    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )


class GroupSettings(Base):
    """
    Настройки одной группы.

    Значения лежат в JSON, поэтому новая функция в реестре
    не требует миграции базы: незнакомые ключи просто берут
    значение по умолчанию.
    """

    __tablename__ = "group_settings"

    chat_id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
    )

    title: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    values: Mapped[dict] = mapped_column(
        JSON,
        default=dict,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow,
    )


class Transaction(Base):
    """
    История операций с алмазами.

    amount > 0 — начисление, amount < 0 — списание.
    balance_after хранится, чтобы историю можно было читать
    как выписку, не пересчитывая всё заново.
    """

    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )

    telegram_id: Mapped[int] = mapped_column(
        BigInteger,
        index=True,
    )

    chat_id: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
        index=True,
    )

    amount: Mapped[int] = mapped_column()

    balance_after: Mapped[int] = mapped_column(default=0)

    # Машинный код операции: bonus, game_win, game_host, gift_in...
    reason: Mapped[str] = mapped_column(
        String(40),
        index=True,
    )

    # Человеческое пояснение для истории
    note: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow,
        index=True,
    )


class DrawingLike(Base):
    """
    Кто лайкнул рисунок. Нужна, чтобы один человек не мог
    накрутить художнику сотню лайков одной кнопкой.
    """

    __tablename__ = "drawing_likes"

    __table_args__ = (
        UniqueConstraint(
            "round_id",
            "telegram_id",
            name="uq_drawing_like",
        ),
    )

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )

    round_id: Mapped[int] = mapped_column(index=True)

    telegram_id: Mapped[int] = mapped_column(
        BigInteger,
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow,
    )


class InventoryItem(Base):
    """
    Вещь в инвентаре: купленная или подаренная.

    Одна строка на владельца и вид товара, количество в qty.
    from_telegram_id заполняется только у подарков — так в профиле
    видно, кто что подарил.
    """

    __tablename__ = "inventory"

    __table_args__ = (
        UniqueConstraint(
            "telegram_id",
            "item_key",
            "from_telegram_id",
            name="uq_inventory_item",
        ),
    )

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )

    telegram_id: Mapped[int] = mapped_column(
        BigInteger,
        index=True,
    )

    item_key: Mapped[str] = mapped_column(
        String(40),
        index=True,
    )

    qty: Mapped[int] = mapped_column(default=1)

    from_telegram_id: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
    )

    from_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow,
    )


class UserAchievement(Base):
    """
    Открытые достижения. Одна строка на человека и достижение.
    """

    __tablename__ = "user_achievements"

    __table_args__ = (
        UniqueConstraint(
            "telegram_id",
            "achievement_key",
            name="uq_user_achievement",
        ),
    )

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )

    telegram_id: Mapped[int] = mapped_column(
        BigInteger,
        index=True,
    )

    achievement_key: Mapped[str] = mapped_column(
        String(40),
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow,
    )


class DailyStat(Base):
    """
    Активность чата по дням — для графиков в веб-панели.

    message_memory для этого не годится: она обрезается, а
    недельные счётчики в group_members обнуляются каждый
    понедельник. Здесь копится история.
    """

    __tablename__ = "daily_stats"

    __table_args__ = (
        UniqueConstraint("chat_id", "day", name="uq_daily_stat"),
    )

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )

    chat_id: Mapped[int] = mapped_column(
        BigInteger,
        index=True,
    )

    day: Mapped[str] = mapped_column(
        String(10),
        index=True,
    )

    messages: Mapped[int] = mapped_column(default=0)

    actions: Mapped[int] = mapped_column(default=0)

    games: Mapped[int] = mapped_column(default=0)

    active_users: Mapped[int] = mapped_column(default=0)

    new_users: Mapped[int] = mapped_column(default=0)

    warnings: Mapped[int] = mapped_column(default=0)

    mutes: Mapped[int] = mapped_column(default=0)

    bans: Mapped[int] = mapped_column(default=0)

    deleted: Mapped[int] = mapped_column(default=0)

    ai_requests: Mapped[int] = mapped_column(default=0)

    commands: Mapped[int] = mapped_column(default=0)

    autoreplies: Mapped[int] = mapped_column(default=0)

    images: Mapped[int] = mapped_column(default=0)

    xp: Mapped[int] = mapped_column(default=0)


class BlockedUser(Base):
    """
    Кого бот игнорирует в конкретной группе.
    """

    __tablename__ = "blocked_users"

    __table_args__ = (
        UniqueConstraint("chat_id", "telegram_id", name="uq_blocked_user"),
    )

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )

    chat_id: Mapped[int] = mapped_column(BigInteger, index=True)

    telegram_id: Mapped[int] = mapped_column(BigInteger, index=True)

    reason: Mapped[str | None] = mapped_column(String(255), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow,
    )


class AuditEvent(Base):
    """
    Журнал: кто, что, над кем, когда.

    actor_kind: admin | bot | system
    category:   moderation | economy | settings | broadcast | system | actions
    """

    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    chat_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)

    actor_kind: Mapped[str] = mapped_column(String(10), default="system")

    actor_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)

    actor_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    target_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)

    target_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    category: Mapped[str] = mapped_column(String(20), index=True)

    action: Mapped[str] = mapped_column(String(40), index=True)

    details: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class ChatWarning(Base):
    """Предупреждения участнику в группе."""

    __tablename__ = "warnings"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    chat_id: Mapped[int] = mapped_column(BigInteger, index=True)

    telegram_id: Mapped[int] = mapped_column(BigInteger, index=True)

    reason: Mapped[str | None] = mapped_column(String(255), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class AdminRole(Base):
    """
    Роль администратора в группе. Если записи нет — роль берётся
    из прав в Telegram: создатель → super_admin, админ → moderator.
    """

    __tablename__ = "admin_roles"

    __table_args__ = (
        UniqueConstraint("chat_id", "telegram_id", name="uq_admin_role"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    chat_id: Mapped[int] = mapped_column(BigInteger, index=True)

    telegram_id: Mapped[int] = mapped_column(BigInteger, index=True)

    role: Mapped[str] = mapped_column(String(20))

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class BotOwner(Base):
    """
    Главный админ бота: права как у создателя (OWNER_IDS) во всех группах
    и во всех разделах панели. Назначает и снимает только создатель.
    """

    __tablename__ = "bot_owners"

    telegram_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)

    name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    added_by: Mapped[int] = mapped_column(BigInteger)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class ActionToggle(Base):
    """Отключённые в группе действия."""

    __tablename__ = "action_toggles"

    __table_args__ = (
        UniqueConstraint("chat_id", "action_key", name="uq_action_toggle"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    chat_id: Mapped[int] = mapped_column(BigInteger, index=True)

    action_key: Mapped[str] = mapped_column(String(40))

    enabled: Mapped[bool] = mapped_column(Boolean, default=False)


class ActionUsage(Base):
    """Сколько раз действие срабатывало по дням."""

    __tablename__ = "action_usage"

    __table_args__ = (
        UniqueConstraint("chat_id", "action_key", "day", name="uq_action_usage"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    chat_id: Mapped[int] = mapped_column(BigInteger, index=True)

    action_key: Mapped[str] = mapped_column(String(40), index=True)

    day: Mapped[str] = mapped_column(String(10), index=True)

    count: Mapped[int] = mapped_column(default=0)


class HourlyStat(Base):
    """Сообщения по часам — для тепловой карты."""

    __tablename__ = "hourly_stats"

    __table_args__ = (
        UniqueConstraint("chat_id", "day", "hour", name="uq_hourly_stat"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    chat_id: Mapped[int] = mapped_column(BigInteger, index=True)

    day: Mapped[str] = mapped_column(String(10), index=True)

    hour: Mapped[int] = mapped_column()

    messages: Mapped[int] = mapped_column(default=0)


class Broadcast(Base):
    """
    Рассылка. status: scheduled | sent | failed | cancelled
    """

    __tablename__ = "broadcasts"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    author_id: Mapped[int] = mapped_column(BigInteger, index=True)

    author_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    chat_ids: Mapped[list] = mapped_column(JSON, default=list)

    text: Mapped[str] = mapped_column(Text)

    photo: Mapped[str | None] = mapped_column(Text, nullable=True)

    media_type: Mapped[str] = mapped_column(String(10), default="photo")

    # groups — в группы; dm — в личку тем, кто запускал бота
    mode: Mapped[str] = mapped_column(String(8), default="groups")

    segment: Mapped[dict] = mapped_column(JSON, default=dict)

    buttons: Mapped[list] = mapped_column(JSON, default=list)

    send_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)

    status: Mapped[str] = mapped_column(String(12), default="scheduled", index=True)

    sent: Mapped[int] = mapped_column(default=0)

    failed: Mapped[int] = mapped_column(default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class ActionCustom(Base):
    """
    Правки действий для конкретной группы — слой поверх каталога.

    kind:
        alias       — своё слово-триггер
        phrase      — своя фраза (шаблон с {actor}, {target_acc}…)
        image       — своя картинка: https-ссылка или data:-URL загрузки
        hide_image  — скрыть картинку из общей коллекции (value = id)
        cooldown    — задержка между срабатываниями, секунд
        image_mode  — mix (свои вперемешку с общими) | own (только свои)
    """

    __tablename__ = "action_custom"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    chat_id: Mapped[int] = mapped_column(BigInteger, index=True)

    action_key: Mapped[str] = mapped_column(String(40), index=True)

    kind: Mapped[str] = mapped_column(String(12), index=True)

    value: Mapped[str] = mapped_column(Text)

    file_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    shows: Mapped[int] = mapped_column(default=0)

    last_used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    author_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class ShopOverride(Base):
    """
    Правила магазина для группы: своя цена, доступность, остаток.
    price=None — цена из каталога; stock=None — без ограничений.
    """

    __tablename__ = "shop_overrides"

    __table_args__ = (
        UniqueConstraint("chat_id", "item_key", name="uq_shop_override"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    chat_id: Mapped[int] = mapped_column(BigInteger, index=True)

    item_key: Mapped[str] = mapped_column(String(40))

    price: Mapped[int | None] = mapped_column(nullable=True)

    enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    stock: Mapped[int | None] = mapped_column(nullable=True)


class AutoReply(Base):
    """
    Автоответ группы: на ключевое слово — заготовленная фраза.
    match: contains | exact | start
    """

    __tablename__ = "auto_replies"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    chat_id: Mapped[int] = mapped_column(BigInteger, index=True)

    trigger: Mapped[str] = mapped_column(String(100))

    response: Mapped[str] = mapped_column(Text)

    match: Mapped[str] = mapped_column(String(10), default="contains")

    probability: Mapped[int] = mapped_column(default=100)

    cooldown: Mapped[int] = mapped_column(default=30)

    enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    hits: Mapped[int] = mapped_column(default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class PunishRule(Base):
    """
    Свое правило наказания: «если [нарушение] N раз за M минут →
    [действие] на [срок]». Проверяются по порядку, срабатывает первое.
    violation = "any" — любое нарушение.
    """

    __tablename__ = "punish_rules"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    chat_id: Mapped[int] = mapped_column(BigInteger, index=True)

    position: Mapped[int] = mapped_column(default=0)

    violation: Mapped[str] = mapped_column(String(20))

    count: Mapped[int] = mapped_column(default=3)

    window_minutes: Mapped[int] = mapped_column(default=10)

    action: Mapped[str] = mapped_column(String(10))

    duration_minutes: Mapped[int] = mapped_column(default=60)

    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class LibraryImage(Base):
    """
    Своя коллекция картинок владельца. Фото хранятся в самом Telegram:
    здесь только file_id. tag — название коллекции: «пиво», «кошки».
    """

    __tablename__ = "library_images"

    __table_args__ = (
        UniqueConstraint("tag", "file_unique_id", name="uq_library_image"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    tag: Mapped[str] = mapped_column(String(40), index=True)

    file_id: Mapped[str] = mapped_column(String(255))

    file_unique_id: Mapped[str] = mapped_column(String(64))

    author_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    used: Mapped[bool] = mapped_column(Boolean, default=False)

    shows: Mapped[int] = mapped_column(default=0)

    last_used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class LibraryLink(Base):
    """К какому действию (или «cats» — котики) привязана коллекция."""

    __tablename__ = "library_links"

    __table_args__ = (
        UniqueConstraint("tag", "target", name="uq_library_link"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    tag: Mapped[str] = mapped_column(String(40), index=True)

    target: Mapped[str] = mapped_column(String(40), index=True)


class LibraryCollection(Base):
    """
    Коллекция как категория. Если as_action — она сама работает как
    действие: ответ человеку словом-триггером присылает фото из неё.
    """

    __tablename__ = "library_collections"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    tag: Mapped[str] = mapped_column(String(40), unique=True, index=True)

    emoji: Mapped[str] = mapped_column(String(16), default="✨")

    as_action: Mapped[bool] = mapped_column(Boolean, default=True)

    triggers: Mapped[list] = mapped_column(JSON, default=list)

    phrase: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class DailyUserStat(Base):
    """Сколько сообщений человек написал в группе за день (по местному времени группы)."""

    __tablename__ = "daily_user_stats"

    __table_args__ = (
        UniqueConstraint("chat_id", "day", "telegram_id", name="uq_daily_user_stat"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    chat_id: Mapped[int] = mapped_column(BigInteger, index=True)

    day: Mapped[str] = mapped_column(String(10), index=True)

    telegram_id: Mapped[int] = mapped_column(BigInteger, index=True)

    messages: Mapped[int] = mapped_column(default=0)


class Marriage(Base):
    """Брак в группе. active=False — развелись (история остаётся)."""

    __tablename__ = "marriages"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    chat_id: Mapped[int] = mapped_column(BigInteger, index=True)

    user1: Mapped[int] = mapped_column(BigInteger, index=True)

    user2: Mapped[int] = mapped_column(BigInteger, index=True)

    since: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)


class DailyPick(Base):
    """Выбор дня (пара дня): один раз в сутки по местному времени группы."""

    __tablename__ = "daily_picks"

    __table_args__ = (
        UniqueConstraint("chat_id", "day", "kind", name="uq_daily_pick"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    chat_id: Mapped[int] = mapped_column(BigInteger, index=True)

    day: Mapped[str] = mapped_column(String(10))

    kind: Mapped[str] = mapped_column(String(20))

    user1: Mapped[int] = mapped_column(BigInteger)

    user2: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    phrase: Mapped[str | None] = mapped_column(Text, nullable=True)


# Рыбалка. Старые таблицы fishing_players / fishing_catches от первой
# интеграции не трогаем: там алмазы, которые записывал сам клиент.

class FishingPlayer(Base):
    """Профиль рыбака. Алмазы и опыт — общие с Марой (user_profiles), здесь только снаряжение и улов."""

    __tablename__ = "fishing_profiles"

    telegram_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)

    location: Mapped[str] = mapped_column(String(20), default="quiet")

    rod: Mapped[str] = mapped_column(String(20), default="starter")

    rod_levels: Mapped[dict] = mapped_column(JSON, default=dict)

    owned_rods: Mapped[list] = mapped_column(JSON, default=list)

    reel: Mapped[str] = mapped_column(String(20), default="basic")

    owned_reels: Mapped[list] = mapped_column(JSON, default=list)

    bobber: Mapped[str] = mapped_column(String(20), default="wood")

    owned_bobbers: Mapped[list] = mapped_column(JSON, default=list)

    # Энергия хранится снимком: значение и момент, от которого идёт
    # восстановление. None — ещё не считали (запас полный).
    energy: Mapped[int | None] = mapped_column(nullable=True)

    energy_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    refills: Mapped[int] = mapped_column(default=0)

    refills_day: Mapped[str] = mapped_column(String(10), default="")

    boat: Mapped[str] = mapped_column(String(20), default="shore")

    owned_boats: Mapped[list] = mapped_column(JSON, default=list)

    bait: Mapped[str] = mapped_column(String(20), default="worm")

    bait_stock: Mapped[dict] = mapped_column(JSON, default=dict)

    caught: Mapped[int] = mapped_column(default=0)

    best: Mapped[float] = mapped_column(Float, default=0.0)

    legendary: Mapped[int] = mapped_column(default=0)

    night: Mapped[int] = mapped_column(default=0)

    species: Mapped[dict] = mapped_column(JSON, default=dict)

    lifetime_weight: Mapped[float] = mapped_column(Float, default=0.0)

    streak: Mapped[int] = mapped_column(default=0)

    last_day: Mapped[str] = mapped_column(String(10), default="")

    quests_day: Mapped[str] = mapped_column(String(10), default="")

    quests: Mapped[list] = mapped_column(JSON, default=list)

    chests: Mapped[int] = mapped_column(default=0)

    opened_chests: Mapped[int] = mapped_column(default=0)

    achievements: Mapped[list] = mapped_column(JSON, default=list)

    last_cast_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class FishingCast(Base):
    """
    Заброс. Рыбу и вес выбирает сервер в момент заброса — телефон
    игрока их не придумывает. resolved: заброс уже засчитан.
    """

    __tablename__ = "fishing_casts"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)

    telegram_id: Mapped[int] = mapped_column(BigInteger, index=True)

    chat_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    fish_key: Mapped[str] = mapped_column(String(20))

    weight: Mapped[float] = mapped_column(Float)

    length: Mapped[int] = mapped_column(default=0)

    trophy: Mapped[bool] = mapped_column(Boolean, default=False)

    location: Mapped[str] = mapped_column(String(20))

    bait: Mapped[str] = mapped_column(String(20))

    bite_delay: Mapped[float] = mapped_column(Float, default=1.0)

    resolved: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class FishingCatch(Base):
    """Засчитанный улов — для рекордов, топов и статистики."""

    __tablename__ = "fishing_log"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    telegram_id: Mapped[int] = mapped_column(BigInteger, index=True)

    chat_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)

    fish_key: Mapped[str] = mapped_column(String(20), index=True)

    weight: Mapped[float] = mapped_column(Float)

    trophy: Mapped[bool] = mapped_column(Boolean, default=False)

    reward: Mapped[int] = mapped_column(default=0)

    xp: Mapped[int] = mapped_column(default=0)

    location: Mapped[str] = mapped_column(String(20))

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
