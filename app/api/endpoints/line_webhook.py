# app/api/endpoints/line_webhook.py

from fastapi import APIRouter, Request, HTTPException
from linebot.v3.webhooks import MessageEvent, TextMessageContent, FollowEvent
from linebot.v3.exceptions import InvalidSignatureError

# Core state manager
from app.core.state_manager import bot_state

# Service layer imports
from app.services.gemini_service import load_persona
from app.services.line_service import (
    handler,
    reply_message,
    push_message_to_admin,
    start_youtube_bot,
    stop_youtube_bot,
    save_user_id,
)
from app.services.youtube_service import post_comment_manual

router = APIRouter()


@router.post("/callback")
async def line_webhook(request: Request):
    """LINEからのWebhookリクエストを受け取るエンドポイント"""
    # ★★★★★ ここが重要 ★★★★★
    # handlerが正常に初期化されているか最初に確認する
    if handler is None:
        print(
            "[CRITICAL ERROR] LINE Webhook handler is not initialized. Check LINE SDK settings in line_service.py and environment variables."
        )
        # LINEプラットフォームには正常な応答を返し、エラーの連鎖を防ぐ
        # 500エラーを返すとLINEはリトライを試みるため、200 OKを返すのが望ましい
        return "OK"

    signature = request.headers.get("X-Line-Signature")
    body = await request.body()
    try:
        # line-bot-sdkのハンドラに処理を委譲
        await handler.handle(body.decode(), signature)
    except InvalidSignatureError:
        # 署名が無効な場合は400エラーを返す
        raise HTTPException(status_code=400, detail="Invalid signature")
    except Exception as e:
        # 予期せぬエラーを捕捉し、ログに記録
        print(f"[ERROR] An exception occurred during handler.handle: {e}")
        # この場合もLINEには200 OKを返す

    # 処理が正常に完了した場合、LINEに200 OKを返す
    return "OK"


# 友だち追加イベントのハンドラ
@handler.add(FollowEvent)
async def handle_follow(event: FollowEvent):
    """友だち追加イベントを処理する"""
    try:
        user_id = event.source.user_id
        save_user_id(user_id)
        await push_message_to_admin(
            f"新しい友だちが追加されました！\nユーザーID: {user_id}"
        )
    except Exception as e:
        print(f"Error in follow event handler: {e}")


# テキストメッセージイベントのハンドラ
@handler.add(MessageEvent, message=TextMessageContent)
async def handle_text_message(event: MessageEvent):
    """
    テキストメッセージをコマンドとして処理する。
    この関数内で発生するすべての例外を捕捉し、LINEには常に200 OKが返されるようにする。
    """
    try:
        text = event.message.text.strip()

        # --- コマンド分岐 ---
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
        # ★★★★★ ここが重要 ★★★★★
        # 処理中にどんなエラーが発生しても、ここで捕捉する。
        # これにより、サーバーが500エラーを返すのを防ぎ、LINEプラットフォームとの通信を維持する。
        print(
            f"[CRITICAL ERROR] An unhandled exception occurred in handle_text_message: {e}"
        )

        # 管理者にエラーを通知する
        try:
            await push_message_to_admin(
                f"重大なエラーが発生しました。サーバーログを確認してください。\n\nエラータイプ: {type(e).__name__}\nエラー内容: {e}"
            )
        except Exception as push_e:
            print(f"Failed to send critical error notification: {push_e}")
