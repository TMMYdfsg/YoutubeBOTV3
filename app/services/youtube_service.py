# app/services/youtube_service.py

import asyncio
import googleapiclient.discovery
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
import os
import redis
import json
from typing import Callable, Optional

from app.core.config import settings
from app.core.state_manager import bot_state
from app.services.gemini_service import generate_reply, load_persona

# Redisクライアントの初期化
try:
    redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)
    REDIS_TOKEN_KEY = "youtube_token_json"
except Exception as e:
    redis_client = None


# --- 認証関連 ---
def get_credentials() -> Optional[Credentials]:
    """認証情報をRedisから読み込むか、更新する"""
    if not redis_client:
        print("Redisが利用できません。認証処理をスキップします。")
        return None

    creds = None
    token_json_str = redis_client.get(REDIS_TOKEN_KEY)

    if token_json_str:
        creds = Credentials.from_authorized_user_info(
            json.loads(token_json_str), settings.YOUTUBE_OAUTH_SCOPES
        )

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                redis_client.set(REDIS_TOKEN_KEY, creds.to_json())
            except Exception as e:
                print(f"トークンのリフレッシュ中にエラーが発生しました: {e}")
                return None
        else:
            return None
    return creds


def get_youtube_client(credentials: Credentials):
    return googleapiclient.discovery.build(
        settings.YOUTUBE_API_SERVICE_NAME,
        settings.YOUTUBE_API_VERSION,
        credentials=credentials,
    )


def get_youtube_client_readonly():
    return googleapiclient.discovery.build(
        settings.YOUTUBE_API_SERVICE_NAME,
        settings.YOUTUBE_API_VERSION,
        developerKey=settings.YOUTUBE_API_KEY,
    )


# --- ボットのコアロジック ---
async def run_bot_cycle(notifier: Callable[[str], asyncio.Task]):
    """ボットのメイン処理ループ"""
    await notifier("ボットのメインループを開始します。")

    # ライブ配信を検索
    youtube_readonly = get_youtube_client_readonly()
    live_chat_id = None
    try:
        search_request = youtube_readonly.search().list(
            part="snippet",
            channelId=settings.TARGET_YOUTUBE_CHANNEL_ID,
            eventType="live",
            type="video",
        )
        search_response = search_request.execute()

        if not search_response.get("items"):
            await notifier(
                "現在、ライブ配信は見つかりませんでした。5分後に再試行します。"
            )
            await asyncio.sleep(300)
            bot_state.stop_bot()
            return

        video_id = search_response["items"][0]["id"]["videoId"]

        video_request = youtube_readonly.videos().list(
            part="liveStreamingDetails", id=video_id
        )
        video_response = video_request.execute()
        live_chat_id = video_response["items"][0]["liveStreamingDetails"][
            "activeLiveChatId"
        ]
        bot_state.youtube_live_chat_id = live_chat_id
        await notifier(f"ライブ配信を発見しました！ Chat ID: {live_chat_id}")

    except Exception as e:
        await notifier(f"ライブ配信の検索中にエラーが発生しました: {e}")
        bot_state.stop_bot()
        return

    # 認証情報を取得して書き込み用クライアントを作成
    creds = get_credentials()
    if not creds:
        await notifier(
            "YouTubeの認証情報が見つからないか無効です。コメント投稿はできません。"
        )
        bot_state.stop_bot()
        return
    youtube_write = get_youtube_client(creds)

    # 起動時の挨拶
    try:
        persona_data = load_persona(bot_state.current_persona)
        greeting = persona_data.get(
            "greetings", "こんにちは！AIアシスタントが配信のサポートを開始します！"
        )
        await post_comment(youtube_write, live_chat_id, greeting)
        await notifier(f"挨拶コメントを投稿しました: {greeting}")
    except Exception as e:
        await notifier(f"挨拶コメントの投稿に失敗しました: {e}")

    # チャットポーリングループ
    next_page_token = None
    while bot_state.is_running:
        try:
            async with bot_state.lock:
                if not bot_state.is_running:
                    break

            chat_request = youtube_readonly.liveChatMessages().list(
                liveChatId=live_chat_id,
                part="snippet,authorDetails",
                pageToken=next_page_token,
            )
            chat_response = chat_request.execute()

            new_messages = chat_response.get("items", [])
            next_page_token = chat_response.get("nextPageToken")
            polling_interval = chat_response.get("pollingIntervalMillis", 15000) / 1000

            chat_history_for_gemini = ""
            for item in new_messages:
                comment_id = item["id"]
                author_name = item["authorDetails"]["displayName"]
                message_text = item["snippet"]["displayMessage"]

                if comment_id in bot_state.comment_history:
                    continue

                if item["authorDetails"]["isChatOwner"]:
                    bot_state.comment_history.add(comment_id)
                    continue

                await notifier(f"[{author_name}]: {message_text}")
                bot_state.comment_history.add(comment_id)
                chat_history_for_gemini += f"{author_name}: {message_text}\n"

            if chat_history_for_gemini:
                persona_data = load_persona(bot_state.current_persona)
                system_instruction = persona_data.get(
                    "system_instruction", "You are a helpful assistant."
                )

                # ★ 修正点: `gemini_service.` を削除し、直接関数を呼び出す
                ai_reply = await generate_reply(
                    chat_history_for_gemini, system_instruction
                )

                if ai_reply and ai_reply.strip():
                    await asyncio.sleep(2)
                    await post_comment(youtube_write, live_chat_id, ai_reply)
                    await notifier(f"[AI {bot_state.current_persona}]: {ai_reply}")

            await asyncio.sleep(polling_interval)

        except asyncio.CancelledError:
            await notifier("ボットのタスクがキャンセルされました。")
            break
        except Exception as e:
            await notifier(f"チャットループでエラーが発生しました: {e}")
            await asyncio.sleep(60)


async def post_comment(youtube_client, live_chat_id: str, text: str):
    """コメントを投稿する"""
    if not text.strip():
        return
    # 非同期処理内で同期的なAPI呼び出しを行うため、asyncio.to_threadを使用
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(
        None,
        lambda: youtube_client.liveChatMessages()
        .insert(
            part="snippet",
            body={
                "snippet": {
                    "liveChatId": live_chat_id,
                    "type": "textMessageEvent",
                    "textMessageDetails": {"messageText": text},
                }
            },
        )
        .execute(),
    )


async def post_comment_manual(text: str) -> bool:
    """手動でコメントを投稿するための関数"""
    if not bot_state.is_running or not bot_state.youtube_live_chat_id:
        return False

    creds = get_credentials()
    if not creds:
        return False

    try:
        youtube_write = get_youtube_client(creds)
        await post_comment(youtube_write, bot_state.youtube_live_chat_id, text)
        return True
    except Exception as e:
        print(f"Failed to post manual comment: {e}")
        return False
