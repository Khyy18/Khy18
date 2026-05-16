# Zenith Crypto Trading Bot

Multi-exchange crypto trading bot with AI-powered decision gates and risk management.

## Features

- **Multi-exchange support**: Bybit V5 and OKX via unified adapter interface
- **Multi-timeframe Donchian strategy**: 1m execution, 1h/4h signals, daily trend filter
- **AI gate modules**: macro sentinel (news blackout), regime classifier, weekly postmortem
- **LLM router**: Groq -> Cerebras -> Gemini fallback chain with circuit-breaker
- **Kill-switches**: daily (3%), weekly (7%), MDD (15%) loss limits
- **Correlation guard**: net beta exposure cap across portfolio
- **Vol-targeting**: 20% annualized portfolio volatility target
- **Telegram terminal**: full control panel for monitoring and manual overrides
- **Graceful degradation**: auto-pause on consecutive errors, auto-recovery probe

## Supported Symbols

BTCUSDT, ETHUSDT, SOLUSDT (configurable in config.py)

## Quick Start

1. Copy `.env.example` to `.env`:
   ```bash
   cp .env.example .env
   ```

2. Fill in your API keys and configuration in `.env`

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Run the bot:
   ```bash
   python main.py
   ```

## Configuration

All secrets are read from environment variables. Trading parameters (symbols, timeframes, risk limits) are defined in `config.py`.

## Deployment

See `deploy/` directory for Docker and systemd deployment options.
