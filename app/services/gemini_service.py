# app/services/gemini_service.py (最新のGemini APIに対応)

import os
import yaml
import google.generativeai as genai
from typing import Dict
from app.core.config import settings

# APIキーを設定
genai.configure(api_key=settings.GEMINI_API_KEY)

# モデルの設定
generation_config = {
    "temperature": 0.8,
    "top_p": 1.0,
    "top_k": 32,
    "max_output_tokens": 2048,
}

safety_settings = [
    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
]

# 最新のAPIのモデル初期化方法
model = genai.GenerativeModel(
    model_name="gemini-1.5-flash",
    generation_config=generation_config,
    safety_settings=safety_settings,
)

PERSONAS_DIR = "personas"


def load_persona(persona_name: str) -> Dict:
    """ペルソナファイルを読み込む"""
    filepath = os.path.join(PERSONAS_DIR, f"{persona_name}.yaml")
    if not os.path.exists(filepath):
        # デフォルトにフォールバック
        filepath = os.path.join(PERSONAS_DIR, "default.yaml")
        if not os.path.exists(filepath):
            raise FileNotFoundError("Default persona file not found.")
    with open(filepath, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


async def generate_reply(chat_history: str, system_instruction: str) -> str:
    """AIによる返信を生成する (最新APIバージョン)"""
    try:
        # system_instruction を持つ一時的なモデルインスタンスを作成
        convo_model = genai.GenerativeModel(
            model_name="gemini-1.5-flash",
            generation_config=generation_config,
            safety_settings=safety_settings,
            system_instruction=system_instruction,
        )
        response = await convo_model.generate_content_async(chat_history)
        return response.text
    except Exception as e:
        print(f"Error generating reply: {e}")
        return "すみません、ちょっと考えがまとまりませんでした…"
