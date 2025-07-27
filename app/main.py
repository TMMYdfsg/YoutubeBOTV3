# app/main.py
import asyncio
from fastapi import FastAPI, Request, Response
from fastapi.responses import HTMLResponse

from app.api.endpoints import line_webhook
from app.core.state_manager import bot_state
from app.bot_logic import run_bot_cycle
from app.services import youtube_service
from app.services.line_service import push_message_to_admin

app = FastAPI(title="YouTube Live AI Bot")


# --- ライフサイクルイベント ---
@app.on_event("startup")
async def startup_event():
    # ボットのメインロジックをバックグラウンドタスクとして起動
    bot_state.bot_task = asyncio.create_task(run_bot_cycle())
    print(
        "アプリケーションが起動しました。ボットのバックグラウンドタスクを開始します。"
    )


@app.on_event("shutdown")
async def shutdown_event():
    if bot_state.bot_task:
        bot_state.bot_task.cancel()
        try:
            await bot_state.bot_task
        except asyncio.CancelledError:
            print("ボットタスクが正常にキャンセルされました。")
    print("アプリケーションをシャットダウンします。")


# --- APIルーター ---
app.include_router(line_webhook.router, prefix="/api", tags=["line"])


# --- OAuthコールバック ---
@app.get("/auth/youtube/callback", response_class=HTMLResponse)
async def youtube_auth_callback(request: Request):
    code = request.query_params.get("code")
    if not code:
        return "認証に失敗しました。コードがありません。"

    try:
        youtube_service.exchange_code_for_token(code)
        await push_message_to_admin("YouTube認証が正常に完了しました！")
        return """
        <html>
            <head><title>認証成功</title></head>
            <body>
                <h1>認証に成功しました！</h1>
                <p>このウィンドウは閉じて、LINEアプリに戻ってください。</p>
            </body>
        </html>
        """
    except Exception as e:
        await push_message_to_admin(f"YouTube認証に失敗しました: {e}")
        return f"認証中にエラーが発生しました: {e}"


# --- ルートエンドポイント ---
@app.get("/")
def read_root():
    return {"status": "YouTube Bot is running"}
