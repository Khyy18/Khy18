"""Employee ORM model."""

from sqlalchemy import Column, Float, Integer, String, Text
from sqlalchemy.sql import func

from backend.database import Base


class Employee(Base):
    __tablename__ = "employees"

    id = Column(Integer, primary_key=True, autoincrement=True)
    fio = Column(Text, nullable=False)
    position = Column(Text, nullable=False)
    rate = Column(Float, nullable=False, default=1.0)
    created_at = Column(String, server_default=func.now())
