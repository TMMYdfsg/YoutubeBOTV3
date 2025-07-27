# app/core/state_manager.py (最終修正版)

import asyncio
from typing import Optional, Set


class BotState:
    """ボットの稼働状態を管理するシングルトンクラス"""

    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(BotState, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        # 初期化が複数回実行されるのを防ぐ
        if not hasattr(self, "initialized"):
            self.is_running: bool = False
            self.current_persona: str = "default"
            self.bot_task: Optional[asyncio.Task] = None
            self.youtube_live_chat_id: Optional[str] = None
            self.comment_history: Set[str] = set()
            # ★ エラーの原因となっていたロック機能を追加
            self.lock = asyncio.Lock()
            self.initialized: bool = True

    def start_bot(self, task: asyncio.Task):
        """ボットを開始状態にする"""
        self.is_running = True
        self.bot_task = task
        self.comment_history.clear()

    def stop_bot(self):
        """ボットを停止状態にする"""
        if self.bot_task and not self.bot_task.done():
            self.bot_task.cancel()
        self.is_running = False
        self.bot_task = None
        self.youtube_live_chat_id = None
        self.comment_history.clear()


# アプリケーション全体で共有するインスタンスを作成
bot_state = BotState()
