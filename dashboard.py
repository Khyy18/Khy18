"""Веб-дашборд Zenith-Control Ultimate (read-only).

Простой aiohttp HTTP-сервер на DASHBOARD_PORT (env, default 8080).
Не требует авторизации — предполагается, что доступ закрыт на уровне
firewall VPS (только localhost или vpn). Для публичного хостинга добавьте
basic-auth или reverse-proxy с паролем.

Эндпоинты:
  GET /           — HTML-страница дашборда (авторефреш 10с)
  GET /health     — простой 200 OK {"status": "ok"} для health-check Docker
  GET /api/status — JSON: глобальное состояние бота
  GET /api/positions — JSON: открытые позиции по символам
  GET /api/equity — JSON: последние N точек кривой эквити
  GET /api/funding — JSON: последний funding-снапшот
  GET /api/arb    — JSON: активная арб-позиция + статистика
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, Optional

import aiohttp
from aiohttp import web

import arb_storage
import memory

_state_ref: Optional[dict[str, Any]] = None


def _utc_now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat(timespec="seconds")


def set_state(state: dict[str, Any]) -> None:
    """Вызывается из main.py при старте, чтобы дашборд читал живой state."""
    global _state_ref
    _state_ref = state


def _g() -> dict[str, Any]:
    if _state_ref is None:
        return {}
    return _state_ref.get("global") or {}


def _symbols_state() -> dict[str, Any]:
    if _state_ref is None:
        return {}
    return _state_ref.get("symbols") or {}


async def handle_health(request: web.Request) -> web.Response:
    return web.json_response({"status": "ok", "ts": _utc_now_iso()})


async def handle_status(request: web.Request) -> web.Response:
    g = _g()
    data = {
        "bot_running": bool(g.get("bot_running", False)),
        "kill_switch_state": str(g.get("kill_switch_state") or "NONE"),
        "kill_until_utc": g.get("kill_until_utc"),
        "blackout": bool((g.get("blackout") or {}).get("blackout", False)),
        "blackout_reason": str((g.get("blackout") or {}).get("reason") or ""),
        "degraded": bool(g.get("degraded", False)),
        "degraded_reason": str(g.get("degraded_reason") or ""),
        "equity_start": g.get("equity_start"),
        "daily_pnl": float(g.get("daily_pnl") or 0.0),
        "weekly_pnl": float(g.get("weekly_pnl") or 0.0),
        "cumulative_pnl": float(g.get("cumulative_pnl") or 0.0),
        "hwm": float(g.get("hwm") or 0.0),
        "ts": _utc_now_iso(),
    }
    return web.json_response(data)


async def handle_positions(request: web.Request) -> web.Response:
    syms = _symbols_state()
    positions = []
    for symbol, sym_state in syms.items():
        trade = sym_state.get("open_trade")
        if trade:
            positions.append({
                "symbol": symbol,
                "side": trade.get("side"),
                "entry_price": trade.get("entry_price"),
                "qty": trade.get("qty"),
                "current_stop": trade.get("current_stop"),
                "entry_ts_iso": trade.get("entry_ts_iso"),
                "high_since_entry": trade.get("high_since_entry"),
                "low_since_entry": trade.get("low_since_entry"),
            })
        regime = sym_state.get("regime") or {}
        positions.append({
            "symbol": symbol,
            "open": trade is not None,
            "regime": regime.get("regime"),
            "regime_confidence": regime.get("confidence"),
        }) if not trade else None

    open_only = [p for p in positions if p.get("open")]
    regime_only = [p for p in positions if not p.get("open") and "regime" in p]
    return web.json_response({
        "open_positions": open_only,
        "regimes": regime_only,
        "ts": _utc_now_iso(),
    })


async def handle_equity(request: web.Request) -> web.Response:
    limit = int(request.rel_url.query.get("limit", "50"))
    limit = max(1, min(500, limit))
    try:
        rows = memory.get_equity_curve(limit)
    except Exception:
        rows = []
    return web.json_response({"equity": rows, "ts": _utc_now_iso()})


async def handle_funding(request: web.Request) -> web.Response:
    g = _g()
    snap = g.get("funding_snapshot")
    if not snap:
        return web.json_response({"error": "нет данных — funding-сканер ещё не запускался"})

    result: dict[str, Any] = {}
    for ex_name, snaps in snap.items():
        result[ex_name] = []
        for s in snaps:
            try:
                result[ex_name].append({
                    "symbol": s.symbol,
                    "funding_rate": s.funding_rate,
                    "apr": s.apr,
                    "net_apr": s.net_apr,
                    "mark_price": s.mark_price,
                    "interval_hours": s.interval_hours,
                    "side_recommendation": s.side_recommendation,
                })
            except AttributeError:
                result[ex_name].append(str(s))

    return web.json_response({"funding": result, "ts": _utc_now_iso()})


async def handle_arb(request: web.Request) -> web.Response:
    active = arb_storage.get_active()
    recent = arb_storage.get_recent_closed(limit=10)
    stats = arb_storage.get_total_stats()
    return web.json_response({
        "active": active,
        "recent_closed": recent,
        "stats": stats,
        "ts": _utc_now_iso(),
    }, dumps=lambda obj: json.dumps(obj, default=str))


_HTML = """<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Zenith-Control Dashboard</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: 'Segoe UI', system-ui, sans-serif; background: #0f1117; color: #e2e8f0; padding: 1rem; }
  h1 { color: #7dd3fc; margin-bottom: 1rem; font-size: 1.5rem; }
  h2 { color: #94a3b8; margin: 1rem 0 0.5rem; font-size: 1rem; text-transform: uppercase; letter-spacing: 0.05em; }
  .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 0.75rem; margin-bottom: 1rem; }
  .card { background: #1e2130; border-radius: 0.75rem; padding: 1rem; border: 1px solid #2d3748; }
  .card .label { font-size: 0.75rem; color: #64748b; margin-bottom: 0.25rem; text-transform: uppercase; }
  .card .value { font-size: 1.25rem; font-weight: 600; }
  .green { color: #4ade80; } .red { color: #f87171; } .yellow { color: #fbbf24; } .blue { color: #60a5fa; }
  table { width: 100%; border-collapse: collapse; font-size: 0.85rem; }
  th { text-align: left; padding: 0.5rem; color: #64748b; border-bottom: 1px solid #2d3748; }
  td { padding: 0.5rem; border-bottom: 1px solid #1a2035; }
  .badge { display: inline-block; padding: 0.15rem 0.5rem; border-radius: 9999px; font-size: 0.7rem; font-weight: 600; }
  .badge-green { background: #14532d; color: #4ade80; }
  .badge-red { background: #450a0a; color: #f87171; }
  .badge-yellow { background: #422006; color: #fbbf24; }
  .badge-blue { background: #1e3a5f; color: #60a5fa; }
  .ts { font-size: 0.7rem; color: #475569; margin-top: 0.5rem; }
  #refresh-bar { width: 0%; height: 2px; background: #3b82f6; transition: width 0.1s linear; }
</style>
</head>
<body>
<div id="refresh-bar"></div>
<h1>🛡 Zenith-Control Ultimate — Дашборд</h1>
<div class="grid" id="status-cards">
  <div class="card"><div class="label">Загрузка...</div><div class="value">—</div></div>
</div>

<h2>📂 Открытые позиции</h2>
<div class="card" style="padding:0.5rem"><table id="positions-table">
  <tr><th>Символ</th><th>Сторона</th><th>Вход</th><th>Qty</th><th>Стоп</th><th>Открыта</th></tr>
</table></div>

<h2>🔁 Режимы рынка</h2>
<div class="card" style="padding:0.5rem"><table id="regimes-table">
  <tr><th>Символ</th><th>Режим</th><th>Уверенность</th></tr>
</table></div>

<h2>⚡ Арбитраж (активная пара)</h2>
<div class="card" id="arb-card"><div class="label">Нет активной арб-позиции</div></div>

<h2>📡 Funding Snapshot</h2>
<div class="card" id="funding-card"><div class="label">Нет данных</div></div>

<div class="ts" id="last-update">Обновление каждые 10с</div>

<script>
const REFRESH_SEC = 10;
let progress = 0;
let bar = document.getElementById('refresh-bar');

function fmt(v, digits=4) {
  if (v == null) return '—';
  const n = parseFloat(v);
  return isNaN(n) ? String(v) : n.toFixed(digits);
}
function pct(v) { return v == null ? '—' : (parseFloat(v)*100).toFixed(2)+'%'; }
function badge(text, cls) { return `<span class="badge badge-${cls}">${text}</span>`; }

async function loadStatus() {
  try {
    const r = await fetch('/api/status');
    const d = await r.json();
    const g = d;
    const equity = g.equity_start != null ? (parseFloat(g.equity_start) + parseFloat(g.cumulative_pnl||0)).toFixed(2) : '—';
    const running = g.bot_running;
    const ks = g.kill_switch_state || 'NONE';
    document.getElementById('status-cards').innerHTML = `
      <div class="card"><div class="label">Торговля</div><div class="value ${running?'green':'red'}">${running?'▶ ACTIVE':'⏸ STOPPED'}</div></div>
      <div class="card"><div class="label">Kill-switch</div><div class="value ${ks==='NONE'?'green':'red'}">${ks}</div></div>
      <div class="card"><div class="label">Эквити USDT</div><div class="value blue">${equity}</div></div>
      <div class="card"><div class="label">Суточный PnL</div><div class="value ${parseFloat(g.daily_pnl||0)>=0?'green':'red'}">${parseFloat(g.daily_pnl||0)>=0?'+':''}${fmt(g.daily_pnl,2)}</div></div>
      <div class="card"><div class="label">Недельный PnL</div><div class="value ${parseFloat(g.weekly_pnl||0)>=0?'green':'red'}">${parseFloat(g.weekly_pnl||0)>=0?'+':''}${fmt(g.weekly_pnl,2)}</div></div>
      <div class="card"><div class="label">Blackout</div><div class="value ${g.blackout?'yellow':'green'}">${g.blackout?'⚠ '+g.blackout_reason.substring(0,30):'OK'}</div></div>
    `;
  } catch(e) { console.error('status error', e); }
}

async function loadPositions() {
  try {
    const r = await fetch('/api/positions');
    const d = await r.json();
    const tbody = d.open_positions.map(p => `
      <tr>
        <td><b>${p.symbol}</b></td>
        <td>${p.side==='Buy'?'🟢 LONG':'🔴 SHORT'}</td>
        <td>${fmt(p.entry_price,4)}</td>
        <td>${fmt(p.qty,4)}</td>
        <td>${fmt(p.current_stop,4)}</td>
        <td>${p.entry_ts_iso||'—'}</td>
      </tr>`).join('') || '<tr><td colspan="6" style="color:#475569">Нет открытых позиций</td></tr>';
    document.getElementById('positions-table').innerHTML =
      '<tr><th>Символ</th><th>Сторона</th><th>Вход</th><th>Qty</th><th>Стоп</th><th>Открыта</th></tr>' + tbody;

    const rtbody = d.regimes.map(r => `
      <tr>
        <td>${r.symbol}</td>
        <td>${r.regime||'—'}</td>
        <td>${r.regime_confidence!=null?r.regime_confidence+'%':'—'}</td>
      </tr>`).join('');
    document.getElementById('regimes-table').innerHTML =
      '<tr><th>Символ</th><th>Режим</th><th>Уверенность</th></tr>' + rtbody;
  } catch(e) { console.error('positions error', e); }
}

async function loadArb() {
  try {
    const r = await fetch('/api/arb');
    const d = await r.json();
    const a = d.active;
    const s = d.stats;
    const arbEl = document.getElementById('arb-card');
    if (a) {
      arbEl.innerHTML = `
        <div class="label">Активная ARB #${a.id}</div>
        <table><tr><th>Поле</th><th>Значение</th></tr>
          <tr><td>Символ</td><td><b>${a.symbol}</b></td></tr>
          <tr><td>LONG @ </td><td>${a.long_exchange} вход ${fmt(a.long_entry,4)}</td></tr>
          <tr><td>SHORT @ </td><td>${a.short_exchange} вход ${fmt(a.short_entry,4)}</td></tr>
          <tr><td>Qty</td><td>${fmt(a.qty_base,6)}</td></tr>
          <tr><td>Funding получено</td><td class="green">${fmt(a.funding_received,4)} USDT</td></tr>
          <tr><td>Открыта</td><td>${a.opened_ts}</td></tr>
          <tr><td>APR на входе</td><td>${pct(a.edge_apr_open)}</td></tr>
        </table>
        <div style="margin-top:0.5rem;font-size:0.75rem;color:#64748b">
          Всего закрыто арб-сделок: ${s.n} | Суммарный PnL: ${fmt(s.pnl_sum,2)} USDT
        </div>`;
    } else {
      arbEl.innerHTML = `<div class="label">Нет активной арб-позиции</div>
        <div style="margin-top:0.5rem;font-size:0.75rem;color:#64748b">
          Всего закрыто: ${s.n} | Суммарный PnL: ${fmt(s.pnl_sum,2)} USDT |
          Funding: ${fmt(s.funding_sum,2)} USDT
        </div>`;
    }
  } catch(e) { console.error('arb error', e); }
}

async function loadFunding() {
  try {
    const r = await fetch('/api/funding');
    const d = await r.json();
    if (d.error) {
      document.getElementById('funding-card').innerHTML = `<div class="label">${d.error}</div>`;
      return;
    }
    let html = '';
    for (const [ex, snaps] of Object.entries(d.funding||{})) {
      html += `<div style="color:#94a3b8;margin:0.5rem 0 0.25rem;font-size:0.8rem">${ex.toUpperCase()}</div>`;
      html += '<table><tr><th>Символ</th><th>Rate/8h</th><th>APR нетто</th><th>Рек.</th></tr>';
      for (const s of (snaps||[]).slice(0,6)) {
        const apr = parseFloat(s.net_apr||0);
        const cls = apr > 0.2 ? 'green' : apr > 0 ? 'blue' : 'red';
        html += `<tr><td>${s.symbol}</td><td>${pct(s.funding_rate)}</td><td class="${cls}">${pct(s.net_apr)}</td><td>${s.side_recommendation||'—'}</td></tr>`;
      }
      html += '</table>';
    }
    document.getElementById('funding-card').innerHTML = html || '<div class="label">Нет данных</div>';
  } catch(e) { console.error('funding error', e); }
}

async function refresh() {
  await Promise.all([loadStatus(), loadPositions(), loadArb(), loadFunding()]);
  document.getElementById('last-update').textContent =
    'Последнее обновление: ' + new Date().toLocaleTimeString('ru-RU');
}

refresh();
setInterval(refresh, REFRESH_SEC * 1000);

let pct2 = 0;
setInterval(() => {
  pct2 = Math.min(100, pct2 + (100 / (REFRESH_SEC * 10)));
  bar.style.width = pct2 + '%';
  if (pct2 >= 100) pct2 = 0;
}, 100);
</script>
</body>
</html>"""


def _make_app() -> web.Application:
    app = web.Application()
    app.router.add_get("/", lambda r: web.Response(text=_HTML, content_type="text/html"))
    app.router.add_get("/health", handle_health)
    app.router.add_get("/api/status", handle_status)
    app.router.add_get("/api/positions", handle_positions)
    app.router.add_get("/api/equity", handle_equity)
    app.router.add_get("/api/funding", handle_funding)
    app.router.add_get("/api/arb", handle_arb)
    return app


async def start_server(state: dict[str, Any]) -> None:
    """Запустить веб-дашборд. Блокирует до завершения (вызывается через gather)."""
    set_state(state)
    port = int(os.getenv("DASHBOARD_PORT", "8080"))
    enabled = os.getenv("DASHBOARD_ENABLED", "true").strip().lower() not in (
        "0", "false", "no", "off"
    )
    if not enabled:
        print("[DASH] Дашборд отключён (DASHBOARD_ENABLED=false)")
        return

    app = _make_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    print(f"[DASH] Дашборд запущен: http://0.0.0.0:{port}/")
    try:
        import asyncio
        while True:
            await asyncio.sleep(3600)
    finally:
        await runner.cleanup()
