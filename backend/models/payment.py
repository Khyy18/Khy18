"""ParentPayment ORM model."""

from sqlalchemy import Column, Float, ForeignKey, Integer, String

from backend.database import Base


class ParentPayment(Base):
    __tablename__ = "parent_payments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    child_id = Column(Integer, ForeignKey("children.id"), nullable=False)
    month = Column(Integer)
    year = Column(Integer)
    attendance_days = Column(Integer)
    amount_due = Column(Float)
    amount_paid = Column(Float, default=0)
    paid_at = Column(String)
