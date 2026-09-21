from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    String,
    Text,
    DateTime,
    UniqueConstraint,
    Boolean,
)

from sqlalchemy.orm import Mapped, mapped_column

from database.database import Base, utcnow


class User(Base):
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
