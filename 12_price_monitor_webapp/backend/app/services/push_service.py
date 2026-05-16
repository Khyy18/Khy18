"""Push notification service via FCM."""
from __future__ import annotations


import logging

import httpx

from app.config import settings
from app.db.models import PushLog, User

logger = logging.getLogger(__name__)

class PushService:
    """Sends push notifications via Firebase Cloud Messaging."""

    async def send_push(
        self, user: User, title: str, body: str, db=None
    ) -> bool:
        """Send push notification to a single user."""
        if not user.fcm_token or not settings.fcm_server_key:
            return False

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    "https://fcm.googleapis.com/fcm/send",
                    headers={
                        "Authorization": f"key={settings.fcm_server_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "to": user.fcm_token,
                        "notification": {"title": title, "body": body},
                    },
                    timeout=10,
                )
                success = resp.status_code == 200
        except Exception as e:
            logger.error("FCM send failed for user %d: %s", user.id, e)
            success = False

        # Log the push
        if db:
            log = PushLog(user_id=user.id, title=title, body=body)
            db.add(log)
            await db.commit()

        return success

    async def send_bulk(self, users: list[User], title: str, body: str) -> int:
        """Send push notification to multiple users. Returns success count."""
        sent = 0
        for user in users:
            if await self.send_push(user, title, body):
                sent += 1
        return sent

push_service = PushService()
