from pydantic_settings import BaseSettings, SettingsConfigDict



class Settings(BaseSettings):
    PROJECT_NAME: str
    ENVIRONMENT: str
    # DEBUG, INFO, WARNING, ERROR. Logs are JSON on stdout (for Promtail/Loki).
    LOG_LEVEL: str = "INFO"

    DATABASE_URL: str

    REDIS_URL: str

    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int
    REFRESH_TOKEN_EXPIRE_DAYS: int
    REGISTRATION_TOKEN_EXPIRE_MINUTES: int

    # Verify-only: signs the customer service's access tokens (cust_access cookie). We never mint
    # tokens with this key, only verify. Shared with us out-of-band by the customer-service team.
    CUSTOMER_TOKEN_SIGNING_KEY: str

    RESEND_API_KEY: str
    RESEND_SENDER_EMAIL: str

    AWS_ACCESS_KEY_ID: str
    AWS_SECRET_ACCESS_KEY: str
    AWS_REGION: str
    AWS_S3_BUCKET: str
    AWS_S3_PUBLIC_BASE_URL: str
    
    OTP_EXPIRE_MINUTES: int
    OTP_MAX_ATTEMPTS: int
    
    OTP_RESEND_COOLDOWN_SECONDS: int
    
    MAX_PROFILE_IMAGE_SIZE_MB: int
    MAX_ID_DOCUMENT_SIZE_MB: int
    MAX_SELFIE_SIZE_MB: int
    MAX_POST_IMAGE_SIZE_MB: int
    MAX_POST_VIDEO_SIZE_MB: int
    MAX_POST_MEDIA_ITEMS: int
    
    FRONTEND_ORIGINS: str
    @property
    def frontend_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.FRONTEND_ORIGINS.split(",") if origin.strip()]
    
    COOKIE_DOMAIN: str
    COOKIE_SECURE: bool
    COOKIE_SAMESITE: str
    
    GOOGLE_CLIENT_ID: str

    # Match-service sync. Optional on purpose (a new REQUIRED setting crash-loops the pods until the
    # ConfigMap/Secret has it): either one empty = syncing is switched off, nothing else changes.
    # MATCH_SERVICE_URL is the cluster-internal base URL, e.g. http://match-service.<namespace>.svc:8000
    # MATCH_INTERNAL_API_KEY must equal match-service's INTERNAL_API_KEY (a secret).
    MATCH_SERVICE_URL: str = ""
    MATCH_INTERNAL_API_KEY: str = ""

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True)


settings = Settings()