"""Shared httpx.AsyncClient for the application."""

import httpx

_http_client: httpx.AsyncClient | None = None


def create_http_client() -> httpx.AsyncClient:
    """Create a shared httpx.AsyncClient with connection pool limits."""
    return httpx.AsyncClient(
        limits=httpx.Limits(
            max_connections=100,
            max_keepalive_connections=20,
        ),
        timeout=httpx.Timeout(30.0),
    )


def get_http_client() -> httpx.AsyncClient:
    """Get the shared httpx.AsyncClient instance.

    Returns the module-level client that is initialized during app lifespan.
    """
    global _http_client
    if _http_client is None:
        _http_client = create_http_client()
    return _http_client


def set_http_client(client: httpx.AsyncClient) -> None:
    """Set the module-level httpx client (called during lifespan startup)."""
    global _http_client
    _http_client = client


async def close_http_client() -> None:
    """Close the shared httpx client (called during lifespan shutdown)."""
    global _http_client
    if _http_client is not None:
        await _http_client.aclose()
        _http_client = None
