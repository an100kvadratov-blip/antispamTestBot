import os
import re
import logging
from logging.handlers import RotatingFileHandler
from telegram import Update
from telegram.ext import Application, MessageHandler, filters
from telegram.error import BadRequest
from dotenv import load_dotenv
import asyncio

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

async def check_message(update: Update, context):
    """Проверяет сообщения на наличие спама и удаляет их."""
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

def application():
    """Создает и возвращает объект Application."""
    app = Application.builder().token(TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, check_message))
    return app

async def main():
    """Запускает бота."""
    logger.info("🚀 Бот запускается...")
    logger.info("🤖 Антиспам-бот запущен!")
    logger.info("📍 Токен: %s...", TOKEN[:10])
    logger.info("👑 ID владельца: [%s]", OWNER_ID)
    logger.info("🛡️ Защищенный канал: %s", PROTECTED_CHANNEL_ID)
    logger.info("📊 Режим детального логирования включен")

    app = application()
    await app.initialize()  # Инициализируем приложение
    # Проверяем права бота
    if not await check_bot_permissions(app):
        logger.error("🛑 Бот не запущен из-за отсутствия прав")
        await app.shutdown()
        return

    if URL:
        logger.info("🌐 Запуск в режиме webhook: %s", URL)
        await app.start()
        await app.updater.start_webhook(
            listen="0.0.0.0",
            port=int(os.environ.get("PORT", 5000)),
            url_path=TOKEN,
            webhook_url=URL + TOKEN
        )
        # Добавляем задержку перед установкой webhook
        await asyncio.sleep(1)
        await app.bot.set_webhook(url=URL + TOKEN)
        try:
            await asyncio.Event().wait()  # Бесконечное ожидание для webhook
        finally:
            await app.updater.stop()
            await app.stop()
            await app.shutdown()
    else:
        logger.info("📡 Запуск в режиме polling")
        await app.start()
        await app.updater.start_polling(poll_interval=1.0)
        try:
            await asyncio.Event().wait()  # Бесконечное ожидание для polling
        finally:
            await app.updater.stop()
            await app.stop()
            await app.shutdown()

if __name__ == "__main__":
    asyncio.run(main())