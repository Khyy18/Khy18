"""TimesheetMark ORM model."""

from sqlalchemy import Column, ForeignKey, Integer, Text

from backend.database import Base


class TimesheetMark(Base):
    __tablename__ = "timesheet_marks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False)
    date = Column(Text, nullable=False)
    mark_type = Column(Text, nullable=False)
