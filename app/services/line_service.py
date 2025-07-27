# app/services/line_service.py

import asyncio
import json
from typing import List

# --- サードパーティライブラリのインポート ---
from supabase import create_client, Client
from linebot.v3 import WebhookHandler
from linebot.v3.messaging import (
    AsyncApiClient,
    AsyncMessagingApi,
    Configuration,
    TextMessage,
    PushMessageRequest,
    ReplyMessageRequest,
)

# --- アプリケーション内モジュールのインポート ---
from app.core.config import settings
from app.core.state_manager import bot_state
from app.services.gemini_service import load_persona
from app.services.youtube_service import run_bot_cycle, post_comment_manual

# --- 初期化セクション ---

# Supabaseクライアントの初期化
try:
    supabase: Client = create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)
    print("Supabaseクライアントの初期化に成功しました。")
except Exception as e:
    print(f"Supabaseクライアントの初期化に失敗しました: {e}")
    supabase = None

# LINE SDKの初期化
try:
    configuration = Configuration(access_token=settings.LINE_CHANNEL_ACCESS_TOKEN)
    async_api_client = AsyncApiClient(configuration)
    line_bot_api = AsyncMessagingApi(async_api_client)
    # ★★★★★ ここが重要 ★★★★★
    # WebhookHandlerを非同期モードで初期化する
    handler = WebhookHandler(settings.LINE_CHANNEL_SECRET, async_mode=True)
    print("LINE SDKの初期化に成功しました。")
except Exception as e:
    print(f"LINE SDKの初期化中にエラーが発生しました: {e}")
    line_bot_api = None
    handler = None


# --- ユーザーID管理 (Supabase対応) ---


def get_all_user_ids() -> List[str]:
    """全てのユーザーIDをSupabaseから読み込む"""
    if not supabase:
        return []
    try:
        response = supabase.table("line_users").select("user_id").execute()
        return [item["user_id"] for item in response.data]
    except Exception as e:
        print(f"SupabaseからのユーザーID取得に失敗: {e}")
        return []


def save_user_id(user_id: str):
    """新しいユーザーIDをSupabaseに保存する"""
    if not supabase:
        return
    try:
        response = (
            supabase.table("line_users")
            .select("user_id")
            .eq("user_id", user_id)
            .execute()
        )
        if not response.data:
            supabase.table("line_users").insert({"user_id": user_id}).execute()
    except Exception as e:
        print(f"SupabaseへのユーザーID保存に失敗: {e}")


# --- メッセージ送信 ---


async def push_message_to_admin(text: str):
    """管理者（ログ監視者）にプッシュメッセージを送信する"""
    if not line_bot_api:
        print(
            "LINE SDKが初期化されていないため、管理者へのプッシュメッセージを送信できません。"
        )
        return
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
    if not line_bot_api:
        print("LINE SDKが初期化されていないため、リプライメッセージを送信できません。")
        return
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
    task = asyncio.create_task(run_bot_cycle(notifier=push_message_to_admin))
    bot_state.start_bot(task)
    return True


async def stop_youtube_bot():
    """YouTubeボットのタスクを停止する"""
    if not bot_state.is_running:
        return False
    try:
        persona_data = load_persona(bot_state.current_persona)
        goodbye = persona_data.get("goodbyes", "本日の配信はこれにて！お疲れ様でした！")
        await post_comment_manual(goodbye)
        await push_message_to_admin(f"終了挨拶を投稿しました: {goodbye}")
    except Exception as e:
        await push_message_to_admin(f"終了挨拶の投稿に失敗しました: {e}")

    for i in range(3, 0, -1):
        await push_message_to_admin(f"ボットを {i} 秒後に停止します...")
        await asyncio.sleep(1)

    bot_state.stop_bot()
    return True
