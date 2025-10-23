import logging
import os
from datetime import datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from telegram.constants import ParseMode
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from database import Database
from scraper import MacOSScraper
import config

# Настройка логирования
log_dir = '/app/data' if os.path.exists('/app/data') else '.'
log_path = os.path.join(log_dir, 'bot.log')

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler(log_path, encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class MacOSUpdateBot:
    def __init__(self):
        self.db = Database()
        self.scraper = MacOSScraper(config.MACOS_URL)
        self.app = Application.builder().token(config.BOT_TOKEN).build()
        self.scheduler = AsyncIOScheduler()
        
        # Регистрация команд
        self.app.add_handler(CommandHandler("start", self.start_command))
        self.app.add_handler(CommandHandler("help", self.help_command))
        self.app.add_handler(CommandHandler("status", self.status_command))
        self.app.add_handler(CommandHandler("latest", self.latest_command))
        self.app.add_handler(CommandHandler("check", self.check_command))
        self.app.add_handler(CommandHandler("myid", self.myid_command))

    def is_authorized(self, user_id: int) -> bool:
        """Проверка авторизации пользователя"""
        return user_id in config.ALLOWED_USER_IDS

    def is_admin(self, user_id: int) -> bool:
        """Проверка прав администратора"""
        return user_id in config.ADMIN_USER_IDS

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /start"""
        user_id = update.effective_user.id
        
        if not self.is_authorized(user_id):
            await update.message.reply_text(
                "⛔ У вас нет доступа к этому боту.\n"
                f"Ваш ID: `{user_id}`\n\n"
                "Обратитесь к администратору для получения доступа.",
                parse_mode=ParseMode.MARKDOWN
            )
            return

        welcome_message = (
            "👋 Привет! Я бот для отслеживания обновлений macOS Sequoia.\n\n"
            "📱 Доступные команды:\n"
            "/start - Это сообщение\n"
            "/help - Справка по командам\n"
            "/status - Статус и последняя проверка\n"
            "/latest - Показать последний релиз\n"
            "/myid - Узнать свой Telegram ID\n"
        )
        
        if self.is_admin(user_id):
            welcome_message += "/check - Принудительная проверка обновлений (админ)\n"

        welcome_message += (
            "\n🔔 Я автоматически проверяю обновления каждые "
            f"{config.CHECK_INTERVAL // 3600} час(а) и присылаю уведомления о новых релизах."
        )

        await update.message.reply_text(welcome_message)

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /help"""
        if not self.is_authorized(update.effective_user.id):
            await update.message.reply_text("⛔ У вас нет доступа к этому боту.")
            return

        help_text = (
            "ℹ️ *Справка по командам*\n\n"
            "/start - Приветствие и список команд\n"
            "/help - Эта справка\n"
            "/status - Показать статус бота и время последней проверки\n"
            "/latest - Показать информацию о последнем релизе\n"
            "/myid - Узнать свой Telegram ID\n"
        )
        
        if self.is_admin(update.effective_user.id):
            help_text += "/check - Запустить проверку обновлений прямо сейчас\n"

        help_text += (
            "\n📋 *О боте:*\n"
            f"Проверяю обновления каждые {config.CHECK_INTERVAL // 3600} час(а).\n"
            "Уведомления отправляются автоматически при обнаружении новых релизов."
        )

        await update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN)

    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /status"""
        if not self.is_authorized(update.effective_user.id):
            await update.message.reply_text("⛔ У вас нет доступа к этому боту.")
            return

        last_check = self.db.get_last_check()
        total_releases = self.db.count_releases()
        
        if last_check:
            check_time = datetime.fromisoformat(last_check['check_time'])
            status_text = (
                "📊 *Статус бота*\n\n"
                f"🕐 Последняя проверка: {check_time.strftime('%d.%m.%Y %H:%M:%S')}\n"
                f"📦 Найдено релизов: {last_check['releases_found']}\n"
                f"🆕 Новых релизов: {last_check['new_releases']}\n"
                f"✅ Статус: {last_check['status']}\n"
                f"💾 Всего в БД: {total_releases}\n\n"
                f"⏱ Интервал проверки: {config.CHECK_INTERVAL // 3600} час(а)"
            )
        else:
            status_text = (
                "📊 *Статус бота*\n\n"
                "Проверок еще не было.\n"
                f"💾 Всего в БД: {total_releases}\n"
                f"⏱ Интервал проверки: {config.CHECK_INTERVAL // 3600} час(а)"
            )

        await update.message.reply_text(status_text, parse_mode=ParseMode.MARKDOWN)

    async def latest_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /latest"""
        if not self.is_authorized(update.effective_user.id):
            await update.message.reply_text("⛔ У вас нет доступа к этому боту.")
            return

        latest_public = self.db.get_latest_release('public')
        latest_beta = self.db.get_latest_release('beta')

        response = "📦 *Последние релизы macOS Sequoia*\n\n"

        if latest_public:
            response += (
                f"🟢 *Public Release*\n"
                f"📦 Версия: {latest_public['version']}\n"
                f"🔨 Build: {latest_public['build']}\n"
                f"📅 Обнаружен: {datetime.fromisoformat(latest_public['date_discovered']).strftime('%d.%m.%Y %H:%M')}\n"
                f"⬇️ [Скачать]({latest_public['download_url']})\n\n"
            )
        else:
            response += "🟢 *Public Release*\nНет данных\n\n"

        if latest_beta:
            response += (
                f"🟡 *Beta Release*\n"
                f"📦 Версия: {latest_beta['version']}\n"
                f"🔨 Build: {latest_beta['build']}\n"
                f"📅 Обнаружен: {datetime.fromisoformat(latest_beta['date_discovered']).strftime('%d.%m.%Y %H:%M')}\n"
                f"⬇️ [Скачать]({latest_beta['download_url']})\n"
            )
        else:
            response += "🟡 *Beta Release*\nНет данных"

        await update.message.reply_text(
            response, 
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=True
        )

    async def check_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /check - только для админов"""
        user_id = update.effective_user.id
        
        if not self.is_authorized(user_id):
            await update.message.reply_text("⛔ У вас нет доступа к этому боту.")
            return

        if not self.is_admin(user_id):
            await update.message.reply_text("⛔ Эта команда доступна только администраторам.")
            return

        await update.message.reply_text("🔄 Запускаю проверку обновлений...")
        
        # Запускаем проверку
        await self.check_for_updates()
        
        await update.message.reply_text("✅ Проверка завершена! Используйте /status для просмотра результатов.")

    async def myid_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /myid"""
        user_id = update.effective_user.id
        username = update.effective_user.username or "не установлен"
        first_name = update.effective_user.first_name or "не указано"
        
        await update.message.reply_text(
            f"👤 *Ваша информация*\n\n"
            f"🆔 ID: `{user_id}`\n"
            f"👤 Имя: {first_name}\n"
            f"📝 Username: @{username}\n\n"
            f"Скопируйте ID и отправьте администратору для получения доступа.",
            parse_mode=ParseMode.MARKDOWN
        )

    async def check_for_updates(self):
        """Проверка обновлений"""
        logger.info("Начинаю проверку обновлений...")
        
        # Проверяем, первый ли это запуск
        is_first_run = self.db.count_releases() == 0
        
        result = self.scraper.scrape()
        
        if not result['success']:
            logger.error(f"Ошибка при проверке: {result['error']}")
            self.db.add_check_history(0, 0, f"Ошибка: {result['error']}")
            return

        releases = result['releases']
        new_releases = []

        # Проверяем каждый релиз
        for release in releases:
            added = self.db.add_release(
                release['version'],
                release['build'],
                release['release_type'],
                release['date_published'],
                release['download_url']
            )
            
            if added:
                new_releases.append(release)

        # Сохраняем историю проверки
        self.db.add_check_history(
            len(releases),
            len(new_releases),
            "Успешно"
        )

        logger.info(f"Проверка завершена. Найдено релизов: {len(releases)}, новых: {len(new_releases)}")

        # Отправляем уведомления о новых релизах
        if new_releases:
            if is_first_run:
                # При первом запуске отправляем только сводку
                logger.info(f"Первый запуск: найдено {len(new_releases)} релизов, отправляю только сводку")
                await self.send_first_run_summary(new_releases)
            else:
                # При обычной работе отправляем уведомления о каждом новом релизе
                await self.send_notifications(new_releases)

    async def send_first_run_summary(self, releases: list):
        """Отправка сводки при первом запуске (вместо спама всеми релизами)"""
        public_releases = [r for r in releases if r['release_type'] == 'public']
        beta_releases = [r for r in releases if r['release_type'] == 'beta']
        
        # Получаем самые новые версии
        latest_public = self.db.get_latest_release('public')
        latest_beta = self.db.get_latest_release('beta')
        
        message = (
            "🎉 *Бот запущен!*\n\n"
            f"Добавлено в базу данных:\n"
            f"🟢 Public релизов: {len(public_releases)}\n"
            f"🟡 Beta релизов: {len(beta_releases)}\n\n"
            "*Последние версии:*\n\n"
        )
        
        if latest_public:
            message += (
                f"🟢 *Public:* {latest_public['version']} (Build {latest_public['build']})\n"
                f"⬇️ [Скачать]({latest_public['download_url']})\n\n"
            )
        
        if latest_beta:
            message += (
                f"🟡 *Beta:* {latest_beta['version']} (Build {latest_beta['build']})\n"
                f"⬇️ [Скачать]({latest_beta['download_url']})\n\n"
            )
        
        message += "Используйте /latest для просмотра последних релизов."
        
        for chat_id in config.NOTIFICATION_TARGETS:
            try:
                await self.app.bot.send_message(
                    chat_id=chat_id,
                    text=message,
                    parse_mode=ParseMode.MARKDOWN,
                    disable_web_page_preview=True
                )
                logger.info(f"Сводка первого запуска отправлена в чат {chat_id}")
            except Exception as e:
                logger.error(f"Ошибка при отправке в чат {chat_id}: {e}")

    async def send_notifications(self, releases: list):
        """Отправка уведомлений о новых релизах"""
        for release in releases:
            message = self.format_release_message(release)
            
            for chat_id in config.NOTIFICATION_TARGETS:
                try:
                    await self.app.bot.send_message(
                        chat_id=chat_id,
                        text=message,
                        parse_mode=ParseMode.MARKDOWN,
                        disable_web_page_preview=True
                    )
                    logger.info(f"Уведомление отправлено в чат {chat_id}")
                    
                    # Отмечаем как уведомленный
                    self.db.mark_as_notified(
                        release['version'],
                        release['build'],
                        release['release_type']
                    )
                except Exception as e:
                    logger.error(f"Ошибка при отправке в чат {chat_id}: {e}")

    def format_release_message(self, release: dict) -> str:
        """Форматирование сообщения о релизе"""
        emoji = "🟢" if release['release_type'] == 'public' else "🟡"
        type_name = "Public Release" if release['release_type'] == 'public' else "Beta Release"
        
        message = (
            f"{emoji} *Новый релиз macOS Sequoia!*\n\n"
            f"📦 Версия: `{release['version']}`\n"
            f"🔨 Build: `{release['build']}`\n"
            f"🏷️ Тип: {type_name}\n"
        )
        
        if release['date_published']:
            message += f"📅 Дата: {release['date_published']}\n"
        
        if release['download_url']:
            message += f"\n⬇️ [Скачать InstallAssistant.pkg]({release['download_url']})\n"
        
        message += "\n💾 Размер: ~13 GB"
        
        return message

    async def scheduled_check(self):
        """Плановая проверка (вызывается по расписанию)"""
        await self.check_for_updates()

    def start(self):
        """Запуск бота"""
        # Настройка планировщика
        self.scheduler.add_job(
            self.scheduled_check,
            'interval',
            seconds=config.CHECK_INTERVAL,
            id='check_updates'
        )
        self.scheduler.start()
        
        logger.info("Бот запущен!")
        logger.info(f"Интервал проверки: {config.CHECK_INTERVAL} секунд")
        logger.info(f"Авторизованные пользователи: {config.ALLOWED_USER_IDS}")
        logger.info(f"Цели уведомлений: {config.NOTIFICATION_TARGETS}")
        
        # Запуск бота
        self.app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    bot = MacOSUpdateBot()
    bot.start()
