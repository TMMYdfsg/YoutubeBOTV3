# app/main.py

import os
import base64
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.api.endpoints import line_webhook
from app.core.config import settings

# --- Render対応：永続データディレクトリの定義 ---
DATA_DIR = settings.DATA_DIR

app = FastAPI(
    title="YouTube Live Comment Bot",
    description="A bot that automatically replies to YouTube Live comments using Gemini and is managed via LINE.",
    version="1.0.0",
)


@app.on_event("startup")
def startup_event():
    """
    アプリケーション起動時に実行されるイベント
    Renderの永続ディスクに必要な認証ファイルを書き出す
    """
    print("アプリケーションが起動しました。")

    # 永続データディレクトリが存在しない場合は作成
    if not os.path.exists(DATA_DIR):
        print(f"データディレクトリ '{DATA_DIR}' を作成します。")
        os.makedirs(DATA_DIR)

    # 環境変数から認証情報を読み込み、ファイルとして書き出す
    files_to_write = {
        "google-credentials.json": settings.GOOGLE_CREDENTIALS_JSON,
        "client_secret.json": settings.CLIENT_SECRET_JSON,
        "token.json": settings.YOUTUBE_TOKEN_JSON,
    }

    for filename, content in files_to_write.items():
        filepath = os.path.join(DATA_DIR, filename)
        if content:
            # ファイルが既に存在する場合は上書きしない（初回起動時のみ書き出す）
            if not os.path.exists(filepath):
                print(f"環境変数から '{filename}' を書き出します。")
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(content)
        else:
            # 必須ではないファイルについては警告レベルを下げる
            if filename not in ["token.json"]:
                print(
                    f"警告: 環境変数 '{filename.upper().replace('-', '_').replace('.', '_')}' が設定されていません。"
                )

    print("起動時処理が完了しました。")


app.include_router(line_webhook.router, prefix="/api/v1/line", tags=["line"])


@app.get("/", tags=["Root"])
async def read_root():
    """サーバーの稼働状況を確認するためのエンドポイント"""
    return JSONResponse(content={"status": "YouTube Bot is running"})
