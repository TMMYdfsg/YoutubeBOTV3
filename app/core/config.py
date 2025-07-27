# app/core/config.py

from pydantic_settings import BaseSettings
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

    # --- Render対応：ファイル内容を環境変数から受け取る ---
    GOOGLE_CREDENTIALS_JSON: Optional[str] = None
    CLIENT_SECRET_JSON: Optional[str] = None
    YOUTUBE_TOKEN_BASE64: Optional[str] = None

    # --- 定数 ---
    YOUTUBE_API_SERVICE_NAME: str = "youtube"
    YOUTUBE_API_VERSION: str = "v3"

    # Render対応：ファイルパスを永続ディスクのパスに変更
    DATA_DIR: str = "/app/data"
    GOOGLE_CREDENTIALS_FILE: str = f"{DATA_DIR}/google-credentials.json"
    CLIENT_SECRET_FILE: str = f"{DATA_DIR}/client_secret.json"
    USER_IDS_FILE: str = f"{DATA_DIR}/user_ids.json"
    TOKEN_PICKLE_FILE: str = f"{DATA_DIR}/token.pickle"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
