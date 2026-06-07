"""SQLite database layer using SQLAlchemy ORM."""
from __future__ import annotations

import datetime
from pathlib import Path

from sqlalchemy import (
    Boolean, Column, DateTime, Float, Integer, String,
    create_engine, func,
)
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from utils.config import get_config


class Base(DeclarativeBase):
    pass


class EyeSession(Base):
    __tablename__ = "eye_sessions"
    id = Column(Integer, primary_key=True, autoincrement=True)
    started_at = Column(DateTime, default=datetime.datetime.utcnow)
    ended_at = Column(DateTime, nullable=True)
    duration_minutes = Column(Float, default=0.0)
    blink_count = Column(Integer, default=0)
    avg_blink_rate = Column(Float, default=0.0)
    avg_distance_cm = Column(Float, default=0.0)
    breaks_taken = Column(Integer, default=0)
    breaks_missed = Column(Integer, default=0)
    posture_alerts = Column(Integer, default=0)


class EyeScore(Base):
    __tablename__ = "eye_scores"
    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(DateTime, default=datetime.datetime.utcnow)
    overall_score = Column(Float, default=0.0)
    blink_score = Column(Float, default=0.0)
    session_score = Column(Float, default=0.0)
    distance_score = Column(Float, default=0.0)
    break_score = Column(Float, default=0.0)
    ambient_score = Column(Float, default=0.0)
    screen_time_minutes = Column(Float, default=0.0)
    strain_risk = Column(String, default="Low")


class NotificationLog(Base):
    __tablename__ = "notification_log"
    id = Column(Integer, primary_key=True, autoincrement=True)
    sent_at = Column(DateTime, default=datetime.datetime.utcnow)
    category = Column(String)
    message = Column(String)
    acknowledged = Column(Boolean, default=False)


class PostureEvent(Base):
    __tablename__ = "posture_events"
    id = Column(Integer, primary_key=True, autoincrement=True)
    recorded_at = Column(DateTime, default=datetime.datetime.utcnow)
    head_offset = Column(Float, default=0.0)
    alert_type = Column(String)


class DatabaseManager:
    _instance: DatabaseManager | None = None

    def __init__(self) -> None:
        cfg = get_config()
        db_path = Path(cfg.database["path"])
        db_path.parent.mkdir(parents=True, exist_ok=True)
        engine = create_engine(f"sqlite:///{db_path}", echo=False)
        Base.metadata.create_all(engine)
        self._SessionLocal = sessionmaker(bind=engine, autoflush=True, autocommit=False)

    @classmethod
    def get_instance(cls) -> "DatabaseManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def get_session(self) -> Session:
        return self._SessionLocal()

    def start_session(self) -> int:
        with self.get_session() as s:
            rec = EyeSession(started_at=datetime.datetime.utcnow())
            s.add(rec)
            s.commit()
            s.refresh(rec)
            return rec.id

    def end_session(self, session_id: int, **kwargs) -> None:
        with self.get_session() as s:
            rec = s.get(EyeSession, session_id)
            if rec:
                rec.ended_at = datetime.datetime.utcnow()
                started = rec.started_at or datetime.datetime.utcnow()
                rec.duration_minutes = (
                    datetime.datetime.utcnow() - started
                ).total_seconds() / 60
                for k, v in kwargs.items():
                    setattr(rec, k, v)
                s.commit()

    def save_score(self, score_data: dict) -> None:
        with self.get_session() as s:
            s.add(EyeScore(**score_data))
            s.commit()

    def log_notification(self, category: str, message: str) -> None:
        with self.get_session() as s:
            s.add(NotificationLog(category=category, message=message))
            s.commit()

    def log_posture_event(self, head_offset: float, alert_type: str) -> None:
        with self.get_session() as s:
            s.add(PostureEvent(head_offset=head_offset, alert_type=alert_type))
            s.commit()

    def get_today_summary(self) -> dict:
        today = datetime.date.today()
        with self.get_session() as s:
            sessions = (
                s.query(EyeSession)
                .filter(func.date(EyeSession.started_at) == today.isoformat())
                .all()
            )
            score_row = (
                s.query(EyeScore)
                .filter(func.date(EyeScore.date) == today.isoformat())
                .order_by(EyeScore.date.desc())
                .first()
            )
        return {
            "screen_time_minutes": sum(s.duration_minutes or 0 for s in sessions),
            "blink_count": sum(s.blink_count or 0 for s in sessions),
            "breaks_taken": sum(s.breaks_taken or 0 for s in sessions),
            "posture_alerts": sum(s.posture_alerts or 0 for s in sessions),
            "overall_score": score_row.overall_score if score_row else 0.0,
            "strain_risk": score_row.strain_risk if score_row else "Unknown",
        }

    def get_weekly_scores(self) -> list[dict]:
        from datetime import timedelta
        today = datetime.date.today()
        week_ago = today - timedelta(days=7)
        with self.get_session() as s:
            rows = (
                s.query(EyeScore)
                .filter(EyeScore.date >= week_ago.isoformat())
                .order_by(EyeScore.date.asc())
                .all()
            )
        return [
            {
                "date": r.date.strftime("%a"),
                "overall_score": r.overall_score,
                "blink_score": r.blink_score,
                "break_score": r.break_score,
                "strain_risk": r.strain_risk,
            }
            for r in rows
        ]
