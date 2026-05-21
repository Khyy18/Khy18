"""
Singleton экземпляр BillingWorker.
Вынесен в отдельный модуль для устранения циклических импортов:
app.main -> app.sessions.router -> app.main (billing_worker)
"""

from app.billing.worker import BillingWorker

billing_worker = BillingWorker()
