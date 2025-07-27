# app/main.py

import os
import redis
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.api.endpoints import line_webhook
from app.core.config import settings

app = FastAPI(
    title="YouTube Live Comment Bot",
    description="A bot that automatically replies to YouTube Live comments using Gemini and is managed via LINE.",
    version="1.1.0-redis",
)


@app.on_event("startup")
def startup_event():
    """
    アプリケーション起動時に実行されるイベント。
    Renderデプロイ時にRedisへ初回トークンを設定します。
    """
    print("アプリケーションが起動しました。")

    # --- Redisへの初回トークン設定 ---
    try:
        # 環境変数からRedisのURLを取得して接続
        redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)
        token_key = "youtube_token_json"

        # Redisにトークンが存在せず、かつ環境変数に初期トークンが設定されている場合のみ書き込む
        if not redis_client.exists(token_key) and settings.YOUTUBE_TOKEN_JSON_INITIAL:
            print("Redisに初期トークンを設定します...")
            redis_client.set(token_key, settings.YOUTUBE_TOKEN_JSON_INITIAL)
            print("初期トークンの設定が完了しました。")

    except Exception as e:
        # Redisへの接続失敗は、ローカル環境では想定内のため、エラーログのみ表示
        print(f"Redisの初期設定中にエラーが発生しました: {e}")

    print("起動時処理が完了しました。")


# LINEからのWebhookを受け取るルーターを登録
app.include_router(line_webhook.router, prefix="/api/v1/line", tags=["line"])


@app.get("/", tags=["Root"])
async def read_root():
    """サーバーの稼働状況を確認するためのエンドポイント"""
    # 正常なJSONレスポンスを返すように修正
    return JSONResponse(content={"status": "YouTube Bot is running"})
