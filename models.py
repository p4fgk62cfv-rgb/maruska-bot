from datetime import datetime

from sqlalchemy import (
    BigInteger,
    String,
    Text,
    DateTime,
    UniqueConstraint,
    Boolean,
)

from sqlalchemy.orm import Mapped, mapped_column

from database.database import Base


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
        default=datetime.utcnow,
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
        default=datetime.utcnow,
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

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
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
        default=datetime.utcnow,
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

    joined_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
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
        default=datetime.utcnow,
        index=True,
    )


class ActionImage(Base):
    """
    Фотографии для действий.

    Один action = отдельная коллекция фотографий.

    used=False:
        фотография ещё не использовалась в текущем цикле.

    used=True:
        уже использовалась.
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

    photographer_name: Mapped[str] = mapped_column(
        String(255),
    )

    photographer_url: Mapped[str] = mapped_column(
        Text,
    )

    unsplash_url: Mapped[str] = mapped_column(
        Text,
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
        default=datetime.utcnow,
    )
