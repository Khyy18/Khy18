"""Audit log ORM model."""

from sqlalchemy import Column, Integer, String, Text, DateTime
from sqlalchemy.sql import func

from backend.database import Base


class AuditLog(Base):
    __tablename__ = "audit_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, server_default=func.now(), nullable=False)
    user_id = Column(String, nullable=True)
    action = Column(String, nullable=False)  # POST, PUT, DELETE
    entity_type = Column(String, nullable=True)  # e.g. employees, children
    entity_id = Column(String, nullable=True)
    old_value = Column(Text, nullable=True)  # JSON string
    new_value = Column(Text, nullable=True)  # JSON string
    ip_address = Column(String, nullable=True)
