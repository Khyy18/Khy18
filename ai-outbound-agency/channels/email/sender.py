import asyncio
import json
import logging
from datetime import date, timezone, datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

import aiosmtplib
import redis.asyncio as aioredis

logger = logging.getLogger(__name__)


class AsyncEmailSender:
    """Multi-domain email sender with rotation and daily limit tracking."""

    def __init__(
        self,
        smtp_accounts: list[dict[str, Any]],
        redis_url: str,
        reputation_tracker: Any | None = None,
    ) -> None:
        self._accounts = smtp_accounts
        self._redis = aioredis.from_url(redis_url, decode_responses=True)
        self._current_index = 0
        self._reputation_tracker = reputation_tracker

    async def _get_daily_send_count(self, domain: str) -> int:
        """Get the number of emails sent today for a domain."""
        key = f"email:sends:{domain}:{date.today().isoformat()}"
        count = await self._redis.get(key)
        return int(count) if count else 0

    async def _increment_send_count(self, domain: str) -> None:
        """Increment today's send counter for a domain."""
        key = f"email:sends:{domain}:{date.today().isoformat()}"
        pipe = self._redis.pipeline()
        pipe.incr(key)
        pipe.expire(key, 86400 * 2)  # Expire after 2 days
        await pipe.execute()

    async def _pick_account(self) -> dict[str, Any] | None:
        """Pick next available account using round-robin that hasn't hit daily limit."""
        total = len(self._accounts)
        for _ in range(total):
            account = self._accounts[self._current_index % total]
            self._current_index = (self._current_index + 1) % total
            domain = account["domain"]
            daily_limit = account.get("daily_limit", 50)
            current_count = await self._get_daily_send_count(domain)
            if current_count < daily_limit:
                # Check domain reputation if tracker is available
                if self._reputation_tracker is not None:
                    score = await self._reputation_tracker.get_reputation_score(domain)
                    if score < 60:
                        logger.warning(
                            "Domain %s skipped due to low reputation score: %d",
                            domain,
                            score,
                        )
                        continue
                return account
        return None

    def _inject_tracking(
        self,
        html_body: str,
        tracking_pixel_url: str | None = None,
        tracked_links: dict[str, str] | None = None,
    ) -> str:
        """Inject tracking pixel and rewrite tracked links in the HTML body."""
        body = html_body

        # Rewrite tracked links
        if tracked_links:
            for original_url, tracking_url in tracked_links.items():
                body = body.replace(original_url, tracking_url)

        # Inject tracking pixel at end of body
        if tracking_pixel_url:
            pixel_tag = (
                f'<img src="{tracking_pixel_url}" '
                f'width="1" height="1" style="display:none" alt="" />'
            )
            body = body + pixel_tag

        return body

    async def send_email(
        self,
        to: str,
        subject: str,
        html_body: str,
        message_id: str,
        tracking_pixel_url: str | None = None,
        tracked_links: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Send an email with domain rotation, tracking injection, and retry logic.

        Returns a dict with domain_used, message_id_header, and success status.
        """
        # Pre-send spam check
        from channels.email.spam_checker import SpamChecker

        checker = SpamChecker()
        spam_result = checker.check_message(subject, html_body)

        if spam_result.verdict == "blocked":
            logger.warning(
                "Email to %s blocked by spam checker (score=%.1f): %s",
                to,
                spam_result.score,
                [c.name for c in spam_result.breakdown],
            )
            return {
                "domain_used": None,
                "message_id_header": None,
                "success": False,
                "spam_blocked": True,
            }

        if spam_result.verdict == "warning":
            logger.warning(
                "Email to %s has spam warning (score=%.1f): %s",
                to,
                spam_result.score,
                [c.name for c in spam_result.breakdown],
            )

        account = await self._pick_account()
        if account is None:
            logger.warning("No available domain - all daily limits reached")
            return {
                "domain_used": None,
                "message_id_header": None,
                "success": False,
            }

        domain = account["domain"]

        # Check if domain is paused by bounce monitor
        if await self._is_domain_paused(domain):
            logger.warning("Domain %s is paused due to high bounce rate, skipping", domain)
            return {
                "domain_used": domain,
                "message_id_header": None,
                "success": False,
            }

        from_addr = f"{account['user']}@{domain}" if "@" not in account["user"] else account["user"]
        message_id_header = f"<{message_id}@{domain}>"

        # Inject tracking into body
        final_body = self._inject_tracking(html_body, tracking_pixel_url, tracked_links)

        # Build MIME message
        msg = MIMEMultipart("alternative")
        msg["From"] = from_addr
        msg["To"] = to
        msg["Subject"] = subject
        msg["Message-ID"] = message_id_header
        msg["Reply-To"] = from_addr
        msg.attach(MIMEText(final_body, "html"))

        # Retry logic with exponential backoff
        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                async with aiosmtplib.SMTP(
                    hostname=account["host"],
                    port=account["port"],
                    use_tls=True,
                ) as smtp:
                    await smtp.login(account["user"], account["password"])
                    await smtp.send_message(msg)

                await self._increment_send_count(domain)
                logger.info(
                    "Email sent to %s via %s (message_id=%s)",
                    to,
                    domain,
                    message_id,
                )
                return {
                    "domain_used": domain,
                    "message_id_header": message_id_header,
                    "success": True,
                }
            except aiosmtplib.SMTPResponseException as exc:
                if 550 <= exc.code <= 559:
                    # Hard bounce - record it
                    await self._record_bounce(domain, "hard")
                    logger.error(
                        "Permanent SMTP failure (%d) sending to %s via %s: %s",
                        exc.code,
                        to,
                        domain,
                        str(exc),
                    )
                    break
                elif exc.code >= 500:
                    logger.error(
                        "Permanent SMTP failure (%d) sending to %s via %s: %s",
                        exc.code,
                        to,
                        domain,
                        str(exc),
                    )
                    break
                wait_time = 2 ** attempt
                logger.warning(
                    "Transient SMTP error (%d) attempt %d/%d for %s: %s. Retrying in %ds...",
                    exc.code,
                    attempt + 1,
                    max_attempts,
                    domain,
                    str(exc),
                    wait_time,
                )
                if attempt < max_attempts - 1:
                    await asyncio.sleep(wait_time)
            except Exception as exc:
                wait_time = 2 ** attempt
                logger.warning(
                    "Send attempt %d/%d failed for %s: %s. Retrying in %ds...",
                    attempt + 1,
                    max_attempts,
                    domain,
                    str(exc),
                    wait_time,
                )
                if attempt < max_attempts - 1:
                    await asyncio.sleep(wait_time)

        logger.error("All send attempts failed for %s via %s", to, domain)
        return {
            "domain_used": domain,
            "message_id_header": message_id_header,
            "success": False,
        }

    async def send_email_from_domain(
        self,
        domain: str,
        to: str,
        subject: str,
        html_body: str,
        message_id: str,
        tracking_pixel_url: str | None = None,
        tracked_links: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Send an email from a specific domain, bypassing round-robin rotation.

        Used by warmup scheduler to ensure warmup sends go through the intended domain.
        """
        account = None
        for acct in self._accounts:
            if acct.get("domain") == domain:
                account = acct
                break

        if account is None:
            logger.warning("Domain %s not found in configured accounts", domain)
            return {
                "domain_used": None,
                "message_id_header": None,
                "success": False,
            }

        # Check if domain is paused by bounce monitor
        if await self._is_domain_paused(domain):
            logger.warning("Domain %s is paused due to high bounce rate, skipping", domain)
            return {
                "domain_used": domain,
                "message_id_header": None,
                "success": False,
            }

        # Check daily limit
        daily_limit = account.get("daily_limit", 50)
        current_count = await self._get_daily_send_count(domain)
        if current_count >= daily_limit:
            logger.warning("Domain %s has reached its daily limit", domain)
            return {
                "domain_used": domain,
                "message_id_header": None,
                "success": False,
            }

        from_addr = f"{account['user']}@{domain}" if "@" not in account["user"] else account["user"]
        message_id_header = f"<{message_id}@{domain}>"

        # Inject tracking into body
        final_body = self._inject_tracking(html_body, tracking_pixel_url, tracked_links)

        # Build MIME message
        msg = MIMEMultipart("alternative")
        msg["From"] = from_addr
        msg["To"] = to
        msg["Subject"] = subject
        msg["Message-ID"] = message_id_header
        msg["Reply-To"] = from_addr
        msg.attach(MIMEText(final_body, "html"))

        # Retry logic with exponential backoff
        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                async with aiosmtplib.SMTP(
                    hostname=account["host"],
                    port=account["port"],
                    use_tls=True,
                ) as smtp:
                    await smtp.login(account["user"], account["password"])
                    await smtp.send_message(msg)

                await self._increment_send_count(domain)
                logger.info(
                    "Email sent to %s via %s (pinned domain, message_id=%s)",
                    to,
                    domain,
                    message_id,
                )
                return {
                    "domain_used": domain,
                    "message_id_header": message_id_header,
                    "success": True,
                }
            except aiosmtplib.SMTPResponseException as exc:
                if 550 <= exc.code <= 559:
                    # Hard bounce - record it
                    await self._record_bounce(domain, "hard")
                    logger.error(
                        "Permanent SMTP failure (%d) sending to %s via %s: %s",
                        exc.code,
                        to,
                        domain,
                        str(exc),
                    )
                    break
                elif exc.code >= 500:
                    logger.error(
                        "Permanent SMTP failure (%d) sending to %s via %s: %s",
                        exc.code,
                        to,
                        domain,
                        str(exc),
                    )
                    break
                wait_time = 2 ** attempt
                logger.warning(
                    "Transient SMTP error (%d) attempt %d/%d for %s: %s. Retrying in %ds...",
                    exc.code,
                    attempt + 1,
                    max_attempts,
                    domain,
                    str(exc),
                    wait_time,
                )
                if attempt < max_attempts - 1:
                    await asyncio.sleep(wait_time)
            except Exception as exc:
                wait_time = 2 ** attempt
                logger.warning(
                    "Send attempt %d/%d failed for %s: %s. Retrying in %ds...",
                    attempt + 1,
                    max_attempts,
                    domain,
                    str(exc),
                    wait_time,
                )
                if attempt < max_attempts - 1:
                    await asyncio.sleep(wait_time)

        logger.error("All send attempts failed for %s via %s", to, domain)
        return {
            "domain_used": domain,
            "message_id_header": message_id_header,
            "success": False,
        }

    async def _is_domain_paused(self, domain: str) -> bool:
        """Check if a domain is paused by the bounce monitor."""
        pause_key = f"paused:{domain}"
        result = await self._redis.get(pause_key)
        return result == "1"

    async def _record_bounce(self, domain: str, bounce_type: str = "hard") -> None:
        """Record a bounce event via BounceMonitor, triggering auto-pause if needed."""
        from channels.email.bounce_monitor import BounceMonitor

        monitor = BounceMonitor.__new__(BounceMonitor)
        monitor._redis = self._redis
        await monitor.record_bounce(domain, bounce_type)

    async def close(self) -> None:
        """Close the Redis connection."""
        await self._redis.close()
