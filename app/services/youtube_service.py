# app/services/youtube_service.py
import asyncio
import googleapiclient.discovery
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
import os
import json
from supabase import create_client, Client
from typing import Callable, Optional

from app.core.config import settings
from app.core.state_manager import bot_state
from app.services.gemini_service import generate_reply, load_persona

# Supabaseクライアントの初期化
try:
    supabase: Client = create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)
    print("Supabaseクライアントの初期化に成功しました。")
except Exception as e:
    print(f"Supabaseクライアントの初期化に失敗しました: {e}")
    supabase = None


def get_credentials() -> Optional[Credentials]:
    """認証情報をSupabaseから読み込むか、更新する"""
    if not supabase:
        return None
    creds = None

    try:
        response = (
            supabase.table("youtube_tokens")
            .select("token_data")
            .eq("service_name", "youtube")
            .execute()
        )
        if response.data:
            token_data = response.data[0]["token_data"]
            creds = Credentials.from_authorized_user_info(
                token_data, settings.YOUTUBE_OAUTH_SCOPES
            )

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
                supabase.table("youtube_tokens").update(
                    {"token_data": json.loads(creds.to_json())}
                ).eq("service_name", "youtube").execute()
            else:
                return None
        return creds
    except Exception as e:
        print(f"Supabaseからの認証情報取得/更新に失敗: {e}")
        return None


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


async def run_bot_cycle(notifier: Callable[[str], asyncio.Task]):
    """ボットのメイン処理ループ"""
    await notifier("ボットのメインループを開始します。")

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

    creds = get_credentials()
    if not creds:
        await notifier(
            "YouTubeの認証情報が見つからないか無効です。コメント投稿はできません。"
        )
        bot_state.stop_bot()
        return
    youtube_write = get_youtube_client(creds)

    try:
        persona_data = load_persona(bot_state.current_persona)
        greeting = persona_data.get(
            "greetings", "こんにちは！AIアシスタントが配信のサポートを開始します！"
        )
        await post_comment(youtube_write, live_chat_id, greeting)
        await notifier(f"挨拶コメントを投稿しました: {greeting}")
    except Exception as e:
        await notifier(f"挨拶コメントの投稿に失敗しました: {e}")

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
                if comment_id in bot_state.comment_history:
                    continue

                author_name = item["authorDetails"]["displayName"]
                message_text = item["snippet"]["displayMessage"]

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
    if not text.strip():
        return
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
