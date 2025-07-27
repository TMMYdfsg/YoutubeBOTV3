# app/main.py
import os
import json
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from supabase import create_client, Client

from app.api.endpoints import line_webhook
from app.core.config import settings

app = FastAPI(title="YouTube Live Comment Bot", version="1.2.0-supabase")


@app.on_event("startup")
def startup_event():
    """アプリケーション起動時に実行されるイベント"""
    print("アプリケーションが起動しました。")

    # --- Supabaseへの初回トークン設定 ---
    try:
        supabase: Client = create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)
        response = (
            supabase.table("youtube_tokens")
            .select("service_name")
            .eq("service_name", "youtube")
            .execute()
        )

        if not response.data and settings.YOUTUBE_TOKEN_JSON_INITIAL:
            print("Supabaseに初期トークンを設定します...")
            token_data = json.loads(settings.YOUTUBE_TOKEN_JSON_INITIAL)
            supabase.table("youtube_tokens").insert(
                {"service_name": "youtube", "token_data": token_data}
            ).execute()
            print("初期トークンの設定が完了しました。")
    except Exception as e:
        print(f"Supabaseの初期設定中にエラーが発生しました: {e}")

    print("起動時処理が完了しました。")


app.include_router(line_webhook.router, prefix="/api/v1/line", tags=["line"])


@app.get("/", tags=["Root"])
async def read_root():
    return JSONResponse(content={"status": "YouTube Bot is running"})
