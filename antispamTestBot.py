import os
import re
import logging
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from dotenv import load_dotenv
import redis

# Загрузка переменных из .env файла
load_dotenv()

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Получаем переменные окружения
BOT_TOKEN = os.getenv("BOT_TOKEN")
PORT = int(os.environ.get('PORT', 8443))
REDIS_URL = os.getenv("REDIS_URL")
if not BOT_TOKEN:
    logger.error("BOT_TOKEN environment variable is not set!")
    raise ValueError("BOT_TOKEN environment variable is not set!")
if not REDIS_URL:
    logger.error("REDIS_URL environment variable is not set!")
    raise ValueError("REDIS_URL environment variable is not set!")

# Настройка Redis клиента
redis_client = redis.from_url(REDIS_URL)

# ID владельца
OWNER_IDS = [185147632]

# ID канала, сообщения от которого не нужно удалять
PROTECTED_CHANNEL_ID = -1002989870351

# Чёрный список слов и паттернов для фильтрации спама
SPAM_PATTERNS = [
    r"https?://", r"www\.", r"\.(com|ru|org|net|info|bot|me)/?", r"t\.me/", r"@[a-zA-Z0-9_]{5,}",
    r"подработк", r"заработок", r"заработать", r"ваканси", r"работ[аыу]", r"работать",
    r"пиши\s*(в?\s*(лс|личку|личные|пм|pm|dm))", r"обращайся", r"напиши", r"свяжись",
    r"инвест", r"бизнес", r"партнер", r"франшиз", r"крипт", r"биткоин",
    r"быстры[ей]? деньги", r"легк[аои]? заработок", r"на дому", r"удаленн", r"удалённ",
    r"набор.*(сотрудник|персонал|работник)", r"требуются", r"требуется",
    r"\+?\d{10,}", r"@\w{5,}", r"контакт", r"телефон", r"whatsapp", r"вайбер",
    r"бесплатно", r"бонус", r"акци", r"скидк", r"выгодн", r"предложен",
    r"млм", r"сетевой", r"маркетинг", r"8000", r"8\s*000", r"8к", r"8\s*[кk]",
    r"деньги", r"выплат", r"получаешь", r"за\s*4\s*час", r"несколько\s*дней",
    r"нужны\s+люди", r"требуются", r"ищем", r"для\s+работы", r"удаленn",
    r"подработк", r"без\s+вложений", r"без\s+опыта", r"в\s+свободное\s+время"
]

# Время в течение которого пользователь считается новым (24 часа)
NEW_USER_TIME = timedelta(hours=24)


class AntiSpamBot:
    def __init__(self):
        self.compiled_patterns = [re.compile(pattern, re.IGNORECASE) for pattern in SPAM_PATTERNS]

    def is_spam(self, text: str) -> bool:
        """Проверяет текст на наличие спам-паттернов"""
        if not text:
            return False
        text_lower = text.lower()
        spam_keywords = ["http", "www", ".com", ".ru", ".org", "@", "t.me", "подработ", "заработ", "+ лс", "пиши",
                         "набор"]
        if any(keyword in text_lower for keyword in spam_keywords):
            return True
        for pattern in self.compiled_patterns:
            if pattern.search(text):
                return True
        return False

    async def is_new_user(self, chat_id: int, user_id: int) -> bool:
        """Проверяет, является ли пользователь новым (используя Redis)"""
        join_time_str = redis_client.get(f"user_join:{chat_id}:{user_id}")
        if not join_time_str:
            return False
        try:
            join_time = datetime.fromisoformat(join_time_str.decode())
            return datetime.now() - join_time < NEW_USER_TIME
        except (ValueError, TypeError) as e:
            logger.error(f"❌ Ошибка при парсинге времени из Redis: {e}")
            return False

    async def track_user_join(self, chat_id: int, user_id: int):
        """Записывает время вступления пользователя в Redis"""
        redis_client.set(f"user_join:{chat_id}:{user_id}", datetime.now().isoformat())
        logger.info(f"📥 User {user_id} joined chat {chat_id}")

    async def is_admin_or_owner(self, message, context: ContextTypes.DEFAULT_TYPE) -> bool:
        """Проверяет, является ли пользователь администратором или владельцем"""
        try:
            user_id = message.from_user.id
            if user_id in OWNER_IDS:
                logger.info(f"👑 Сообщение от владельца: {message.from_user.first_name} (ID: {user_id})")
                return True
            chat_member = await context.bot.get_chat_member(message.chat.id, user_id)
            if chat_member.status in ['creator', 'administrator']:
                logger.info(f"⚡ Сообщение от администратора: {message.from_user.first_name} (ID: {user_id})")
                return True
        except Exception as e:
            logger.error(f"❌ Ошибка проверки прав: {e}")
        return False


