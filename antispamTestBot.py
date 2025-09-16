import os
import re
import logging
from telegram import Update
from telegram.ext import Application, MessageHandler, filters
from dotenv import load_dotenv

# Загружаем переменные окружения из .env файла
load_dotenv()

# Включаем логирование
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
# Настраиваем уровень логирования для `httpx`
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

# Получаем переменные окружения
TOKEN = os.environ.get("TOKEN")
OWNER_ID = int(os.environ.get("OWNER_ID"))
PROTECTED_CHANNEL_ID = int(os.environ.get("PROTECTED_CHANNEL_ID"))
URL = os.environ.get("URL")

# Обновленный список ключевых слов и регулярных выражений для спама
SPAM_PATTERNS = [
    re.compile(r"https?://", re.IGNORECASE),
    re.compile(r"www\.", re.IGNORECASE),
    re.compile(r"\.(com|ru|org|net|info|bot|me)/?", re.IGNORECASE),
    re.compile(r"t\.me/", re.IGNORECASE),
    re.compile(r"@[a-zA-Z0-9_]{5,}", re.IGNORECASE),
    re.compile(r"подработк", re.IGNORECASE),
    re.compile(r"заработок", re.IGNORECASE),
    re.compile(r"заработать", re.IGNORECASE),
    re.compile(r"ваканси", re.IGNORECASE),
    re.compile(r"работ[аыу]", re.IGNORECASE),
    re.compile(r"работать", re.IGNORECASE),
    re.compile(r"пиши\s*(в?\s*(лс|личку|личные|пм|pm|dm))", re.IGNORECASE),
    re.compile(r"обращайся", re.IGNORECASE),
    re.compile(r"напиши", re.IGNORECASE),
    re.compile(r"свяжись", re.IGNORECASE),
    re.compile(r"инвест", re.IGNORECASE),
    re.compile(r"бизнес", re.IGNORECASE),
    re.compile(r"партнер", re.IGNORECASE),
    re.compile(r"франшиз", re.IGNORECASE),
    re.compile(r"крипт", re.IGNORECASE),
    re.compile(r"биткоин", re.IGNORECASE),
    re.compile(r"быстры[ей]? деньги", re.IGNORECASE),
    re.compile(r"легк[аои]? заработок", re.IGNORECASE),
    re.compile(r"на дому", re.IGNORECASE),
    re.compile(r"удаленн", re.IGNORECASE),
    re.compile(r"удалённ", re.IGNORECASE),
    re.compile(r"набор.*(сотрудник|персонал|работник)", re.IGNORECASE),
    re.compile(r"требуются", re.IGNORECASE),
    re.compile(r"требуется", re.IGNORECASE),
    re.compile(r"\+?\d{10,}", re.IGNORECASE),
    re.compile(r"@\w{5,}", re.IGNORECASE),
    re.compile(r"контакт", re.IGNORECASE),
    re.compile(r"телефон", re.IGNORECASE),
    re.compile(r"whatsapp", re.IGNORECASE),
    re.compile(r"вайбер", re.IGNORECASE),
    re.compile(r"бесплатно", re.IGNORECASE),
    re.compile(r"бонус", re.IGNORECASE),
    re.compile(r"акци", re.IGNORECASE),
    re.compile(r"скидк", re.IGNORECASE),
    re.compile(r"выгодн", re.IGNORECASE),
    re.compile(r"предложен", re.IGNORECASE),
    re.compile(r"млм", re.IGNORECASE),
    re.compile(r"сетевой", re.IGNORECASE),
    re.compile(r"маркетинг", re.IGNORECASE),
    re.compile(r"8000", re.IGNORECASE),
    re.compile(r"8\s*000", re.IGNORECASE),
    re.compile(r"8к", re.IGNORECASE),
    re.compile(r"8\s*[кk]", re.IGNORECASE),
    re.compile(r"деньги", re.IGNORECASE),
    re.compile(r"выплат", re.IGNORECASE),
    re.compile(r"получаешь", re.IGNORECASE),
    re.compile(r"за\s*4\s*час", re.IGNORECASE),
    re.compile(r"несколько\s*дней", re.IGNORECASE),
    re.compile(r"нужны\s+люди", re.IGNORECASE),
    re.compile(r"требуются", re.IGNORECASE),
    re.compile(r"ищем", re.IGNORECASE),
    re.compile(r"для\s+работы", re.IGNORECASE),
    re.compile(r"удаленn", re.IGNORECASE),
    re.compile(r"подработк", re.IGNORECASE),
    re.compile(r"без\s+вложений", re.IGNORECASE),
    re.compile(r"без\s+опыта", re.IGNORECASE),
    re.compile(r"в\s+свободное\s+время", re.IGNORECASE),
]

async def check_message(update: Update, context):
    """Проверяет сообщения на наличие спама и удаляет их при обнаружении."""
    message = update.effective_message
    if not message:
        return

    # Игнорируем сообщения от владельца
    if message.from_user.id == OWNER_ID:
        return

    # Проверяем, находится ли сообщение в защищенном канале
    if message.chat_id != PROTECTED_CHANNEL_ID:
        logger.info(
            "📍 Сообщение получено из незащищенного канала: %s", message.chat_id
        )
        return

    text = message.text or ""
    # Проверяем на наличие ссылок
    if message.entities:
        for entity in message.entities:
            if entity.type in ["url", "text_link"]:
                if "t.me" in entity.url:
                    logger.info("🔍 Найден спам (t.me ссылка) в сообщении от %s", message.from_user.id)
                    await delete_message(message)
                    return

    # Проверяем на наличие спам-паттернов
    for pattern in SPAM_PATTERNS:
        if pattern.search(text):
            logger.info("🔍 Найден спам (%s) в сообщении от %s", pattern.pattern, message.from_user.id)
            await delete_message(message)
            return

async def delete_message(message):
    """Удаляет сообщение."""
    try:
        await message.delete()
        logger.info("🗑️ УДАЛЕНО спам-сообщение от %s", message.from_user.id)
    except Exception as e:
        logger.error("🚫 Не удалось удалить сообщение: %s", e)

# Функция для создания и настройки приложения
def application():
    """Создает и возвращает объект Application."""
    app = Application.builder().token(TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, check_message))
    return app

def main():
    """Запускает бота."""
    logger.info("🚀 Бот запускается...")
    logger.info("🤖 Антиспам-бот запущен!")
    logger.info("📍 Токен: %s...", TOKEN[:10])
    logger.info("👑 ID владельца: [%s]", OWNER_ID)
    logger.info("🛡️ Защищенный канал: %s", PROTECTED_CHANNEL_ID)
    logger.info("📊 Режим детального логирования включен")

    if URL:
        app = application()
        app.run_webhook(
            listen="0.0.0.0",
            port=int(os.environ.get("PORT", "5000")),
            url_path=TOKEN,
            webhook_url=URL + TOKEN
        )
    else:
        app = application()
        app.run_polling(poll_interval=1.0)

if __name__ == "__main__":
    main()