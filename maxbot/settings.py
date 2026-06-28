import logging

from pydantic_settings import BaseSettings, SettingsConfigDict


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    MAX_BOT_TOKEN: str = ""
    MAX_WEBHOOK_SECRET: str = ""
    MAX_API_BASE_URL: str = "https://platform-api2.max.ru"

    BACKEND_INTERNAL_URL: str = "http://backend:8000"
    BACKEND_MAX_START_PATH: str = "/api/v1/max/registration/start"
    BACKEND_MAX_CONTACT_PATH: str = "/api/v1/max/registration/contact"
    BACKEND_MAXBOT_TOKEN: str = ""

    MAXBOT_HOST: str = "0.0.0.0"
    MAXBOT_PORT: int = 8010

    @property
    def backend_start_url(self) -> str:
        return f"{self.BACKEND_INTERNAL_URL.rstrip('/')}{self.BACKEND_MAX_START_PATH}"

    @property
    def backend_contact_url(self) -> str:
        return f"{self.BACKEND_INTERNAL_URL.rstrip('/')}{self.BACKEND_MAX_CONTACT_PATH}"


settings = Settings()