# Создаем экземпляр бота
antispam_bot = AntiSpamBot()


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    try:
        await update.message.reply_text(
            "🚫 Антиспам-бот активирован!\n\n"
            "Добавьте меня в группу как администратора с правами:\n"
            "• Удаление сообщений\n• Блокировка пользователей\n\n"
            "Я буду автоматически удалять спам!"
        )
        logger.info("✅ Start command received")
    except Exception as e:
        logger.error(f"❌ Error in start command: {e}")


async def myid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает ID пользователя"""
    try:
        user_id = update.message.from_user.id
        await update.message.reply_text(f"🆔 Ваш ID: `{user_id}`", parse_mode='Markdown')
        logger.info(f"📋 User {user_id} requested their ID")
    except Exception as e:
        logger.error(f"❌ Error in myid command: {e}")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик всех сообщений"""
    try:
        message = update.message
        if not message or not message.from_user:
            return
        chat_id = message.chat_id
        user_id = message.from_user.id
        user_name = message.from_user.first_name
        text = message.text or message.caption or ""
        logger.info(f"📨 Получено сообщение: Чат ID: {chat_id}, User: {user_name} (ID: {user_id})")
        if message.from_user.is_bot:
            logger.info(f"🤖 Пропущено сообщение от бота: {user_name} (ID: {user_id})")
            return
        if user_id == 777000:
            logger.info(f"📢 Пропущено служебное сообщение от Telegram (ID: 777000)")
            return
        if chat_id == PROTECTED_CHANNEL_ID:
            logger.info(f"🛡️ СООБЩЕНИЕ ИЗ ЗАЩИЩЕННОГО КАНАЛА! Пропускаем: Чат ID: {chat_id}")
            logger.info(f"🛡️ Текст сообщения: {text[:100]}...")
            return
        if await antispam_bot.is_admin_or_owner(message, context):
            logger.info(f"⚡ Пропущено сообщение от администратора/владельца: {user_name} (ID: {user_id})")
            return
        if antispam_bot.is_spam(text):
            logger.info(f"🔍 Найден спам в сообщении от {user_name} (ID: {user_id})")
            logger.info(f"🔍 Текст спама: {text[:100]}...")
            try:
                await message.delete()
                logger.info(f"🗑️ УДАЛЕНО спам-сообщение от {user_name} (ID: {user_id}) в чате {chat_id}")
            except Exception as e:
                logger.error(f"❌ Ошибка удаления сообщения: {e}")
        else:
            logger.info(f"✅ Сообщение от {user_name} (ID: {user_id}) - не спам, пропускаем")
    except Exception as e:
        logger.error(f"❌ Ошибка в handle_message: {e}")


async def handle_new_members(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик новых участников"""
    try:
        chat_id = update.message.chat_id
        for member in update.message.new_chat_members:
            if not member.is_bot:
                await antispam_bot.track_user_join(chat_id, member.id)
                logger.info(f"👥 Новый участник: {member.first_name} (ID: {member.id}) в чате {chat_id}")
        logger.info(f"📥 New members joined chat {chat_id}")
    except Exception as e:
        logger.error(f"❌ Error in handle_new_members: {e}")


async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик ошибок"""
    logger.error(f"❌ Exception while handling an update: {context.error}")


def main():
    """Основная функция запуска бота"""
    try:
        application = Application.builder().token(BOT_TOKEN).build()
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("myid", myid))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        application.add_handler(MessageHandler(filters.CAPTION, handle_message))
        application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, handle_new_members))
        application.add_error_handler(error_handler)
        logger.info("🚀 Бот запускается...")
        print("🤖 Антиспам-бот запущен!")
        print("📍 Токен:", BOT_TOKEN[:10] + "..." if BOT_TOKEN else "Not set")
        print("👑 ID владельца:", OWNER_IDS)
        print("🛡️ Защищенный канал:", PROTECTED_CHANNEL_ID)
        print("📊 Режим детального логирования включен")

        # Запуск бота с вебхуком
        application.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            url_path=BOT_TOKEN,
            webhook_url=f"https://{os.environ.get('HEROKU_APP_NAME')}.herokuapp.com/{BOT_TOKEN}"
        )
    except Exception as e:
        logger.critical(f"💥 Failed to start bot: {e}")
        raise


if __name__ == "__main__":
    main()