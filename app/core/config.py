# app/core/config.py
from pydantic_settings import BaseSettings
from typing import List, Optional


class Settings(BaseSettings):
    LINE_CHANNEL_ACCESS_TOKEN: str
    LINE_CHANNEL_SECRET: str
    LINE_ADMIN_USER_ID: str
    YOUTUBE_API_KEY: str
    TARGET_YOUTUBE_CHANNEL_ID: str
    GEMINI_API_KEY: str
    BASE_URL: str

    # --- Supabase対応 ---
    SUPABASE_URL: str
    SUPABASE_KEY: str
    YOUTUBE_TOKEN_JSON_INITIAL: Optional[str] = None

    # --- 定数 ---
    YOUTUBE_API_SERVICE_NAME: str = "youtube"
    YOUTUBE_API_VERSION: str = "v3"
    YOUTUBE_OAUTH_SCOPES: List[str] = [
        "https://www.googleapis.com/auth/youtube.force-ssl"
    ]

    # Secret Filesのパス (Render環境でのみ有効)
    SECRET_DIR: str = "/etc/secrets"
    CLIENT_SECRET_FILE: str = f"{SECRET_DIR}/client_secret.json"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
