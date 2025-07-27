from fastapi import APIRouter, Request, HTTPException
from linebot.v3.webhooks import MessageEvent, TextMessageContent, FollowEvent
from linebot.v3.exceptions import InvalidSignatureError

from app.core.state_manager import bot_state
from app.services.gemini_service import load_persona

# line_serviceから司令塔となる関数をインポート
from app.services.line_service import (
    handler,
    reply_message,
    push_message_to_admin,
    start_youtube_bot,
    stop_youtube_bot,
)

# 手動投稿機能もインポート
from app.services.youtube_service import post_comment_manual

router = APIRouter()


@router.post("/callback")
async def line_webhook(request: Request):
    signature = request.headers.get("X-Line-Signature")
    if not signature:
        raise HTTPException(
            status_code=400, detail="X-Line-Signature header is required"
        )
    body = await request.body()
    try:
        await handler.handle(body.decode(), signature)
    except InvalidSignatureError:
        raise HTTPException(status_code=400, detail="Invalid signature")
    return "OK"


@handler.add(MessageEvent, message=TextMessageContent)
async def handle_text_message(event: MessageEvent):
    """テキストメッセージをコマンドとして処理する"""
    text = event.message.text.strip()

    try:
        if text.lower() == "起動":
            if start_youtube_bot():
                await reply_message(event.reply_token, "ボットを起動します。")
            else:
                await reply_message(event.reply_token, "ボットは既に起動しています。")

        elif text.lower() == "停止":
            if await stop_youtube_bot():
                await reply_message(event.reply_token, "ボットを停止処理に入ります。")
            else:
                await reply_message(event.reply_token, "ボットは現在停止しています。")

        elif text.lower().startswith("ペルソナ"):
            parts = text.split()
            if len(parts) > 1:
                persona_name = parts[1]
                try:
                    persona_data = load_persona(persona_name)
                    bot_state.current_persona = persona_name
                    reply_text = f"ペルソナを『{persona_data.get('persona_name', persona_name)}』に変更しました。"
                    await reply_message(event.reply_token, reply_text)
                except FileNotFoundError:
                    await reply_message(
                        event.reply_token,
                        f"ペルソナ '{persona_name}' が見つかりません。",
                    )
            else:
                await reply_message(
                    event.reply_token,
                    "ペルソナ名を指定してください。(例: ペルソナ default)",
                )

        else:  # コマンド以外は手動コメントとして処理
            if not bot_state.is_running or not bot_state.youtube_live_chat_id:
                await reply_message(
                    event.reply_token,
                    "ボットが起動していないか、ライブ配信が検知されていないため、コメントを投稿できません。",
                )
                return

            if await post_comment_manual(text):
                await reply_message(
                    event.reply_token, f"手動コメントを投稿しました:\n「{text}」"
                )
            else:
                await reply_message(
                    event.reply_token, "手動コメントの投稿に失敗しました。"
                )

    except Exception as e:
        print(f"Error handling text message: {e}")
        await reply_message(
            event.reply_token, f"コマンド処理中にエラーが発生しました: {e}"
        )
