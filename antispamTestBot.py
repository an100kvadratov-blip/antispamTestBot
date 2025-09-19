import os
import re
import logging
from logging.handlers import RotatingFileHandler
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes
from telegram.error import BadRequest, RetryAfter
from dotenv import load_dotenv
import asyncio
import time

# Загружаем переменные окружения
load_dotenv()

# Настраиваем логирование (файл + консоль)
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Логи в файл с ротацией
file_handler = RotatingFileHandler("bot.log", maxBytes=5*1024*1024, backupCount=2)
file_handler.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
logger.addHandler(file_handler)

# Логи в консоль
console_handler = logging.StreamHandler()
console_handler.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
logger.addHandler(console_handler)

logging.getLogger("httpx").setLevel(logging.WARNING)

# Получаем переменные окружения
TOKEN = os.environ.get("TOKEN")
OWNER_ID = int(os.environ.get("OWNER_ID"))
PROTECTED_CHANNEL_ID = int(os.environ.get("PROTECTED_CHANNEL_ID"))
URL = os.environ.get("URL")
PORT = int(os.environ.get("PORT", 10000))

# Обновленный список паттернов для спама
SPAM_PATTERNS = [
    re.compile(r"https?://|www\.|\.(com|ru|org|net|info|bot|me)/?", re.IGNORECASE),
    re.compile(r"(подработк|заработок|заработать|ваканси|работ[аыу]|работать)", re.IGNORECASE),
    re.compile(r"(пиши\s*(в?\s*(лс|личку|личные|пм|pm|dm))|обращайся|напиши|свяжись)", re.IGNORECASE),
    re.compile(r"(инвест|бизнес|партнер|франшиз|крипт|биткоин)", re.IGNORECASE),
    re.compile(r"(быстры[ей]? деньги|легк[аои]? заработок|на дому|удаленн|удалённ)", re.IGNORECASE),
    re.compile(r"(набор.*(сотрудник|персонал|работник)|требуются|требуется|ищем|для\s+работы)", re.IGNORECASE),
    re.compile(r"\+?\d{10,}|@\w{5,}|контакт|телефон|whatsapp|вайбер", re.IGNORECASE),
    re.compile(r"(бесплатно|бонус|акци|скидк|выгодн|предложен|млм|сетевой|маркетинг)", re.IGNORECASE),
    re.compile(r"(8000|8\s*000|8к|8\s*[кk]|деньги|выплат|получаешь)", re.IGNORECASE),
    re.compile(r"(за\s*4\s*час|несколько\s*дней|нужны\s+люди|без\s+вложений|без\s+опыта)", re.IGNORECASE),
    re.compile(r"(в\s+свободное\s+время|в\s+любое\s+время)", re.IGNORECASE),
]

async def check_bot_permissions(app):
    """Проверяет права бота в канале."""
    try:
        bot = app.bot
        member = await bot.get_chat_member(PROTECTED_CHANNEL_ID, bot.id)
        if not member.can_delete_messages:
            logger.error("🚫 Бот не имеет прав на удаление сообщений в канале %s!", PROTECTED_CHANNEL_ID)
            return False
        logger.info("✅ Бот имеет права на удаление сообщений")
        return True
    except Exception as e:
        logger.error("🚫 Ошибка проверки прав: %s", e)
        return False

async def check_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Проверяет сообщения на наличие спама и удаляет их."""
    logger.info("📨 Получено обновление: chat_id=%s, text=%s", update.effective_chat.id, update.effective_message.text)
    message = update.effective_message
    if not message:
        return

    # Игнорируем сообщения от владельца
    if message.from_user.id == OWNER_ID:
        return

    # Проверяем, находится ли сообщение в защищенном канале
    if message.chat_id != PROTECTED_CHANNEL_ID:
        logger.info("📍 Сообщение получено из незащищенного канала: %s", message.chat_id)
        return

    text = message.text or ""
    # Проверяем t.me в тексте
    if "t.me" in text.lower():
        logger.info("🔍 Найден спам (t.me в тексте) в сообщении от %s", message.from_user.id)
        await delete_message(message)
        return

    # Проверяем на наличие ссылок
    if message.entities:
        for entity in message.entities:
            if entity.type in ["url", "text_link"]:
                logger.info("🔍 Найден спам (ссылка) в сообщении от %s", message.from_user.id)
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
    except BadRequest as e:
        logger.error("🚫 Не удалось удалить сообщение: %s", e)

def run():
    """Запускает бота в режиме опроса."""
    application = Application.builder().token(TOKEN).build()

    # Добавляем обработчик сообщений
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, check_message))

    # Логируем запуск
    logger.info("🚀 Бот запускается...")
    logger.info("🤖 Антиспам-бот запущен!")
    logger.info("📍 Токен: %s...", TOKEN[:10])
    logger.info("👑 ID владельца: [%s]", OWNER_ID)
    logger.info("🛡️ Защищенный канал: %s", PROTECTED_CHANNEL_ID)
    logger.info("📊 Режим детального логирования включен")

    async def start_and_setup():
        await application.initialize()
        permissions_ok = await check_bot_permissions(application)
        if not permissions_ok:
            logger.error("🛑 Бот не запущен из-за отсутствия прав")
            await application.shutdown()
            return

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(start_and_setup())
        logger.info("🚀 Начинаем опрос Telegram на порту %s", os.environ.get("PORT", 10000))
        loop.run_until_complete(application.run_polling(poll_interval=1.0))
    except KeyboardInterrupt:
        loop.run_until_complete(application.stop())
        loop.run_until_complete(application.shutdown())
    finally:
        loop.close()

if __name__ == "__main__":
    run()