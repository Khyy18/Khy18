"""Bounce Monitor - tracks bounce rates, pauses unhealthy domains, DNS health checks."""

from __future__ import annotations

import logging
import socket
from datetime import date
from typing import Any

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)


class BounceMonitor:
    """Monitors email bounce rates and domain health for deliverability management."""

    def __init__(self, redis_url: str) -> None:
        self._redis = aioredis.from_url(redis_url, decode_responses=True)

    async def record_bounce(self, domain: str, bounce_type: str = "hard") -> None:
        """Record a bounce event for a domain.

        Args:
            domain: The sending domain.
            bounce_type: Either 'hard' or 'soft'.
        """
        today = date.today().isoformat()
        bounce_key = f"bounces:{domain}:{today}"
        consecutive_key = f"consecutive_hard:{domain}"

        pipe = self._redis.pipeline()
        pipe.incr(bounce_key)
        pipe.expire(bounce_key, 86400 * 7)  # Keep for 7 days

        if bounce_type == "hard":
            pipe.incr(consecutive_key)
            pipe.expire(consecutive_key, 86400 * 7)
        else:
            # Soft bounce resets consecutive hard bounce counter
            pipe.set(consecutive_key, 0)
            pipe.expire(consecutive_key, 86400 * 7)

        await pipe.execute()

        # Check if domain should be paused
        if await self.should_pause_domain(domain):
            await self.pause_domain(domain)

    async def record_send(self, domain: str) -> None:
        """Record a successful send for a domain.

        Args:
            domain: The sending domain.
        """
        today = date.today().isoformat()
        send_key = f"sends:{domain}:{today}"

        pipe = self._redis.pipeline()
        pipe.incr(send_key)
        pipe.expire(send_key, 86400 * 7)
        await pipe.execute()

        # Reset consecutive hard bounce counter on successful send
        consecutive_key = f"consecutive_hard:{domain}"
        await self._redis.set(consecutive_key, 0)
        await self._redis.expire(consecutive_key, 86400 * 7)

    async def get_bounce_rate(self, domain: str) -> float:
        """Calculate the bounce rate for a domain today.

        Args:
            domain: The sending domain.

        Returns:
            Bounce rate as a float between 0.0 and 1.0.
        """
        today = date.today().isoformat()
        bounce_key = f"bounces:{domain}:{today}"
        send_key = f"sends:{domain}:{today}"

        bounces = await self._redis.get(bounce_key)
        sends = await self._redis.get(send_key)

        bounce_count = int(bounces) if bounces else 0
        send_count = int(sends) if sends else 0

        if send_count == 0:
            return 0.0

        return bounce_count / send_count

    async def check_domain_health(self, domain: str) -> dict[str, Any]:
        """Check overall domain health metrics.

        Args:
            domain: The sending domain.

        Returns:
            Dict with is_paused, bounce_rate, and consecutive_hard_bounces.
        """
        consecutive_key = f"consecutive_hard:{domain}"
        consecutive_raw = await self._redis.get(consecutive_key)
        consecutive_hard = int(consecutive_raw) if consecutive_raw else 0

        return {
            "is_paused": await self.is_domain_paused(domain),
            "bounce_rate": await self.get_bounce_rate(domain),
            "consecutive_hard_bounces": consecutive_hard,
        }

    async def should_pause_domain(self, domain: str) -> bool:
        """Determine if a domain should be paused based on bounce metrics.

        A domain should be paused if:
        - Bounce rate > 5% with at least 20 sends, OR
        - More than 3 consecutive hard bounces

        Args:
            domain: The sending domain.

        Returns:
            True if the domain should be paused.
        """
        today = date.today().isoformat()
        send_key = f"sends:{domain}:{today}"
        sends_raw = await self._redis.get(send_key)
        send_count = int(sends_raw) if sends_raw else 0

        # Check bounce rate with minimum send threshold
        if send_count >= 20:
            bounce_rate = await self.get_bounce_rate(domain)
            if bounce_rate > 0.05:
                return True

        # Check consecutive hard bounces
        consecutive_key = f"consecutive_hard:{domain}"
        consecutive_raw = await self._redis.get(consecutive_key)
        consecutive_hard = int(consecutive_raw) if consecutive_raw else 0

        if consecutive_hard > 3:
            return True

        return False

    async def pause_domain(self, domain: str) -> None:
        """Pause a domain to prevent further sends.

        Args:
            domain: The sending domain to pause.
        """
        pause_key = f"paused:{domain}"
        await self._redis.set(pause_key, "1")
        # Pause for 24 hours by default
        await self._redis.expire(pause_key, 86400)
        logger.warning("Domain %s has been paused due to high bounce rate", domain)

    async def is_domain_paused(self, domain: str) -> bool:
        """Check if a domain is currently paused.

        Args:
            domain: The sending domain.

        Returns:
            True if the domain is paused.
        """
        pause_key = f"paused:{domain}"
        result = await self._redis.get(pause_key)
        return result == "1"

    async def unpause_domain(self, domain: str) -> None:
        """Unpause a domain to allow sends again.

        Args:
            domain: The sending domain to unpause.
        """
        pause_key = f"paused:{domain}"
        await self._redis.delete(pause_key)
        logger.info("Domain %s has been unpaused", domain)

    async def dns_health_check(self, domain: str) -> dict[str, Any]:
        """Check DNS records for email authentication (SPF, DKIM, DMARC).

        Args:
            domain: The domain to check.

        Returns:
            Dict with spf, dkim, and dmarc status and records.
        """
        import dns.resolver

        result: dict[str, Any] = {
            "spf": {"found": False, "record": None},
            "dkim": {"found": False, "record": None},
            "dmarc": {"found": False, "record": None},
        }

        # Check SPF (TXT record with v=spf1)
        try:
            answers = dns.resolver.resolve(domain, "TXT")
            for rdata in answers:
                txt_value = rdata.to_text().strip('"')
                if txt_value.startswith("v=spf1"):
                    result["spf"] = {"found": True, "record": txt_value}
                    break
        except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN, dns.resolver.NoNameservers, Exception) as exc:
            logger.debug("SPF check failed for %s: %s", domain, exc)

        # Check DKIM (selector._domainkey.domain TXT)
        dkim_domain = f"selector1._domainkey.{domain}"
        try:
            answers = dns.resolver.resolve(dkim_domain, "TXT")
            for rdata in answers:
                txt_value = rdata.to_text().strip('"')
                if "DKIM" in txt_value.upper() or "v=DKIM1" in txt_value or "k=" in txt_value:
                    result["dkim"] = {"found": True, "record": txt_value}
                    break
            # If we got any answer, consider DKIM present
            if not result["dkim"]["found"] and answers:
                txt_value = answers[0].to_text().strip('"')
                result["dkim"] = {"found": True, "record": txt_value}
        except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN, dns.resolver.NoNameservers, Exception) as exc:
            logger.debug("DKIM check failed for %s: %s", dkim_domain, exc)

        # Check DMARC (_dmarc.domain TXT)
        dmarc_domain = f"_dmarc.{domain}"
        try:
            answers = dns.resolver.resolve(dmarc_domain, "TXT")
            for rdata in answers:
                txt_value = rdata.to_text().strip('"')
                if txt_value.startswith("v=DMARC1"):
                    result["dmarc"] = {"found": True, "record": txt_value}
                    break
        except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN, dns.resolver.NoNameservers, Exception) as exc:
            logger.debug("DMARC check failed for %s: %s", dmarc_domain, exc)

        return result

    async def check_blacklist(self, domain: str) -> dict[str, Any]:
        """Check if a domain's IP is listed on Spamhaus ZEN DNSBL.

        Args:
            domain: The domain to check.

        Returns:
            Dict with is_listed and details.
        """
        result: dict[str, Any] = {
            "is_listed": False,
            "details": None,
        }

        try:
            # Resolve domain to IP
            import dns.resolver

            try:
                answers = dns.resolver.resolve(domain, "A")
                if not answers:
                    return result
                ip_address = str(answers[0])
            except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN, Exception):
                return result

            # Reverse the IP for DNSBL lookup
            reversed_ip = ".".join(reversed(ip_address.split(".")))
            lookup = f"{reversed_ip}.zen.spamhaus.org"

            try:
                bl_answers = dns.resolver.resolve(lookup, "A")
                if bl_answers:
                    result["is_listed"] = True
                    result["details"] = f"IP {ip_address} listed in Spamhaus ZEN: {[str(r) for r in bl_answers]}"
            except dns.resolver.NXDOMAIN:
                # Not listed - this is the expected case
                pass
            except (dns.resolver.NoAnswer, dns.resolver.NoNameservers, Exception) as exc:
                logger.debug("Blacklist check inconclusive for %s: %s", domain, exc)

        except Exception as exc:
            logger.error("Blacklist check failed for %s: %s", domain, exc)

        return result

    async def close(self) -> None:
        """Close the Redis connection."""
        await self._redis.close()
