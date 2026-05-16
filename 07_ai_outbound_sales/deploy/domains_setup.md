# Domain Setup Guide

## Overview

Proper domain configuration is critical for email deliverability. This guide covers purchasing domains, setting up DNS records (SPF, DKIM, DMARC), and configuring them for use with AI Outbound Agency.

## Step 1: Purchase Domains

We recommend using 3-5 domains for rotation to protect your primary brand domain.

**Recommended registrars:**
- Namecheap (budget-friendly)
- Cloudflare Registrar (at cost)
- Google Domains

**Domain naming tips:**
- Use variations of your brand: `getacme.com`, `tryacme.io`, `acme-team.com`
- Avoid numbers, hyphens in the middle, or spammy-looking names
- Use `.com`, `.io`, or `.co` TLDs

## Step 2: DNS Records

### SPF Record

Add a TXT record to your domain's DNS:

```
Type: TXT
Host: @
Value: v=spf1 include:_spf.google.com include:your-smtp-provider.com ~all
```

Replace `your-smtp-provider.com` with your actual SMTP provider's SPF include.

### DKIM Record

Your SMTP provider will give you a DKIM key. Add it as a TXT record:

```
Type: TXT
Host: selector._domainkey
Value: v=DKIM1; k=rsa; p=YOUR_PUBLIC_KEY_HERE
```

The `selector` and public key come from your email provider.

### DMARC Record

```
Type: TXT
Host: _dmarc
Value: v=DMARC1; p=none; rua=mailto:dmarc-reports@yourdomain.com; pct=100
```

Start with `p=none` (monitoring only), then move to `p=quarantine` after 2 weeks, and finally `p=reject` after confirming no issues.

## Step 3: Namecheap Setup (Example)

1. Log in to Namecheap dashboard
2. Go to Domain List -> select your domain -> Manage
3. Click "Advanced DNS" tab
4. Add the SPF, DKIM, and DMARC TXT records listed above
5. Save changes (DNS propagation takes 1-48 hours)

## Step 4: Verify DNS Records

Use these tools to verify your records:

```bash
# Check SPF
dig TXT yourdomain.com +short

# Check DKIM
dig TXT selector._domainkey.yourdomain.com +short

# Check DMARC
dig TXT _dmarc.yourdomain.com +short
```

Online tools:
- [MXToolbox](https://mxtoolbox.com/SuperTool.aspx)
- [Mail-Tester](https://www.mail-tester.com/)

## Step 5: Domain Warmup

New domains need warming up before sending at volume. AI Outbound Agency handles this automatically:

1. Week 1: 5-10 emails/day per domain
2. Week 2: 20-30 emails/day per domain
3. Week 3: 50-75 emails/day per domain
4. Week 4+: Full volume (up to 100-150/day per domain)

The built-in warmup scheduler manages this progression automatically.

## Step 6: Configure in AI Outbound Agency

Update your `.env` file's `SMTP_DOMAINS` setting:

```json
SMTP_DOMAINS=[{"domain": "getacme.com", "host": "smtp.provider.com", "port": 587, "user": "user@getacme.com", "password": "xxx"}]
```

Multiple domains can be added to the array for automatic rotation.
