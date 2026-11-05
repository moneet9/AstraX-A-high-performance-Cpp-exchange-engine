from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str | None] = mapped_column(String(256), nullable=True)
    apple_subject: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    accounts: Mapped[list[Account]] = relationship(back_populates="user", cascade="all, delete-orphan")


class Account(Base):
    __tablename__ = "accounts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(80), default="Paper account")
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    cash_ticks: Mapped[int] = mapped_column(BigInteger, default=100_000_000)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    user: Mapped[User] = relationship(back_populates="accounts")


class Order(Base):
    __tablename__ = "orders"
    __table_args__ = (UniqueConstraint("account_id", "idempotency_key", name="uq_order_idempotency"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), index=True)
    symbol: Mapped[str] = mapped_column(String(24), index=True)
    side: Mapped[str] = mapped_column(String(4))
    order_type: Mapped[str] = mapped_column(String(16))
    tif: Mapped[str] = mapped_column(String(8), default="GTC")
    price_ticks: Mapped[int] = mapped_column(BigInteger, default=0)
    stop_price_ticks: Mapped[int] = mapped_column(BigInteger, default=0)
    peg_offset_ticks: Mapped[int] = mapped_column(BigInteger, default=0)
    quantity: Mapped[int] = mapped_column(BigInteger)
    filled_quantity: Mapped[int] = mapped_column(BigInteger, default=0)
    engine_order_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, unique=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="accepted", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Execution(Base):
    __tablename__ = "fills"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), index=True)
    price_ticks: Mapped[int] = mapped_column(BigInteger)
    quantity: Mapped[int] = mapped_column(BigInteger)
    side: Mapped[str] = mapped_column(String(4))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)


class Position(Base):
    __tablename__ = "positions"
    __table_args__ = (UniqueConstraint("account_id", "symbol", name="uq_position_account_symbol"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), index=True)
    symbol: Mapped[str] = mapped_column(String(24))
    quantity: Mapped[int] = mapped_column(BigInteger, default=0)
    average_price_ticks: Mapped[int] = mapped_column(BigInteger, default=0)
    realized_pnl_ticks: Mapped[int] = mapped_column(BigInteger, default=0)


class PushToken(Base):
    __tablename__ = "push_tokens"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token: Mapped[str] = mapped_column(String(256), unique=True)

