import os
import re
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes
from telegram.error import BadRequest, TelegramError
import asyncio
from aiohttp import web
from dotenv import load_dotenv

# Загрузка переменных из .env файла
load_dotenv()

# Получаем переменные окружения
TOKEN = os.environ.get("TOKEN")
OWNER_ID = int(os.environ.get("OWNER_ID")) if os.environ.get("OWNER_ID") else None
PROTECTED_CHANNEL_ID = int(os.environ.get("PROTECTED_CHANNEL_ID")) if os.environ.get("PROTECTED_CHANNEL_ID") else None
PORT = int(os.environ.get("PORT", 8080))
WEBHOOK_URL = os.environ.get("WEBHOOK_URL")
NOTIFY_OWNER = os.environ.get("NOTIFY_OWNER", "false").lower() == "true"
STOPWORDS_FILE = os.environ.get("STOPWORDS_FILE", "stopwords.txt")
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
LOG_FILE = os.environ.get("LOG_FILE", "antispam_bot.log")

# ============================================================
# НАСТРОЙКА ДЕТАЛЬНОГО ЛОГИРОВАНИЯ
# ============================================================

detailed_formatter = logging.Formatter(
    '%(asctime)s | %(levelname)-8s | %(name)s | %(funcName)s:%(lineno)d | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

console_formatter = logging.Formatter(
    '%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%H:%M:%S'
)

logger = logging.getLogger(__name__)
logger.setLevel(getattr(logging, LOG_LEVEL))

console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(console_formatter)

file_handler = RotatingFileHandler(
    LOG_FILE,
    maxBytes=10 * 1024 * 1024,
    backupCount=5,
    encoding='utf-8'
)
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(detailed_formatter)

logger.addHandler(console_handler)
logger.addHandler(file_handler)

logging.getLogger('httpx').setLevel(logging.WARNING)
logging.getLogger('telegram').setLevel(logging.WARNING)
logging.getLogger('aiohttp').setLevel(logging.WARNING)

# ============================================================
# ПРОВЕРКА ПЕРЕМЕННЫХ ОКРУЖЕНИЯ
# ============================================================

if not TOKEN or OWNER_ID is None or PROTECTED_CHANNEL_ID is None:
    logger.error("🚫 Отсутствуют обязательные переменные окружения")
    logger.error(f"TOKEN: {'✓' if TOKEN else '✗'}")
    logger.error(f"OWNER_ID: {'✓' if OWNER_ID else '✗'}")
    logger.error(f"PROTECTED_CHANNEL_ID: {'✓' if PROTECTED_CHANNEL_ID else '✗'}")
    raise ValueError("Отсутствуют TOKEN, OWNER_ID или PROTECTED_CHANNEL_ID")

# Счетчики статистики
deleted_count = 0
checked_count = 0
spam_by_pattern = {}


def load_stopwords(filepath: str) -> list:
    """Загружает стоп-слова из файла и компилирует их в регулярные выражения."""
    logger.info(f"📂 Загрузка стоп-слов из файла: {filepath}")
    patterns = []

    if not os.path.exists(filepath):
        logger.warning(f"⚠️ Файл стоп-слов не найден: {filepath}")
        logger.warning("⚠️ Используется базовая защита только от URL")
        patterns.append(re.compile(r"https?://|www\.|t\.me/", re.IGNORECASE))
        return patterns

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        logger.debug(f"📄 Прочитано строк из файла: {len(lines)}")

        for line in lines:
            line = line.strip()
            if not line or line.startswith('#'):
                continue

            escaped = re.escape(line)

            if any(x in line for x in
                   ['http', 'www.', 't.me', '.com', '.ru', '.org', '.net', '.bot', '.me', '.xyz', '.top', '.info']):
                pattern = re.compile(escaped, re.IGNORECASE)
                logger.debug(f"  + URL паттерн: {line}")
            else:
                pattern = re.compile(r'\b' + escaped + r'\b', re.IGNORECASE)
                logger.debug(f"  + Слово паттерн: {line}")

            patterns.append(pattern)
            spam_by_pattern[line] = 0

        logger.info(f"✅ Загружено {len(patterns)} стоп-слов из {filepath}")

    except Exception as e:
        logger.error(f"❌ Ошибка загрузки стоп-слов: {e}", exc_info=True)
        patterns.append(re.compile(r"https?://|www\.|t\.me/", re.IGNORECASE))

    return patterns


SPAM_PATTERNS = load_stopwords(STOPWORDS_FILE)


async def check_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Проверяет сообщения на наличие спама и удаляет их."""
    global deleted_count, checked_count

    message = update.effective_message
    if not message:
        logger.debug("⏭️  Пропущено: нет сообщения в update")
        return

    checked_count += 1

    user_info = f"@{message.from_user.username}" if message.from_user and message.from_user.username else f"ID:{message.from_user.id if message.from_user else 'unknown'}"
    chat_info = f"Chat:{message.chat_id}"
    text_preview = (message.text or message.caption or "")[:50]

    logger.debug(f"🔍 Проверка сообщения #{checked_count} | От: {user_info} | {chat_info} | Текст: '{text_preview}...'")

    # Проверяем только защищенный канал
    if message.chat_id != PROTECTED_CHANNEL_ID:
        logger.debug(f"⏭️  Пропущено: другой канал (нужен {PROTECTED_CHANNEL_ID}, получен {message.chat_id})")
        return

    # ВАЖНО: Пропускаем сообщения от имени самого канала
    if message.sender_chat:
        if message.sender_chat.id == PROTECTED_CHANNEL_ID:
            logger.info(f"📢 Пропущено: официальный пост канала")
            return

    # Игнорируем сообщения от ботов
    if message.from_user and message.from_user.is_bot:
        logger.info(f"🤖 Пропущено: сообщение от бота {message.from_user.username}")
        return

    # Пропускаем сообщения владельца
    if message.from_user and message.from_user.id == OWNER_ID:
        logger.debug(f"👤 Пропущено: сообщение от владельца (ID: {OWNER_ID})")
        return

    text = message.text or message.caption or ""

    # Проверка entities
    if message.entities or message.caption_entities:
        entities = message.entities or message.caption_entities
        logger.debug(f"🔗 Найдено entities: {len(entities)}")

        for entity in entities:
            logger.debug(f"  → Entity тип: {entity.type}")

            if entity.type in ["url", "text_link", "mention"]:
                logger.warning(f"⚠️  СПАМ! Entity: {entity.type} | От: {user_info}")
                deleted_count += 1
                await delete_and_notify(message, f"содержит {entity.type}")
                return

    if not text:
        logger.debug("⏭️  Пропущено: нет текста")
        return

    # Проверка по паттернам
    logger.debug(f"🔎 Проверка по {len(SPAM_PATTERNS)} паттернам...")

    for i, pattern in enumerate(SPAM_PATTERNS):
        match = pattern.search(text)
        if match:
            matched_word = match.group()
            logger.warning(f"⚠️  СПАМ! Паттерн #{i + 1}: '{matched_word}' | От: {user_info}")
            logger.warning(f"   Полный текст: '{text}'")

            for stopword in spam_by_pattern:
                if stopword.lower() in matched_word.lower():
                    spam_by_pattern[stopword] += 1
                    break

            deleted_count += 1
            await delete_and_notify(message, f"стоп-слово: '{matched_word}'")
            return

    logger.debug(f"✅ Сообщение чистое")


async def delete_and_notify(message, reason: str):
    """Удаляет сообщение и уведомляет владельца."""
    user = message.from_user
    text_preview = (message.text or message.caption or "")[:100]

    try:
        await message.delete()

        user_info = f"@{user.username or 'no_username'} (ID: {user.id})" if user else "Неизвестный"

        logger.info("=" * 60)
        logger.info(f"🗑️  СООБЩЕНИЕ УДАЛЕНО")
        logger.info(f"👤 От: {user_info}")
        logger.info(f"📝 Причина: {reason}")
        logger.info(f"💬 Текст: {text_preview}")
        logger.info(f"🕐 Время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info(f"📊 Всего удалено: {deleted_count}")
        logger.info("=" * 60)

        if NOTIFY_OWNER and user:
            try:
                notification = (
                    f"🗑️ <b>Удалено спам-сообщение</b>\n\n"
                    f"👤 От: {user.first_name} (@{user.username or 'no_username'})\n"
                    f"🆔 ID: <code>{user.id}</code>\n"
                    f"📝 Причина: {reason}\n"
                    f"💬 Текст: <i>{text_preview}</i>\n"
                    f"🕐 Время: {datetime.now().strftime('%H:%M:%S')}\n"
                    f"📊 Всего удалено: {deleted_count}"
                )
                await message.bot.send_message(
                    chat_id=OWNER_ID,
                    text=notification,
                    parse_mode="HTML"
                )
                logger.debug(f"📬 Уведомление отправлено владельцу")
            except TelegramError as e:
                logger.error(f"❌ Ошибка отправки уведомления: {e}")

    except BadRequest as e:
        logger.error(f"🚫 Не удалось удалить: {e}")
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}", exc_info=True)


async def startup():
    """Инициализация бота при запуске."""
    global deleted_count, checked_count
    deleted_count = 0
    checked_count = 0

    logger.info("=" * 60)
    logger.info("🤖 АНТИСПАМ БОТ - ЗАПУСК (WEBHOOK MODE)")
    logger.info("=" * 60)
    logger.info(f"🛡️  Защищаемый канал ID: {PROTECTED_CHANNEL_ID}")
    logger.info(f"👤 Владелец ID: {OWNER_ID}")
    logger.info(f"📚 Стоп-слов: {len(SPAM_PATTERNS)}")
    logger.info(f"📬 Уведомления: {'включены' if NOTIFY_OWNER else 'выключены'}")
    logger.info(f"📢 Посты канала: НЕ проверяются")
    logger.info(f"👮 Защита владельца: ВКЛЮЧЕНА")
    logger.info(f"📝 Уровень логов: {LOG_LEVEL}")
    logger.info(f"🌐 Порт: {PORT}")

    if WEBHOOK_URL:
        logger.info(f"🔗 Webhook URL: {WEBHOOK_URL}")
    else:
        logger.warning("⚠️  WEBHOOK_URL не указан - установите его для работы на сервере!")

    logger.info("=" * 60)

    # Устанавливаем webhook, если указан URL
    if WEBHOOK_URL:
        try:
            await application.bot.set_webhook(url=WEBHOOK_URL)
            logger.info(f"✅ Webhook установлен: {WEBHOOK_URL}")
        except Exception as e:
            logger.error(f"❌ Ошибка установки webhook: {e}", exc_info=True)


async def shutdown():
    """Остановка бота."""
    logger.info("=" * 60)
    logger.info("🛑 ОСТАНОВКА БОТА")
    logger.info(f"📊 Проверено: {checked_count} | Удалено: {deleted_count}")

    if deleted_count > 0:
        logger.info(f"\n📈 Топ-5 стоп-слов:")
        sorted_spam = sorted(spam_by_pattern.items(), key=lambda x: x[1], reverse=True)[:5]
        for i, (word, count) in enumerate(sorted_spam, 1):
            if count > 0:
                logger.info(f"   {i}. '{word}': {count} раз")

    logger.info("=" * 60)


# Создаем объект приложения Telegram
application = Application.builder().token(TOKEN).build()
application.add_handler(MessageHandler(
    (filters.TEXT | filters.CAPTION) & ~filters.COMMAND,
    check_message
))


async def webhook_handler(request):
    """Обрабатывает входящие запросы от Telegram."""
    try:
        data = await request.json()
        update = Update.de_json(data, application.bot)

        logger.debug(f"📨 Получен webhook запрос: update_id={update.update_id if update else 'None'}")

        await application.initialize()
        await application.process_update(update)

        return web.Response(text="OK")
    except Exception as e:
        logger.error(f"❌ Ошибка обработки webhook: {e}", exc_info=True)
        return web.Response(text="Error", status=500)


async def health_check(request):
    """Проверка здоровья сервиса."""
    uptime = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    response = (
        f"OK - Bot is running\n"
        f"Stopwords: {len(SPAM_PATTERNS)}\n"
        f"Checked: {checked_count}\n"
        f"Deleted: {deleted_count}\n"
        f"Uptime: {uptime}"
    )
    logger.debug(f"💚 Health check: OK")
    return web.Response(text=response, status=200)


async def get_stats(request):
    """Получить статистику работы бота."""
    stats = {
        "checked": checked_count,
        "deleted": deleted_count,
        "stopwords": len(SPAM_PATTERNS),
        "top_spam": sorted(spam_by_pattern.items(), key=lambda x: x[1], reverse=True)[:10]
    }

    response = f"""
📊 СТАТИСТИКА АНТИСПАМ БОТА

✅ Проверено сообщений: {stats['checked']}
🗑️  Удалено сообщений: {stats['deleted']}
📚 Стоп-слов загружено: {stats['stopwords']}

🔥 Топ-10 стоп-слов:
"""
    for i, (word, count) in enumerate(stats['top_spam'], 1):
        if count > 0:
            response += f"{i}. '{word}': {count} раз\n"

    logger.info(f"📊 Запрошена статистика")
    return web.Response(text=response, status=200)


async def reload_stopwords(request):
    """Перезагрузка стоп-слов без перезапуска бота."""
    global SPAM_PATTERNS, spam_by_pattern

    logger.info("🔄 Начало перезагрузки стоп-слов...")

    try:
        old_count = len(SPAM_PATTERNS)
        SPAM_PATTERNS = load_stopwords(STOPWORDS_FILE)
        spam_by_pattern = {word: 0 for word in spam_by_pattern}
        new_count = len(SPAM_PATTERNS)

        logger.info(f"✅ Стоп-слова перезагружены: {old_count} → {new_count} паттернов")

        return web.Response(
            text=f"✅ Reloaded: {old_count} → {new_count} stopwords",
            status=200
        )
    except Exception as e:
        logger.error(f"❌ Ошибка перезагрузки стоп-слов: {e}", exc_info=True)
        return web.Response(text=f"Error: {str(e)}", status=500)


async def init_app():
    """Инициализация веб-приложения."""
    await application.initialize()
    await startup()

    app = web.Application()
    app.router.add_post("/", webhook_handler)
    app.router.add_get("/health", health_check)
    app.router.add_get("/stats", get_stats)
    app.router.add_post("/reload", reload_stopwords)

    return app


if __name__ == "__main__":
    logger.info(f"🚀 Запускаем веб-сервер на порту {PORT}...")

    # Создаем и запускаем приложение
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    app = loop.run_until_complete(init_app())

    try:
        web.run_app(app, port=PORT)
    except KeyboardInterrupt:
        logger.info("⚠️  Получен сигнал остановки (Ctrl+C)")
    finally:
        loop.run_until_complete(shutdown())
        loop.run_until_complete(application.shutdown())