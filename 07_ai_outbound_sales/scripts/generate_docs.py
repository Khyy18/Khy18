"""Generate OpenAPI documentation from the FastAPI app.

Outputs the OpenAPI JSON schema to docs/openapi.json.

Usage:
    python scripts/generate_docs.py
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Set required environment variables for import (Settings validation)
_env_defaults = {
    "DATABASE_URL": "sqlite+aiosqlite:///test.db",
    "REDIS_URL": "redis://localhost:6379/0",
    "OPENAI_API_KEY": "sk-test",
    "ANTHROPIC_API_KEY": "sk-ant-test",
    "GROQ_API_KEY": "gsk-test",
    "APOLLO_API_KEY": "test",
    "HUNTER_API_KEY": "test",
    "SMTP_HOST": "localhost",
    "SMTP_PORT": "587",
    "SMTP_USER": "test",
    "SMTP_PASSWORD": "test",
}
for key, value in _env_defaults.items():
    if key not in os.environ:
        os.environ[key] = value

from main import app


def generate_openapi_json() -> dict:
    """Generate and return the OpenAPI schema from the FastAPI app."""
    return app.openapi()


def write_docs(output_path: str = "docs/openapi.json") -> str:
    """Write OpenAPI JSON to the specified path."""
    schema = generate_openapi_json()

    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    with open(output_path, "w") as f:
        json.dump(schema, f, indent=2)

    return output_path


if __name__ == "__main__":
    output = write_docs()
    print(f"OpenAPI schema written to: {output}")
