from pydantic import EmailStr, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file="../.env",
        env_file_encoding="utf-8",
        extra="ignore"
    )
    
    API_V1_STR: str
    
    GATEWAY_TOKEN: str
    
    JWT_TOKEN: str
    CUSTOMER_CODE: str
    MERCHANT_ID: str
    SECRET_KEY: str
    CLIENT_ID: str
    PUBLIC_KEY: dict = {
        "kty": "RSA",
        "e": "AQAB",
        "n": "rwm77av7GIttq-JF1itEgLCGEZW_zz16RlUQVYlLbJtyRSu61fCec_rroP6PxjXU2uLzUOaGaLgAPeUZAJrGuVp9nryKgbZceHckdHDYgJd9TsdJ1MYUsXaOb9joN9vmsCscBx1lwSlFQyNQsHUsrjuDk-opf6RCuazRQ9gkoDCX70HV8WBMFoVm-YWQKJHZEaIQxg_DU4gMFyKRkDGKsYKA0POL-UgWA1qkg6nHY5BOMKaqxbc5ky87muWB5nNk4mfmsckyFv9j1gBiXLKekA_y4UwG2o1pbOLpJS3bP_c95rm4M9ZBmGXqfOQhbjz8z-s9C11i-jmOQ2ByohS-ST3E5sqBzIsxxrxyQDTw--bZNhzpbciyYW4GfkkqyeYoOPd_84jPTBDKQXssvj8ZOj2XboS77tvEO1n1WlwUzh8HPCJod5_fEgSXuozpJtOggXBv0C2ps7yXlDZf-7Jar0UYc_NJEHJF-xShlqd6Q3sVL02PhSCM-ibn9DN9BKmD"
    }
    
    ACCESS_TOKEN_EXPIRE_MINUTES: int
    EMAIL_RESET_TOKEN_EXPIRE_HOURS: int
    
    EMAILS_FROM_EMAIL: EmailStr
    EMAILS_FROM_NAME: str
    SMTP_HOST: str
    SMTP_PORT: int
    SMTP_USER: str
    SMTP_PASSWORD: str
    
    SUPERUSER_EMAIL: EmailStr
    SUPERUSER_PASSWORD: str
    
    PROJECT_NAME: str
    
    FRONTEND_HOST: str
    
    UPLOAD_DIR: str
    
    RABBITMQ_HOST: str
    RABBITMQ_PORT: int
    RABBITMQ_USER: str
    RABBITMQ_PASSWORD: str
    
    REDIS_HOST: str
    REDIS_PORT: int
    REDIS_PASSWORD: str

    MAX_BOT_TOKEN: str = ""
    MAX_BOT_LINK: str = ""
    MAX_REGISTRATION_TTL_SECONDS: int = 2400
    MAXBOT_INTERNAL_TOKEN: str = ""

    VK_APP_ID: str = ""
    VK_CLIENT_SECRET: str = ""
    VK_REDIRECT_URI: str = ""
    VK_SCOPE: str = "vkid.personal_info email phone"
    VK_REGISTRATION_TTL_SECONDS: int = 600
    
    @computed_field
    @property
    def REDIS_URL(self) -> str:
        return f"redis://:{self.REDIS_PASSWORD}@{self.REDIS_HOST}:{self.REDIS_PORT}/"
    
    @computed_field
    @property
    def RABBITMQ_URL(self) -> str:
        return f"amqp://{self.RABBITMQ_USER}:{self.RABBITMQ_PASSWORD}@{self.RABBITMQ_HOST}:{self.RABBITMQ_PORT}/"

settings = Settings()

tournament_categories_map = {
    "Зеленый мяч": {
        range(1, 2): 75,
        range(2, 3): 60,
        range(3, 5): 45,
        range(5, 9): 30,
        range(9, 17): 15,
        range(17, 33): 10,
        range(33, 65): 10,
        "additional": 10,
    },
    "Оранжевый мяч": {
        range(1, 2): 10,
        range(2, 3): 10,
        range(3, 5): 10,
        range(5, 9): 10,
        range(9, 17): 10,
        range(17, 33): 10,
        range(33, 65): 10,
        "additional": 10,
    },
    "Красный мяч": {
        range(1, 2): 10,
        range(2, 3): 10,
        range(3, 5): 10,
        range(5, 9): 10,
        range(9, 17): 10,
        range(17, 33): 10,
        range(33, 65): 10,
        "additional": 10,
    },
    "До 17 лет": {
        range(1, 2): 500,
        range(2, 3): 384,
        range(3, 5): 256,
        range(5, 9): 128,
        range(9, 17): 64,
        range(17, 33): 32,
        range(33, 65): 16,
        "additional": 8,
    },
    "До 15 лет": {
        range(1, 2): 378,
        range(2, 3): 252,
        range(3, 5): 168,
        range(5, 9): 112,
        range(9, 17): 56,
        range(17, 33): 28,
        range(33, 65): 14,
        "additional": 7,
    },
    "До 13 лет": {
        range(1, 2): 324,
        range(2, 3): 216,
        range(3, 5): 144,
        range(5, 9): 96,
        range(9, 17): 48,
        range(17, 33): 24,
        range(33, 65): 12,
        "additional": 6,
    },
}
