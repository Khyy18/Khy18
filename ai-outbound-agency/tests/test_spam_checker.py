"""Tests for the SpamChecker class."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from channels.email.spam_checker import SpamChecker, SpamCheckResult


@pytest.fixture
def checker() -> SpamChecker:
    """Return a SpamChecker instance."""
    return SpamChecker()


class TestSpamChecker:
    """Tests for SpamChecker.check_message()."""

    def test_clean_email_passes(self, checker: SpamChecker) -> None:
        """A clean, well-formatted email should pass with score < 3."""
        result = checker.check_message(
            subject="Quick sync",
            html_body="<p>Hi John, wanted to follow up on our conversation.</p>",
        )
        assert result.score < 3
        assert result.verdict == "send"

    def test_spam_words_detected(self, checker: SpamChecker) -> None:
        """Trigger words should add their respective weights to the score."""
        result = checker.check_message(
            subject="Free guarantee",
            html_body="<p>This is a urgent message. Act now for limited time offer.</p>",
        )
        # free=1, guarantee=2, urgent=3, act now=3, limited time=2 = 11
        breakdown_names = [c.name for c in result.breakdown]
        assert "spam_trigger_words" in breakdown_names
        trigger_check = next(c for c in result.breakdown if c.name == "spam_trigger_words")
        assert trigger_check.score >= 5

    def test_all_caps_subject(self, checker: SpamChecker) -> None:
        """A subject that is >50% uppercase should get +3."""
        result = checker.check_message(
            subject="THIS IS AN IMPORTANT MESSAGE",
            html_body="<p>Normal body text here.</p>",
        )
        breakdown_names = [c.name for c in result.breakdown]
        assert "all_caps_subject" in breakdown_names
        caps_check = next(c for c in result.breakdown if c.name == "all_caps_subject")
        assert caps_check.score == 3

    def test_excessive_punctuation(self, checker: SpamChecker) -> None:
        """Excessive punctuation (!!!, ???) should add +2."""
        result = checker.check_message(
            subject="Amazing deal!!!",
            html_body="<p>You won't believe this??? Act fast!!!</p>",
        )
        breakdown_names = [c.name for c in result.breakdown]
        assert "excessive_punctuation" in breakdown_names
        punct_check = next(c for c in result.breakdown if c.name == "excessive_punctuation")
        assert punct_check.score == 2

    def test_high_html_ratio(self, checker: SpamChecker) -> None:
        """Body with >60% HTML tags should get +2."""
        # Create a body where tags far exceed text
        html_body = '<div class="wrapper"><table><tr><td><span><a href="x"></a></span></td></tr></table></div>x'
        result = checker.check_message(
            subject="Hello",
            html_body=html_body,
        )
        breakdown_names = [c.name for c in result.breakdown]
        assert "high_html_ratio" in breakdown_names
        html_check = next(c for c in result.breakdown if c.name == "high_html_ratio")
        assert html_check.score == 2

    def test_high_link_density(self, checker: SpamChecker) -> None:
        """More than 3 links per 100 words should get +2."""
        # Create body with many links and few words
        links = '<a href="http://x.com">link</a> ' * 5
        html_body = f"<p>{links} word1 word2</p>"
        result = checker.check_message(
            subject="Hello",
            html_body=html_body,
        )
        breakdown_names = [c.name for c in result.breakdown]
        assert "high_link_density" in breakdown_names
        link_check = next(c for c in result.breakdown if c.name == "high_link_density")
        assert link_check.score == 2

    def test_heavy_images(self, checker: SpamChecker) -> None:
        """More than 3 img tags should get +1."""
        imgs = '<img src="a.png" /> ' * 5
        html_body = f"<p>Some text {imgs}</p>"
        result = checker.check_message(
            subject="Hello",
            html_body=html_body,
        )
        breakdown_names = [c.name for c in result.breakdown]
        assert "heavy_images" in breakdown_names
        img_check = next(c for c in result.breakdown if c.name == "heavy_images")
        assert img_check.score == 1

    def test_unsubscribe_bonus(self, checker: SpamChecker) -> None:
        """Unsubscribe link should reduce score by 3."""
        result = checker.check_message(
            subject="Hello",
            html_body='<p>Content here.</p><a href="/unsub">Unsubscribe</a>',
        )
        breakdown_names = [c.name for c in result.breakdown]
        assert "unsubscribe_present" in breakdown_names
        unsub_check = next(c for c in result.breakdown if c.name == "unsubscribe_present")
        assert unsub_check.score == -3

    def test_personalization_bonus(self, checker: SpamChecker) -> None:
        """Personalization tokens should reduce score by 2."""
        result = checker.check_message(
            subject="Hi {{first_name}}",
            html_body="<p>Hello, I wanted to reach out.</p>",
        )
        breakdown_names = [c.name for c in result.breakdown]
        assert "personalization_present" in breakdown_names
        pers_check = next(c for c in result.breakdown if c.name == "personalization_present")
        assert pers_check.score == -2

    def test_short_subject_bonus(self, checker: SpamChecker) -> None:
        """Subject under 50 chars should reduce score by 1."""
        result = checker.check_message(
            subject="Quick chat",
            html_body="<p>Body text here.</p>",
        )
        breakdown_names = [c.name for c in result.breakdown]
        assert "short_subject" in breakdown_names
        short_check = next(c for c in result.breakdown if c.name == "short_subject")
        assert short_check.score == -1

    def test_blocked_threshold(self, checker: SpamChecker) -> None:
        """Score >5 should return 'blocked' verdict."""
        result = checker.check_message(
            subject="FREE URGENT WINNER!!!",
            html_body="<p>Congratulations! You are the winner! Act now! Click here for your guarantee!</p>",
        )
        assert result.score > 5
        assert result.verdict == "blocked"

    def test_warning_threshold(self, checker: SpamChecker) -> None:
        """Score 3-5 should return 'warning' verdict."""
        # "urgent" = +3, short subject = -1, personalization = -2 => 0
        # Let's target exactly a warning range: all caps subject (+3) with personalization (-2) + short subject (-1) = 0... no
        # Better approach: use a subject that triggers caps (+3) and body that adds punctuation (+2) 
        # but also has unsubscribe (-3) => net = 2... still not warning
        # Try: caps (+3) + punctuation (+2) + unsub (-3) + short_subject(-1) + personalization(-2) = -1... 
        # Try: trigger word "urgent" in body (+3) + excessive_punctuation (+2) + unsubscribe (-3) + short_subject (-1) = 1... too low
        # Try: "guarantee" (+2) + "limited time" (+2) + short_subject(-1) = 3 => warning
        result = checker.check_message(
            subject="Offer",
            html_body="<p>We guarantee this limited time deal is worth your time.</p>",
        )
        assert 3 <= result.score <= 5
        assert result.verdict == "warning"

    @pytest.mark.asyncio
    async def test_domain_auth_check(self) -> None:
        """verify_domain_auth should detect SPF/DKIM/DMARC via dns.resolver."""
        checker = SpamChecker()

        mock_spf_rdata = MagicMock()
        mock_spf_rdata.to_text.return_value = '"v=spf1 include:_spf.google.com ~all"'

        mock_dkim_rdata = MagicMock()
        mock_dkim_rdata.to_text.return_value = '"v=DKIM1; k=rsa; p=MIGfMA0..."'

        mock_dmarc_rdata = MagicMock()
        mock_dmarc_rdata.to_text.return_value = '"v=DMARC1; p=reject; rua=mailto:dmarc@example.com"'

        def mock_resolve(domain, record_type):
            if record_type == "TXT":
                if domain == "example.com":
                    return [mock_spf_rdata]
                elif domain == "selector1._domainkey.example.com":
                    return [mock_dkim_rdata]
                elif domain == "_dmarc.example.com":
                    return [mock_dmarc_rdata]
            return []

        with patch("dns.resolver.resolve", side_effect=mock_resolve):
            result = await checker.verify_domain_auth("example.com")

        assert result["spf"]["found"] is True
        assert result["dkim"]["found"] is True
        assert result["dmarc"]["found"] is True
        assert result["all_passed"] is True

    @pytest.mark.asyncio
    async def test_domain_auth_check_missing_records(self) -> None:
        """verify_domain_auth should handle missing DNS records."""
        import dns.resolver

        checker = SpamChecker()

        def mock_resolve(domain, record_type):
            raise dns.resolver.NXDOMAIN()

        with patch("dns.resolver.resolve", side_effect=mock_resolve):
            result = await checker.verify_domain_auth("nodns.example.com")

        assert result["spf"]["found"] is False
        assert result["dkim"]["found"] is False
        assert result["dmarc"]["found"] is False
        assert result["all_passed"] is False
