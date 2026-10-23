import importlib

for m in [
    "fastapi", "uvicorn", "uvloop", "sqlalchemy", "asyncpg", "redis",
    "slowapi", "limits.storage", "pydantic_settings", "argon2",
    "passlib.hash", "jose", "cryptography", "boto3", "httpx", "requests",
]:
    importlib.import_module(m)

from limits.errors import ConfigurationError
from limits.storage import storage_from_string

try:
    storage_from_string("redis://localhost:6379")
except ConfigurationError:
    raise
except Exception:
    pass

print("smoke ok")