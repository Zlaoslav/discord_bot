from bot import Bot
from configs_folder.advanced_settings import DAILY_REQUEST_LIMIT, BOT_COMMANDS_LIST, GEMINI_SYSTEM_PROMPT
from google import genai

async def get_remaining_requests(bot: Bot, user_id: int) -> int:
    """Возвращает, сколько запросов осталось у пользователя сегодня."""
    used = await bot.db.daily_requests.get_count(user_id)
    rem = DAILY_REQUEST_LIMIT - used
    return rem if rem >= 0 else 0

async def increment_user_daily_count(bot: Bot, user_id: int) -> int:
    return await bot.db.daily_requests.increment(user_id)

gemini_client = genai.Client() # необходимо указать перед запуском os.environ["GEMINI_API_KEY"] = config_setings["GEMINI_TOKEN"]

def ask_gemini(msg: str) -> str:
    """Вызов Gemini с основным системным промптом и пользовательским сообщением.

    Собираем единый текст: системный блок + список команд + пользовательский ввод.
    Возвращает полный ответ без ограничений (разбиение на сообщения делается в обработчике команды).
    """
    full_prompt = (
        "НАЧАЛО СИСТЕМНОГО ПРОМТА\n" + GEMINI_SYSTEM_PROMPT + "\nКОНЕЦ СИСТЕМНОГО ПРОМТА\nНАЧАЛО СПИСКА КОМАНД\n" + BOT_COMMANDS_LIST + "КОНЕЦ СПИСКА КОМАНД\nНАЧАЛО СООБЩЕНИЯ ПОЛЬЗОВАТЕЛЯ" + msg + "КОНЕЦ СООБЩЕНИЯ ПОЛЬЗОВАТЕЛЯ"
    )

    response = gemini_client.models.generate_content(
        model="gemini-2.5-flash-lite",
        contents=full_prompt
    )

    text = getattr(response, "text", None)
    if not text:
        try:
            text = response.output[0].content[0].text
        except Exception:
            text = str(response)

    return text
