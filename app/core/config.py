# app/core/config.py

from pydantic_settings import BaseSettings

# ★ 修正: `Optional` と `List` を `typing` からインポート
from typing import List, Optional


class Settings(BaseSettings):
    # --- LINE ---
    LINE_CHANNEL_ACCESS_TOKEN: str
    LINE_CHANNEL_SECRET: str
    LINE_ADMIN_USER_ID: str

    # --- YouTube ---
    YOUTUBE_API_KEY: str
    TARGET_YOUTUBE_CHANNEL_ID: str

    # --- Gemini ---
    GEMINI_API_KEY: str

    # --- Application ---
    BASE_URL: str

    # --- Render対応：RedisとSecret Filesから設定を読み込む ---
    # ★ 修正点: REDIS_URLをOptional[str] = Noneとすることで、
    # .envファイルに記載がなくてもエラーにならないようにします。
    REDIS_URL: Optional[str] = None
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
