# app/bot_logic.py
import asyncio
import time
from app.core.state_manager import bot_state
from app.services import youtube_service, gemini_service, line_service


# メインのボット処理ループ
async def run_bot_cycle():
    while True:
        await asyncio.sleep(1)  # CPU負荷軽減のための短い待機
        async with bot_state.lock:
            if not bot_state.is_running:
                continue

            # ライブ配信が見つかっていない場合、検索を試みる
            if not bot_state.target_live_chat_id:
                print("ライブ配信を検索中...")
                live_chat_id = await youtube_service.find_live_chat_id()
                if live_chat_id:
                    bot_state.target_live_chat_id = live_chat_id
                    print(f"ライブ配信を発見しました！ Chat ID: {live_chat_id}")
                    await line_service.push_message_to_admin(
                        f"ライブ配信を発見しました！ボットがコメント監視を開始します。"
                    )
                    # 起動時の挨拶
                    await youtube_service.post_comment(
                        live_chat_id,
                        "こんにちは！AIアシスタントが配信のサポートを開始します！",
                    )
                else:
                    print("ライブ配信が見つかりません。5分後に再試行します。")
                    await asyncio.sleep(300)  # 5分待機
                    continue

            # チャットメッセージを取得
            messages = await youtube_service.get_chat_messages(
                bot_state.target_live_chat_id
            )
            if not messages:
                await asyncio.sleep(10)  # メッセージがない場合は長めに待機
                continue

            for item in messages:
                comment_id = item["id"]
                if comment_id in bot_state.processed_comment_ids:
                    continue

                author_name = item["displayName"]
                comment_text = item["snippet"]["displayMessage"]

                # 自分のコメントは無視
                if (
                    author_name == "YOUR_YOUTUBE_CHANNEL_NAME"
                ):  # ここにご自身のチャンネル名を入れてください
                    bot_state.processed_comment_ids.add(comment_id)
                    continue

                print(f"[{author_name}]: {comment_text}")
                bot_state.processed_comment_ids.add(comment_id)

                # AIによる返信生成
                reply_text = await gemini_service.generate_reply(
                    comment_text, bot_state.current_persona
                )
                if reply_text:
                    await asyncio.sleep(2)  # 少し間を置いて返信
                    await youtube_service.post_comment(
                        bot_state.target_live_chat_id, reply_text
                    )

            await asyncio.sleep(15)  # YouTube APIのクォータを考慮して15秒待機


async def start_bot():
    """ボットを起動する"""
    async with bot_state.lock:
        if bot_state.is_running:
            return "ボットは既に実行中です。"
        bot_state.is_running = True
        bot_state.processed_comment_ids.clear()
        bot_state.target_live_chat_id = None
        return "ボットを起動しました。ライブ配信の検索を開始します。"


async def stop_bot():
    """ボットを停止する"""
    async with bot_state.lock:
        if not bot_state.is_running:
            return "ボットは既に停止しています。"

        if bot_state.target_live_chat_id:
            await line_service.push_message_to_admin("3秒後にボットを停止します。")
            await youtube_service.post_comment(
                bot_state.target_live_chat_id,
                "配信サポートを終了します。お疲れ様でした！",
            )
            await asyncio.sleep(3)

        bot_state.is_running = False
        bot_state.target_live_chat_id = None
        bot_state.processed_comment_ids.clear()
        return "ボットを停止しました。"