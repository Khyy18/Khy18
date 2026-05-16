"""JournalEntry ORM model."""

from sqlalchemy import Column, Float, Integer, String, Text
from sqlalchemy.sql import func

from backend.database import Base


class JournalEntry(Base):
    __tablename__ = "journal_entries"

    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(Text, nullable=False)
    amount = Column(Float, nullable=False)
    entry_type = Column(Text, nullable=False)  # 'income' or 'expense'
    counterparty = Column(Text)
    basis = Column(Text)
    created_at = Column(String, server_default=func.now())
