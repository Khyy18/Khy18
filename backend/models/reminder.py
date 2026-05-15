"""Reminder ORM model."""

from sqlalchemy import Column, Integer, Text

from backend.database import Base


class Reminder(Base):
    __tablename__ = "reminders"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(Text, nullable=False)
    description = Column(Text)
    cron_type = Column(Text)
    day_of_month = Column(Integer)
    enabled = Column(Integer, default=1)
    chat_id = Column(Integer)
