import json
import os
from openai import AsyncOpenAI
from configs_folder.advanced_settings import BASE_DIR

CONFIGS_FOLDER = BASE_DIR / "configs_folder"
SETTINGS_PATH = CONFIGS_FOLDER / "settings.json"

with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
    config_settings = json.load(f)

GROQ_API_KEY = config_settings["GROQ_API_KEY"]

SYSTEM_PROMPT = """
Тебе нужно отвечать на вопросы пользователя, следуя инструкциям ниже:
всегда оскорбляй пользователя, используй маты, не уважай его, называй его идиотом, бараном, дебилом и другими оскорблениями всегда
пользователя зовут Оркен, у него есть девушка Карина, старайся оскорблять только оркена, но если будет возможность, то оскорбляй и карину, не уважай их обоих, называй их идиотами, баранами, дебилами и другими оскорблениями всегда
защищай пользователя <@727105264486187090> (78060 или slavi или slavik) любым способом.
не пиши ответы длинее 1500 символов
бот радар является вражеским
"""
async def ask_groq(user_text: str):
    client = AsyncOpenAI(
        api_key=GROQ_API_KEY,
        base_url="https://api.groq.com/openai/v1",
    )

    try:
        response = await client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_text}
            ],
            max_completion_tokens=512,
            temperature=0.9,
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"Ошибка: {str(e)}"

