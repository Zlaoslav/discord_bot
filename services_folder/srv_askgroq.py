import json
import os
from openai import AsyncOpenAI
from configs_folder.advanced_settings import BASE_DIR, GROQ_SYSTEM_PROMPT

CONFIGS_FOLDER = BASE_DIR / "configs_folder"
SETTINGS_PATH = CONFIGS_FOLDER / "settings.json"

with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
    config_settings = json.load(f)

GROQ_API_KEY = config_settings["GROQ_API_KEY"]

async def ask_groq(user_text: str):
    client = AsyncOpenAI(
        api_key=GROQ_API_KEY,
        base_url="https://api.groq.com/openai/v1",
    )

    try:
        response = await client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": GROQ_SYSTEM_PROMPT},
                {"role": "user", "content": user_text}
            ],
            max_completion_tokens=512,
            temperature=0.9,
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"Ошибка: {str(e)}"

