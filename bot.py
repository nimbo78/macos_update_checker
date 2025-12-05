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


def get_macos_urls() -> dict:
    """Получить словарь URL для мониторинга с поддержкой обратной совместимости"""
    # Новый формат: словарь MACOS_URLS
    if hasattr(config, 'MACOS_URLS') and config.MACOS_URLS:
        return config.MACOS_URLS
    # Старый формат: одиночный MACOS_URL
    if hasattr(config, 'MACOS_URL') and config.MACOS_URL:
        return {"Sequoia": config.MACOS_URL}
    # По умолчанию
    return {"Sequoia": "https://mrmacintosh.com/macos-sequoia-full-installer-database-download-directly-from-apple/"}


class MacOSUpdateBot:
    def __init__(self):
        self.db = Database()
        # Создаём scrapers для каждой версии macOS
        self.macos_urls = get_macos_urls()
        self.scrapers = {
            name: MacOSScraper(url, macos_version=name)
            for name, url in self.macos_urls.items()
        }
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

        macos_versions_list = ", ".join(self.macos_urls.keys())
        welcome_message = (
            f"👋 Привет! Я бот для отслеживания обновлений macOS.\n\n"
            f"🖥️ Отслеживаемые версии: {macos_versions_list}\n\n"
            "📱 Доступные команды:\n"
            "/start - Это сообщение\n"
            "/help - Справка по командам\n"
            "/status - Статус и последняя проверка\n"
            "/latest - Показать последние релизы\n"
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
        releases_by_macos = self.db.count_releases_by_macos()

        if last_check:
            check_time = datetime.fromisoformat(last_check['check_time'])
            status_text = (
                "📊 *Статус бота*\n\n"
                f"🕐 Последняя проверка: {check_time.strftime('%d.%m.%Y %H:%M:%S')}\n"
                f"📦 Найдено релизов: {last_check['releases_found']}\n"
                f"🆕 Новых релизов: {last_check['new_releases']}\n"
                f"✅ Статус: {last_check['status']}\n\n"
                f"💾 *Всего в БД:* {total_releases}\n"
            )
            # Статистика по версиям macOS
            if releases_by_macos:
                for macos_ver, count in sorted(releases_by_macos.items()):
                    status_text += f"  • macOS {macos_ver}: {count}\n"
            status_text += f"\n🖥️ Отслеживаемые версии: {', '.join(self.macos_urls.keys())}\n"
            status_text += f"⏱ Интервал проверки: {config.CHECK_INTERVAL // 3600} час(а)"
        else:
            status_text = (
                "📊 *Статус бота*\n\n"
                "Проверок еще не было.\n"
                f"💾 Всего в БД: {total_releases}\n"
                f"🖥️ Отслеживаемые версии: {', '.join(self.macos_urls.keys())}\n"
                f"⏱ Интервал проверки: {config.CHECK_INTERVAL // 3600} час(а)"
            )

        await update.message.reply_text(status_text, parse_mode=ParseMode.MARKDOWN)

    async def latest_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /latest"""
        if not self.is_authorized(update.effective_user.id):
            await update.message.reply_text("⛔ У вас нет доступа к этому боту.")
            return

        # Получаем последние релизы для каждой версии macOS
        latest_public_by_macos = self.db.get_latest_releases_by_macos('public')
        latest_beta_by_macos = self.db.get_latest_releases_by_macos('beta')

        response = "📦 *Последние релизы macOS*\n\n"

        # Объединяем все версии macOS
        all_macos_versions = set(latest_public_by_macos.keys()) | set(latest_beta_by_macos.keys())

        if not all_macos_versions:
            response += "Нет данных о релизах."
        else:
            for macos_ver in sorted(all_macos_versions, reverse=True):
                response += f"🖥️ *macOS {macos_ver}*\n\n"

                latest_public = latest_public_by_macos.get(macos_ver)
                latest_beta = latest_beta_by_macos.get(macos_ver)

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
                        f"⬇️ [Скачать]({latest_beta['download_url']})\n\n"
                    )
                else:
                    response += "🟡 *Beta Release*\nНет данных\n\n"

                response += "─────────────────\n\n"

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
        """Проверка обновлений для всех версий macOS"""
        logger.info("Начинаю проверку обновлений...")

        # Проверяем, первый ли это запуск
        is_first_run = self.db.count_releases() == 0

        all_releases = []
        all_new_releases = []
        errors = []

        # Проверяем каждую версию macOS
        for macos_name, scraper in self.scrapers.items():
            logger.info(f"Проверяю macOS {macos_name}...")
            result = scraper.scrape()

            if not result['success']:
                logger.error(f"Ошибка при проверке macOS {macos_name}: {result['error']}")
                errors.append(f"{macos_name}: {result['error']}")
                continue

            releases = result['releases']
            all_releases.extend(releases)

            # Проверяем каждый релиз
            for release in releases:
                added = self.db.add_release(
                    release['version'],
                    release['build'],
                    release['release_type'],
                    release['date_published'],
                    release['download_url'],
                    release.get('macos_version', macos_name)
                )

                if added:
                    all_new_releases.append(release)

        # Формируем статус проверки
        if errors:
            status = f"Частично: ошибки в {', '.join(errors)}"
        else:
            status = "Успешно"

        # Сохраняем историю проверки
        self.db.add_check_history(
            len(all_releases),
            len(all_new_releases),
            status
        )

        logger.info(f"Проверка завершена. Найдено релизов: {len(all_releases)}, новых: {len(all_new_releases)}")

        # Отправляем уведомления о новых релизах
        if all_new_releases:
            if is_first_run:
                # При первом запуске отправляем только сводку
                logger.info(f"Первый запуск: найдено {len(all_new_releases)} релизов, отправляю только сводку")
                await self.send_first_run_summary(all_new_releases)
            else:
                # При обычной работе отправляем уведомления о каждом новом релизе
                await self.send_notifications(all_new_releases)

    async def send_first_run_summary(self, releases: list):
        """Отправка сводки при первом запуске (вместо спама всеми релизами)"""
        public_releases = [r for r in releases if r['release_type'] == 'public']
        beta_releases = [r for r in releases if r['release_type'] == 'beta']

        # Группируем по версиям macOS
        releases_by_macos = {}
        for r in releases:
            macos_ver = r.get('macos_version', 'Sequoia')
            if macos_ver not in releases_by_macos:
                releases_by_macos[macos_ver] = {'public': 0, 'beta': 0}
            releases_by_macos[macos_ver][r['release_type']] += 1

        message = (
            "🎉 *Бот запущен!*\n\n"
            f"Добавлено в базу данных:\n"
            f"🟢 Public релизов: {len(public_releases)}\n"
            f"🟡 Beta релизов: {len(beta_releases)}\n\n"
        )

        # Показываем статистику по версиям macOS
        if len(releases_by_macos) > 1:
            message += "*По версиям macOS:*\n"
            for macos_ver in sorted(releases_by_macos.keys(), reverse=True):
                counts = releases_by_macos[macos_ver]
                message += f"  • {macos_ver}: {counts['public']} public, {counts['beta']} beta\n"
            message += "\n"

        message += "*Последние версии:*\n\n"

        # Получаем последние релизы для каждой версии macOS
        latest_public_by_macos = self.db.get_latest_releases_by_macos('public')
        latest_beta_by_macos = self.db.get_latest_releases_by_macos('beta')

        for macos_ver in sorted(set(latest_public_by_macos.keys()) | set(latest_beta_by_macos.keys()), reverse=True):
            message += f"🖥️ *macOS {macos_ver}:*\n"

            latest_public = latest_public_by_macos.get(macos_ver)
            latest_beta = latest_beta_by_macos.get(macos_ver)

            if latest_public:
                message += (
                    f"🟢 Public: {latest_public['version']} (Build {latest_public['build']})\n"
                )

            if latest_beta:
                message += (
                    f"🟡 Beta: {latest_beta['version']} (Build {latest_beta['build']})\n"
                )

            message += "\n"

        message += "Используйте /latest для просмотра подробной информации."

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
                        release['release_type'],
                        release.get('macos_version', 'Sequoia')
                    )
                except Exception as e:
                    logger.error(f"Ошибка при отправке в чат {chat_id}: {e}")

    def format_release_message(self, release: dict) -> str:
        """Форматирование сообщения о релизе"""
        emoji = "🟢" if release['release_type'] == 'public' else "🟡"
        type_name = "Public Release" if release['release_type'] == 'public' else "Beta Release"
        macos_version = release.get('macos_version', 'Sequoia')

        message = (
            f"{emoji} *Новый релиз macOS {macos_version}!*\n\n"
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
        logger.info(f"Отслеживаемые версии macOS: {list(self.macos_urls.keys())}")
        logger.info(f"Авторизованные пользователи: {config.ALLOWED_USER_IDS}")
        logger.info(f"Цели уведомлений: {config.NOTIFICATION_TARGETS}")

        # Запуск бота
        self.app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    bot = MacOSUpdateBot()
    bot.start()
