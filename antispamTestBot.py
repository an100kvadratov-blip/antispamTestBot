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

# Список ключевых слов и регулярных выражений для спама
SPAM_PATTERNS = [
    re.compile(r"заработок", re.IGNORECASE),
    re.compile(r"быстрый доход", re.IGNORECASE),
    re.compile(r"бинарные опционы", re.IGNORECASE),
    re.compile(r"криптовалют", re.IGNORECASE),
    re.compile(r"\bакции\b", re.IGNORECASE),
    re.compile(r"\bинвестиции\b", re.IGNORECASE),
    re.compile(r"трейдинг", re.IGNORECASE),
    re.compile(r"подарок", re.IGNORECASE),
    re.compile(r"бесплатно", re.IGNORECASE),
    re.compile(r"канал", re.IGNORECASE),
    re.compile(r"telegram", re.IGNORECASE),
    re.compile(r"whatsapp", re.IGNORECASE),
    re.compile(r"viber", re.IGNORECASE),
    re.compile(r"\bчат\b", re.IGNORECASE),
    re.compile(r"\bписать в лс\b", re.IGNORECASE),
    re.compile(r"https?://t\.me", re.IGNORECASE),
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

# Создаем объект application в глобальной области видимости
application = Application.builder().token(TOKEN).build()
# Добавляем обработчик для всех текстовых сообщений
application.add_handler(
    MessageHandler(filters.TEXT & ~filters.COMMAND, check_message)
)

def main():
    """Запускает бота."""
    logger.info("🚀 Бот запускается...")
    logger.info("🤖 Антиспам-бот запущен!")
    logger.info("📍 Токен: %s...", TOKEN[:10])
    logger.info("👑 ID владельца: [%s]", OWNER_ID)
    logger.info("🛡️ Защищенный канал: %s", PROTECTED_CHANNEL_ID)
    logger.info("📊 Режим детального логирования включен")

    if URL:
        application.run_webhook(
            listen="0.0.0.0",
            port=int(os.environ.get("PORT", "5000")),
            url_path=TOKEN,
            webhook_url=URL + TOKEN
        )
    else:
        application.run_polling(poll_interval=1.0)

if __name__ == "__main__":
    main()