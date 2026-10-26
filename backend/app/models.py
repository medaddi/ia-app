"""
Database tables.
  users          app accounts (username + access code) and each user's daily loss limit
  sessions       login tokens
  activation_keys / subscribers   Telegram access codes and the chats that activated one
  signals        every signal the strategies sent, with its tracked outcome (strategy win rate)
  trades         trades a user actually took (history, P&L, win rate per user)
  settings       app parameters (key → JSON value)
  watermarks     anti copy-trading log: which chat received which personal offset
"""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    access_code_hash: Mapped[str] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(16), default="user")  # admin | user
    daily_loss_limit: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # $; None = no limit
    risk_usd: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # $ risked per signal → the lot shown to this user
    # Legacy columns, no longer used (kept so existing databases keep working)
    capital: Mapped[float] = mapped_column(Float, default=0)
    risk_pct: Mapped[float] = mapped_column(Float, default=1)
    default_lot: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    telegram_chat_id: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class SessionToken(Base):
    __tablename__ = "sessions"
    token: Mapped[str] = mapped_column(String(80), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ActivationKey(Base):
    __tablename__ = "activation_keys"
    code: Mapped[str] = mapped_column(String(64), primary_key=True)
    label: Mapped[str] = mapped_column(String(120), default="")
    duration_hours: Mapped[int] = mapped_column(Integer, default=720)
    multi_use: Mapped[bool] = mapped_column(Boolean, default=False)
    used_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)


class Subscriber(Base):
    __tablename__ = "subscribers"
    chat_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    first_name: Mapped[str] = mapped_column(String(120), default="")
    code: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    activated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    capital: Mapped[float] = mapped_column(Float, default=0)
    risk_pct: Mapped[float] = mapped_column(Float, default=1)
    expired_notified: Mapped[bool] = mapped_column(Boolean, default=False)
    muted: Mapped[bool] = mapped_column(Boolean, default=False)  # /stop pauses signals, /resume turns them back on
    risk_usd: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # /risk 80 → each signal comes with the lot for $80


class Signal(Base):
    __tablename__ = "signals"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)  # strategy setup id
    symbol: Mapped[str] = mapped_column(String(16), index=True)
    setup: Mapped[str] = mapped_column(String(16))
    direction: Mapped[str] = mapped_column(String(8))
    entry_type: Mapped[str] = mapped_column(String(8))
    entry: Mapped[float] = mapped_column(Float)
    sl: Mapped[float] = mapped_column(Float)
    tp1: Mapped[float] = mapped_column(Float)
    tp2: Mapped[float] = mapped_column(Float)
    tp3: Mapped[float] = mapped_column(Float)
    rr_tp2: Mapped[float] = mapped_column(Float)
    score: Mapped[float] = mapped_column(Float)
    signal_time: Mapped[int] = mapped_column(Integer)  # unix seconds, close of the signal candle
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    recipients: Mapped[int] = mapped_column(Integer, default=0)
    latency_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    state: Mapped[str] = mapped_column(String(16), default="PENDING")  # lifecycle state
    outcome: Mapped[Optional[str]] = mapped_column(String(12), nullable=True)  # WIN | LOSS | BREAKEVEN
    r_multiple: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    exit_time: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    params: Mapped[dict] = mapped_column(JSON)  # replayable order parameters
    payload: Mapped[dict] = mapped_column(JSON)  # AISignal as shown in the app


class Trade(Base):
    __tablename__ = "trades"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    chat_id: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, index=True)
    signal_id: Mapped[Optional[str]] = mapped_column(String(80), nullable=True, index=True)
    symbol: Mapped[str] = mapped_column(String(16))
    direction: Mapped[str] = mapped_column(String(8))
    entry: Mapped[float] = mapped_column(Float)
    sl: Mapped[float] = mapped_column(Float)
    tp1: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    tp2: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    tp3: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    lots: Mapped[float] = mapped_column(Float)  # the lot the user really took
    capital: Mapped[float] = mapped_column(Float, default=0)  # legacy, unused
    risk_pct: Mapped[float] = mapped_column(Float, default=1)  # legacy, unused
    status: Mapped[str] = mapped_column(String(10), default="OPEN")  # OPEN | CLOSED
    result: Mapped[Optional[str]] = mapped_column(String(12), nullable=True)  # WIN | LOSS | BREAKEVEN
    exit_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    pnl: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # account currency
    r_multiple: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    breakeven: Mapped[bool] = mapped_column(Boolean, default=False)
    source: Mapped[str] = mapped_column(String(12), default="app")  # app | telegram
    notes: Mapped[str] = mapped_column(Text, default="")
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class Setting(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON)


class Watermark(Base):
    __tablename__ = "watermarks"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ref: Mapped[str] = mapped_column(String(8), index=True)
    chat_id: Mapped[str] = mapped_column(String(32))
    signal_id: Mapped[str] = mapped_column(String(80), index=True)
    symbol: Mapped[str] = mapped_column(String(16))
    offset: Mapped[float] = mapped_column(Float)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
