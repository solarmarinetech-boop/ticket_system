from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    # Telegram Bot
    bot_token: str
    webhook_url: str = ""
    webhook_path: str = "/webhook"

    # Database (Railway PostgreSQL)
    database_url: str

    # Groq API
    # Ключ: https://console.groq.com → API Keys → Create API Key (бесплатно)
    groq_api_key: str
    groq_model: str = "llama-3.3-70b-versatile"

    # Web Console Auth (JWT)
    secret_key: str = "change-me-in-production-min-32-chars"
    access_token_expire_minutes: int = 480

    # Admins — Telegram Chat ID через запятую
    admin_chat_ids: str = ""

    # App
    debug: bool = False
    log_level: str = "INFO"

    @property
    def admin_ids_list(self) -> List[int]:
        if not self.admin_chat_ids:
            return []
        return [int(x.strip()) for x in self.admin_chat_ids.split(",") if x.strip()]

    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
