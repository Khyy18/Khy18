# VPS Setup Guide

## Overview

This guide covers setting up a production VPS for AI Outbound Agency using Hetzner Cloud (recommended for value), though the steps apply to any Linux VPS provider.

## Step 1: Create VPS

### Hetzner Cloud

1. Create an account at [hetzner.com/cloud](https://www.hetzner.com/cloud)
2. Create a new project
3. Add a server:
   - Location: Choose nearest to your target audience
   - Image: Ubuntu 22.04
   - Type: CPX21 (3 vCPU, 4GB RAM) minimum for production
   - SSH Key: Add your public key
   - Networking: Enable IPv4 and IPv6

### Minimum Requirements

- 2 vCPU
- 4GB RAM
- 40GB SSD
- Ubuntu 22.04 LTS

## Step 2: Initial Server Setup

```bash
# SSH into your server
ssh root@YOUR_SERVER_IP

# Update system
apt update && apt upgrade -y

# Create a non-root user
adduser deploy
usermod -aG sudo deploy

# Copy SSH keys to new user
rsync --archive --chown=deploy:deploy ~/.ssh /home/deploy

# Switch to new user
su - deploy
```

## Step 3: Configure Firewall

```bash
# Install UFW
sudo apt install ufw -y

# Set defaults
sudo ufw default deny incoming
sudo ufw default allow outgoing

# Allow SSH, HTTP, HTTPS
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp

# Enable firewall
sudo ufw enable
sudo ufw status
```

## Step 4: Install Docker

```bash
# Install Docker
curl -fsSL https://get.docker.com | sh

# Add user to docker group
sudo usermod -aG docker deploy

# Log out and back in for group changes
exit
ssh deploy@YOUR_SERVER_IP

# Verify
docker --version
docker compose version
```

## Step 5: Install SSL (Let's Encrypt)

```bash
# Install Certbot
sudo apt install certbot -y

# Get certificate (replace with your domain)
sudo certbot certonly --standalone -d yourdomain.com -d www.yourdomain.com

# Auto-renewal is configured automatically
sudo certbot renew --dry-run
```

## Step 6: Clone and Deploy

```bash
# Clone the repository
git clone https://github.com/your-org/ai-outbound-agency.git
cd ai-outbound-agency

# Run the setup script
chmod +x deploy/setup.sh
./deploy/setup.sh
```

## Step 7: Configure Nginx (Optional Reverse Proxy)

```bash
sudo apt install nginx -y

# Create config
sudo tee /etc/nginx/sites-available/outbound << 'EOF'
server {
    listen 80;
    server_name yourdomain.com;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl;
    server_name yourdomain.com;

    ssl_certificate /etc/letsencrypt/live/yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/yourdomain.com/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
EOF

sudo ln -s /etc/nginx/sites-available/outbound /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

## Step 8: Monitoring

Set up basic monitoring:

```bash
# Install htop for process monitoring
sudo apt install htop -y

# Check Docker container health
docker compose ps
docker compose logs -f --tail=100
```

The built-in health monitor (`/health` endpoint) provides application-level monitoring. Configure Telegram alerts in your `.env` for real-time notifications.

## Maintenance

```bash
# Update application
git pull
docker compose build
docker compose up -d

# View logs
docker compose logs app --tail=200

# Database backup
docker compose exec db pg_dump -U postgres outbound > backup_$(date +%Y%m%d).sql
```
