"""SQLAdmin panel setup with basic HTTP authentication."""

import os
from typing import Optional

from sqladmin import Admin, ModelView
from sqladmin.authentication import AuthenticationBackend
from starlette.requests import Request

from backend.database import engine
from backend.models.employee import Employee
from backend.models.child import Child
from backend.models.journal import JournalEntry
from backend.models.audit_log import AuditLog
from backend.models.reminder import Reminder
from backend.models.timesheet import TimesheetMark
from backend.models.payment import ParentPayment


# --- Authentication ---

class AdminAuth(AuthenticationBackend):
    """Basic session-based authentication for admin panel."""

    async def login(self, request: Request) -> bool:
        form = await request.form()
        username = form.get("username", "")
        password = form.get("password", "")

        admin_user = os.environ.get("ADMIN_USER", "admin")
        admin_password = os.environ.get("ADMIN_PASSWORD", "admin")

        if username == admin_user and password == admin_password:
            request.session.update({"authenticated": True})
            return True
        return False

    async def logout(self, request: Request) -> bool:
        request.session.clear()
        return True

    async def authenticate(self, request: Request) -> Optional[bool]:
        if request.session.get("authenticated"):
            return True
        return False


# --- Model Views ---

class EmployeeAdmin(ModelView, model=Employee):
    name = "Сотрудник"
    name_plural = "Сотрудники"
    column_list = [Employee.id, Employee.fio, Employee.position, Employee.rate]


class ChildAdmin(ModelView, model=Child):
    name = "Ребёнок"
    name_plural = "Дети"
    column_list = [
        Child.id, Child.child_fio, Child.group_name,
        Child.parent_fio, Child.discount_percent,
    ]


class JournalEntryAdmin(ModelView, model=JournalEntry):
    name = "Запись журнала"
    name_plural = "Журнал операций"
    column_list = [
        JournalEntry.id, JournalEntry.date, JournalEntry.amount,
        JournalEntry.entry_type, JournalEntry.counterparty,
    ]


class AuditLogAdmin(ModelView, model=AuditLog):
    name = "Запись аудита"
    name_plural = "Журнал аудита"
    column_list = [
        AuditLog.id, AuditLog.timestamp, AuditLog.user_id,
        AuditLog.action, AuditLog.entity_type,
    ]


class ReminderAdmin(ModelView, model=Reminder):
    name = "Напоминание"
    name_plural = "Напоминания"
    column_list = [
        Reminder.id, Reminder.name, Reminder.cron_type,
        Reminder.day_of_month, Reminder.enabled,
    ]


class TimesheetMarkAdmin(ModelView, model=TimesheetMark):
    name = "Отметка табеля"
    name_plural = "Табель"
    column_list = [
        TimesheetMark.id, TimesheetMark.employee_id,
        TimesheetMark.date, TimesheetMark.mark_type,
    ]


class ParentPaymentAdmin(ModelView, model=ParentPayment):
    name = "Родительская оплата"
    name_plural = "Родительские оплаты"
    column_list = [
        ParentPayment.id, ParentPayment.child_id,
        ParentPayment.month, ParentPayment.year,
        ParentPayment.amount_due, ParentPayment.amount_paid,
    ]


def setup_admin(app):
    """Mount SQLAdmin at /admin/ with authentication."""
    authentication_backend = AdminAuth(secret_key="admin-secret-key-change-me")
    admin = Admin(
        app,
        engine,
        base_url="/admin/",
        authentication_backend=authentication_backend,
        title="Детский сад - Админ",
    )

    admin.add_view(EmployeeAdmin)
    admin.add_view(ChildAdmin)
    admin.add_view(JournalEntryAdmin)
    admin.add_view(AuditLogAdmin)
    admin.add_view(ReminderAdmin)
    admin.add_view(TimesheetMarkAdmin)
    admin.add_view(ParentPaymentAdmin)
