# app/main.py (最終修正版)

import os
import base64
import asyncio
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.api.endpoints import line_webhook
from app.core.config import settings
from app.core.state_manager import bot_state

# Renderデプロイ時に永続データを保存するディレクトリ
DATA_DIR = settings.DATA_DIR

app = FastAPI(
    title="YouTube Live Comment Bot",
    description="A bot that automatically replies to YouTube Live comments using Gemini and is managed via LINE.",
    version="2.0.0-final",
)


@app.on_event("startup")
def startup_event():
    """
    アプリケーション起動時に実行されるイベント。
    Renderデプロイ時に環境変数から認証ファイルを書き出す処理。
    ローカル実行時は主にディレクトリ作成のみ機能します。
    """
    print("アプリケーションが起動しました。")

    if not os.path.exists(DATA_DIR):
        print(f"データディレクトリ '{DATA_DIR}' を作成します。")
        os.makedirs(DATA_DIR)

    # --- 以下はRenderデプロイ時にのみ意味を持つ処理 ---
    files_to_write = {
        "google-credentials.json": settings.GOOGLE_CREDENTIALS_JSON,
        "client_secret.json": settings.CLIENT_SECRET_JSON,
    }

    for filename, content in files_to_write.items():
        filepath = os.path.join(DATA_DIR, filename)
        if content and not os.path.exists(filepath):
            print(f"環境変数から '{filename}' を書き出します。")
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(content)

    token_filepath = settings.TOKEN_PICKLE_FILE
    if settings.YOUTUBE_TOKEN_BASE64 and not os.path.exists(token_filepath):
        print("環境変数から 'token.pickle' をデコードして書き出します。")
        try:
            decoded_token = base64.b64decode(settings.YOUTUBE_TOKEN_BASE64)
            with open(token_filepath, "wb") as f:
                f.write(decoded_token)
        except Exception as e:
            print(f"token.pickleのデコード中にエラーが発生しました: {e}")

    print("起動時処理が完了しました。LINEから「起動」コマンドを送信してください。")


@app.on_event("shutdown")
async def shutdown_event():
    """アプリケーション終了時に実行されるイベント"""
    print("アプリケーションをシャットダウンします。")
    if bot_state.is_running and bot_state.bot_task:
        print("実行中のボットタスクをキャンセルします...")
        bot_state.bot_task.cancel()
        try:
            # タスクのキャンセルが完了するのを待つ
            await bot_state.bot_task
        except asyncio.CancelledError:
            print("ボットタスクは正常にキャンセルされました。")
        except Exception as e:
            print(f"シャットダウン中のタスク待機でエラーが発生しました: {e}")
    print("シャットダウン処理が完了しました。")


# LINEからのWebhookを受け取るルーターを登録
app.include_router(line_webhook.router, prefix="/api/v1/line", tags=["line"])


@app.get("/", tags=["Root"], include_in_schema=False)
async def read_root():
    """サーバーの稼働状況を確認するためのエンドポイント"""
    return JSONResponse(content={"status": "YouTube Bot is running"})
