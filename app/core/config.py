from pydantic_settings import BaseSettings, SettingsConfigDict



class Settings(BaseSettings):
    PROJECT_NAME: str
    ENVIRONMENT: str

    DATABASE_URL: str

    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int
    REFRESH_TOKEN_EXPIRE_DAYS: int
    REGISTRATION_TOKEN_EXPIRE_MINUTES: int

    MAILJET_API_KEY: str
    MAILJET_API_SECRET: str
    MAILJET_SENDER_EMAIL: str

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
    
    FRONTEND_ORIGINS: str
    @property
    def frontend_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.FRONTEND_ORIGINS.split(",") if origin.strip()]
    
    COOKIE_DOMAIN: str
    COOKIE_SECURE: bool
    COOKIE_SAMESITE: str
    
    GOOGLE_CLIENT_ID: str

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True)


settings = Settings()