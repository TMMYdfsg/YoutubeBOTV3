# app/services/youtube_service.py (YouTube関連ロジックに専念)

import asyncio
import googleapiclient.discovery
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
import os
import pickle
from typing import Callable, Optional

from app.core.config import settings
from app.core.state_manager import bot_state
from app.services.gemini_service import generate_reply, load_persona


# --- 認証関連 ---
def get_credentials() -> Optional[Credentials]:
    """認証情報を読み込むか、更新する"""
    creds = None
    if os.path.exists("token.pickle"):
        with open("token.pickle", "rb") as token:
            creds = pickle.load(token)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                with open("token.pickle", "wb") as token:
                    pickle.dump(creds, token)
            except Exception as e:
                print(f"Error refreshing token: {e}")
                return None
        else:
            # ここでは認証フローを開始しない。認証は別途行う。
            return None
    return creds


# --- APIクライアント作成 ---
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
    await notifier(
        f"ボットのメインループを開始します。チャンネルID: {settings.TARGET_YOUTUBE_CHANNEL_ID}"
    )

    youtube_readonly = get_youtube_client_readonly()
    live_chat_id = None

    # ライブ配信を検索
    try:
        search_request = youtube_readonly.search().list(
            part="snippet",
            channelId=settings.TARGET_YOUTUBE_CHANNEL_ID,
            eventType="live",
            type="video",
        )
        search_response = search_request.execute()

        if not search_response.get("items"):
            await notifier("現在、ライブ配信は見つかりませんでした。")
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
        await notifier(f"ライブ配信を検知しました！ チャットID: {live_chat_id}")

    except Exception as e:
        await notifier(f"ライブ配信の検索中にエラーが発生しました: {e}")
        bot_state.stop_bot()
        return

    # 認証情報を取得して書き込み用クライアントを作成
    creds = get_credentials()
    if not creds:
        await notifier(
            "YouTubeの認証情報(token.pickle)が見つからないか無効です。コメント投稿はできません。"
        )
        bot_state.stop_bot()
        return
    youtube_write = get_youtube_client(creds)

    # 最初の挨拶を投稿
    try:
        persona_data = load_persona(bot_state.current_persona)
        greeting = persona_data.get("greetings", "皆さん、こんにちは！AIボットです。")
        await post_comment(youtube_write, live_chat_id, greeting)
    except Exception as e:
        await notifier(f"挨拶コメントの投稿に失敗しました: {e}")

    # チャットポーリングループ
    last_published_at = None
    while bot_state.is_running:
        try:
            chat_request = youtube_readonly.liveChatMessages().list(
                liveChatId=live_chat_id, part="snippet,authorDetails"
            )
            chat_response = chat_request.execute()

            chat_history_for_gemini = ""
            new_messages = chat_response.get("items", [])

            for item in new_messages:
                comment_id = item["id"]
                author = item["authorDetails"]["displayName"]
                message = item["snippet"]["displayMessage"]

                # 処理済みのコメントはスキップ
                if comment_id in bot_state.comment_history:
                    continue

                bot_state.comment_history.add(comment_id)
                await notifier(f"[{author}]: {message}")
                chat_history_for_gemini += f"{author}: {message}\n"

            # 新しいメッセージがあればAIに返信を依頼
            if chat_history_for_gemini:
                persona_data = load_persona(bot_state.current_persona)
                system_instruction = persona_data.get(
                    "system_instruction", "You are a helpful assistant."
                )

                ai_reply = await generate_reply(
                    chat_history_for_gemini, system_instruction
                )

                if ai_reply:
                    await post_comment(youtube_write, live_chat_id, ai_reply)
                    await notifier(f"[AI {bot_state.current_persona}]: {ai_reply}")
                    bot_state.comment_history.add(
                        f"ai_reply_{comment_id}"
                    )  # AIの返信も履歴に追加

            await asyncio.sleep(15)  # APIクォータを考慮して15秒待機

        except asyncio.CancelledError:
            await notifier("ボットのタスクがキャンセルされました。")
            break
        except Exception as e:
            await notifier(f"チャットループでエラーが発生しました: {e}")
            await asyncio.sleep(60)  # エラー時は長めに待つ


async def post_comment(youtube_client, live_chat_id: str, text: str):
    """コメントを投稿する"""
    if not text.strip():
        return
    request = youtube_client.liveChatMessages().insert(
        part="snippet",
        body={
            "snippet": {
                "liveChatId": live_chat_id,
                "type": "textMessageEvent",
                "textMessageDetails": {"messageText": text},
            }
        },
    )
    request.execute()


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
