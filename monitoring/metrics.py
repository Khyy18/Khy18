"""Определение Prometheus-метрик приложения."""

from prometheus_client import Counter, Gauge, Histogram

# --- HTTP ---
HTTP_REQUESTS_TOTAL = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "path", "status"],
)

HTTP_REQUEST_DURATION = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "path"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

# --- Платежи ---
PAYMENT_EVENTS_TOTAL = Counter(
    "payment_events_total",
    "Total payment events",
    ["event_type"],
)

# --- Торговля ---
TRADE_OPERATIONS_TOTAL = Counter(
    "trade_operations_total",
    "Total trade operations",
    ["symbol", "side", "outcome"],
)

TRADE_PNL_DISTRIBUTION = Histogram(
    "trade_pnl_distribution",
    "Distribution of trade PnL values",
    buckets=(-100, -50, -20, -10, -5, -2, -1, 0, 1, 2, 5, 10, 20, 50, 100),
)

# --- Gauges ---
QUEUE_LENGTH = Gauge(
    "queue_length",
    "Current queue length",
)

OPEN_POSITIONS_COUNT = Gauge(
    "open_positions_count",
    "Number of currently open positions",
)
