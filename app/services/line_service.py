# app/services/line_service.py (ボットの司令塔)

import asyncio
import json
from typing import List, Optional

from linebot.v3 import WebhookHandler
from linebot.v3.messaging import (
    AsyncApiClient,
    AsyncMessagingApi,
    Configuration,
    TextMessage,
    PushMessageRequest,
    BroadcastRequest,
    ReplyMessageRequest,
)
from linebot.v3.webhooks import MessageEvent, TextMessageContent, FollowEvent

from app.core.config import settings
from app.core.state_manager import bot_state

# youtube_serviceからメインループと手動投稿機能をインポート
from app.services.youtube_service import run_bot_cycle, post_comment_manual
from app.services.gemini_service import load_persona

# --- 設定 ---
configuration = Configuration(access_token=settings.LINE_CHANNEL_ACCESS_TOKEN)
async_api_client = AsyncApiClient(configuration)
line_bot_api = AsyncMessagingApi(async_api_client)
handler = WebhookHandler(settings.LINE_CHANNEL_SECRET)

USER_IDS_FILE = "user_ids.json"


# --- メッセージ送信 ---
async def push_message_to_admin(text: str):
    """管理者（ログ監視者）にプッシュメッセージを送信する"""
    try:
        await line_bot_api.push_message(
            PushMessageRequest(
                to=settings.LINE_ADMIN_USER_ID, messages=[TextMessage(text=text)]
            )
        )
    except Exception as e:
        print(f"Error sending push message to admin: {e}")


async def reply_message(reply_token: str, text: str):
    """コマンド送信者に返信する"""
    try:
        await line_bot_api.reply_message(
            ReplyMessageRequest(
                reply_token=reply_token, messages=[TextMessage(text=text)]
            )
        )
    except Exception as e:
        print(f"Error replying message: {e}")


# --- ボット制御 ---
def start_youtube_bot():
    """YouTubeボットのバックグラウンドタスクを開始する"""
    if bot_state.is_running:
        return False
    # ここで、通知関数として push_message_to_admin を渡す
    task = asyncio.create_task(run_bot_cycle(notifier=push_message_to_admin))
    bot_state.start_bot(task)
    return True


async def stop_youtube_bot():
    """YouTubeボットのタスクを停止する"""
    if not bot_state.is_running:
        return False

    # 終了挨拶を投稿
    try:
        persona_data = load_persona(bot_state.current_persona)
        goodbye = persona_data.get("goodbyes", "本日の配信はこれにて！お疲れ様でした！")
        await post_comment_manual(goodbye)
        await push_message_to_admin(f"終了挨拶を投稿しました: {goodbye}")
    except Exception as e:
        await push_message_to_admin(f"終了挨拶の投稿に失敗しました: {e}")

    # 3秒のカウントダウン
    for i in range(3, 0, -1):
        await push_message_to_admin(f"ボットを {i} 秒後に停止します...")
        await asyncio.sleep(1)

    bot_state.stop_bot()
    return True
