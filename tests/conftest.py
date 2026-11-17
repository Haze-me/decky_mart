import os

# Settings() is built at import time and most fields are required. Dummy values, set BEFORE any `app.*`
# import. Real environment variables beat the .env file, so tests never read your .env or touch a real
# database, Redis, S3 or mail provider.
os.environ.update(
    {
        "PROJECT_NAME": "solver-auth-test",
        "ENVIRONMENT": "test",
        "DATABASE_URL": "postgresql+asyncpg://test:test@localhost:5432/test",
        "REDIS_URL": "redis://localhost:6379",
        "JWT_SECRET_KEY": "test-solver-secret",
        "JWT_ALGORITHM": "HS256",
        "ACCESS_TOKEN_EXPIRE_MINUTES": "15",
        "REFRESH_TOKEN_EXPIRE_DAYS": "7",
        "REGISTRATION_TOKEN_EXPIRE_MINUTES": "30",
        "CUSTOMER_TOKEN_SIGNING_KEY": "test-customer-secret",
        "RESEND_API_KEY": "test",
        "RESEND_SENDER_EMAIL": "test@example.com",
        "AWS_ACCESS_KEY_ID": "test",
        "AWS_SECRET_ACCESS_KEY": "test",
        "AWS_REGION": "us-east-1",
        "AWS_S3_BUCKET": "test-bucket",
        "AWS_S3_PUBLIC_BASE_URL": "https://example.com",
        "OTP_EXPIRE_MINUTES": "10",
        "OTP_MAX_ATTEMPTS": "5",
        "OTP_RESEND_COOLDOWN_SECONDS": "60",
        "MAX_PROFILE_IMAGE_SIZE_MB": "5",
        "MAX_ID_DOCUMENT_SIZE_MB": "5",
        "MAX_SELFIE_SIZE_MB": "15",
        "MAX_POST_IMAGE_SIZE_MB": "5",
        "MAX_POST_VIDEO_SIZE_MB": "50",
        "MAX_POST_MEDIA_ITEMS": "5",
        "FRONTEND_ORIGINS": "http://localhost:3000",
        "COOKIE_DOMAIN": "",
        "COOKIE_SECURE": "False",
        "COOKIE_SAMESITE": "lax",
        "GOOGLE_CLIENT_ID": "test",
    }
)
