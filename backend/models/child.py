"""Child ORM model."""

from sqlalchemy import Column, Float, Integer, String, Text
from sqlalchemy.sql import func

from backend.database import Base


class Child(Base):
    __tablename__ = "children"

    id = Column(Integer, primary_key=True, autoincrement=True)
    child_fio = Column(Text, nullable=False)
    group_name = Column(Text, nullable=False)
    parent_fio = Column(Text, nullable=False)
    discount_percent = Column(Float, default=0)
    created_at = Column(String, server_default=func.now())
