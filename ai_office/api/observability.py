"""Observability: Request logging middleware и MetricsCollector."""

import asyncio
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from ai_office.core.logging import correlation_id_var, get_logger

logger = get_logger(__name__)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Middleware для логирования HTTP-запросов с correlation ID."""

    async def dispatch(self, request: Request, call_next):
        """Log method, path, status_code, duration_ms. Set correlation_id."""
        # Get or generate correlation ID
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())

        # Set context var for propagation
        token = correlation_id_var.set(request_id)

        start = time.perf_counter()
        try:
            response = await call_next(request)
            duration_ms = (time.perf_counter() - start) * 1000

            logger.info(
                "HTTP %s %s -> %d (%.1fms)",
                request.method,
                request.url.path,
                response.status_code,
                duration_ms,
            )

            # Add correlation ID to response headers
            response.headers["X-Request-ID"] = request_id
            return response
        except Exception as e:
            duration_ms = (time.perf_counter() - start) * 1000
            logger.error(
                "HTTP %s %s -> 500 (%.1fms) error=%s",
                request.method,
                request.url.path,
                duration_ms,
                str(e),
            )
            raise
        finally:
            correlation_id_var.reset(token)


class MetricsCollector:
    """In-memory metrics collector с Prometheus-совместимым выводом."""

    def __init__(self):
        self._lock = asyncio.Lock()
        # Counters: key -> value
        self._counters: dict[str, float] = {}
        # Histogram observations: key -> list of values
        self._histograms: dict[str, list[float]] = {}
        # Gauges: key -> value
        self._gauges: dict[str, float] = {}

    async def increment_counter(self, name: str, labels: dict[str, str] | None = None, value: float = 1.0):
        """Increment a counter metric."""
        key = self._make_key(name, labels)
        async with self._lock:
            self._counters[key] = self._counters.get(key, 0) + value

    async def observe_histogram(self, name: str, value: float, labels: dict[str, str] | None = None):
        """Observe a value for histogram metric."""
        key = self._make_key(name, labels)
        async with self._lock:
            if key not in self._histograms:
                self._histograms[key] = []
            self._histograms[key].append(value)

    async def set_gauge(self, name: str, value: float, labels: dict[str, str] | None = None):
        """Set a gauge metric value."""
        key = self._make_key(name, labels)
        async with self._lock:
            self._gauges[key] = value

    async def get_counter(self, name: str, labels: dict[str, str] | None = None) -> float:
        """Get current counter value."""
        key = self._make_key(name, labels)
        async with self._lock:
            return self._counters.get(key, 0)

    async def get_gauge(self, name: str, labels: dict[str, str] | None = None) -> float:
        """Get current gauge value."""
        key = self._make_key(name, labels)
        async with self._lock:
            return self._gauges.get(key, 0)

    async def get_histogram_observations(self, name: str, labels: dict[str, str] | None = None) -> list[float]:
        """Get histogram observations."""
        key = self._make_key(name, labels)
        async with self._lock:
            return list(self._histograms.get(key, []))

    def _make_key(self, name: str, labels: dict[str, str] | None = None) -> str:
        """Create a metric key from name and labels."""
        if not labels:
            return name
        label_str = ",".join(f'{k}="{v}"' for k, v in sorted(labels.items()))
        return f"{name}{{{label_str}}}"

    async def format_prometheus(self) -> str:
        """Format all metrics as Prometheus text exposition."""
        lines: list[str] = []

        async with self._lock:
            # Counters
            counter_names = set()
            for key in self._counters:
                base_name = key.split("{")[0]
                counter_names.add(base_name)

            for base_name in sorted(counter_names):
                lines.append(f"# HELP {base_name} Counter metric")
                lines.append(f"# TYPE {base_name} counter")
                for key, value in sorted(self._counters.items()):
                    if key.split("{")[0] == base_name:
                        lines.append(f"{key} {value}")

            # Gauges
            gauge_names = set()
            for key in self._gauges:
                base_name = key.split("{")[0]
                gauge_names.add(base_name)

            for base_name in sorted(gauge_names):
                lines.append(f"# HELP {base_name} Gauge metric")
                lines.append(f"# TYPE {base_name} gauge")
                for key, value in sorted(self._gauges.items()):
                    if key.split("{")[0] == base_name:
                        lines.append(f"{key} {value}")

            # Histograms (simplified: sum, count, buckets)
            histogram_names = set()
            for key in self._histograms:
                base_name = key.split("{")[0]
                histogram_names.add(base_name)

            buckets = [0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]

            for base_name in sorted(histogram_names):
                lines.append(f"# HELP {base_name} Histogram metric")
                lines.append(f"# TYPE {base_name} histogram")
                for key, observations in sorted(self._histograms.items()):
                    if key.split("{")[0] != base_name:
                        continue
                    # Extract labels portion
                    if "{" in key:
                        label_part = key[key.index("{") + 1:key.index("}")]
                    else:
                        label_part = ""

                    total = sum(observations)
                    count = len(observations)

                    for bucket in buckets:
                        bucket_count = sum(1 for v in observations if v <= bucket)
                        if label_part:
                            lines.append(f'{base_name}_bucket{{{label_part},le="{bucket}"}} {bucket_count}')
                        else:
                            lines.append(f'{base_name}_bucket{{le="{bucket}"}} {bucket_count}')

                    if label_part:
                        lines.append(f'{base_name}_bucket{{{label_part},le="+Inf"}} {count}')
                        lines.append(f"{base_name}_sum{{{label_part}}} {total}")
                        lines.append(f"{base_name}_count{{{label_part}}} {count}")
                    else:
                        lines.append(f'{base_name}_bucket{{le="+Inf"}} {count}')
                        lines.append(f"{base_name}_sum {total}")
                        lines.append(f"{base_name}_count {count}")

        lines.append("")
        return "\n".join(lines)


# Module-level singleton
metrics_collector = MetricsCollector()
