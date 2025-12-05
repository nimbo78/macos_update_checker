import sqlite3
import logging
from datetime import datetime
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)


class Database:
    def __init__(self, db_path: str = None):
        # Используем /app/data/ в Docker контейнере или текущую директорию локально
        if db_path is None:
            import os
            db_path = os.path.join("/app/data" if os.path.exists("/app/data") else ".", "macos_releases.db")
        self.db_path = db_path
        self.init_database()

    def init_database(self):
        """Инициализация базы данных"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Таблица релизов
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS releases (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    version TEXT NOT NULL,
                    build TEXT,
                    release_type TEXT NOT NULL,
                    macos_version TEXT NOT NULL DEFAULT 'Sequoia',
                    date_published TEXT,
                    download_url TEXT,
                    date_discovered TEXT NOT NULL,
                    notified INTEGER DEFAULT 0,
                    UNIQUE(version, build, release_type, macos_version)
                )
            """)

            # Миграция: добавляем колонку macos_version если её нет
            cursor.execute("PRAGMA table_info(releases)")
            columns = [col[1] for col in cursor.fetchall()]
            if 'macos_version' not in columns:
                cursor.execute("ALTER TABLE releases ADD COLUMN macos_version TEXT NOT NULL DEFAULT 'Sequoia'")
                logger.info("Добавлена колонка macos_version в таблицу releases")
            
            # Таблица истории проверок
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS check_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    check_time TEXT NOT NULL,
                    releases_found INTEGER,
                    new_releases INTEGER,
                    status TEXT
                )
            """)
            
            conn.commit()
            logger.info("База данных инициализирована")

    def add_release(self, version: str, build: str, release_type: str,
                   date_published: str, download_url: str, macos_version: str = "Sequoia") -> bool:
        """Добавить новый релиз в базу данных"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO releases (version, build, release_type, macos_version,
                                        date_published, download_url, date_discovered, notified)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 0)
                """, (version, build, release_type, macos_version, date_published, download_url,
                      datetime.now().isoformat()))
                conn.commit()
                logger.info(f"Добавлен новый релиз: macOS {macos_version} {version} ({build}) - {release_type}")
                return True
        except sqlite3.IntegrityError:
            # Релиз уже существует
            return False
        except Exception as e:
            logger.error(f"Ошибка при добавлении релиза: {e}")
            return False

    def get_all_releases(self, macos_version: Optional[str] = None) -> List[Dict]:
        """Получить все релизы из базы данных"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            if macos_version:
                cursor.execute("""
                    SELECT version, build, release_type, macos_version,
                           date_published, download_url, date_discovered
                    FROM releases
                    WHERE macos_version = ?
                    ORDER BY id DESC
                """, (macos_version,))
            else:
                cursor.execute("""
                    SELECT version, build, release_type, macos_version,
                           date_published, download_url, date_discovered
                    FROM releases
                    ORDER BY id DESC
                """)

            releases = []
            for row in cursor.fetchall():
                releases.append({
                    'version': row[0],
                    'build': row[1],
                    'release_type': row[2],
                    'macos_version': row[3],
                    'date_published': row[4],
                    'download_url': row[5],
                    'date_discovered': row[6]
                })

            return releases

    def get_latest_release(self, release_type: Optional[str] = None,
                          macos_version: Optional[str] = None) -> Optional[Dict]:
        """Получить последний релиз (по версии, не по дате добавления)"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            # Строим запрос с учётом фильтров
            query = """
                SELECT version, build, release_type, macos_version,
                       date_published, download_url, date_discovered
                FROM releases
            """
            conditions = []
            params = []

            if release_type:
                conditions.append("release_type = ?")
                params.append(release_type)
            if macos_version:
                conditions.append("macos_version = ?")
                params.append(macos_version)

            if conditions:
                query += " WHERE " + " AND ".join(conditions)

            cursor.execute(query, params)

            rows = cursor.fetchall()
            if not rows:
                return None

            # Сортируем по версии (парсим как tuple чисел)
            def parse_version(version_str):
                try:
                    parts = version_str.split('.')
                    return tuple(int(p) for p in parts)
                except:
                    return (0, 0, 0)

            sorted_rows = sorted(rows, key=lambda r: parse_version(r[0]), reverse=True)
            row = sorted_rows[0]

            return {
                'version': row[0],
                'build': row[1],
                'release_type': row[2],
                'macos_version': row[3],
                'date_published': row[4],
                'download_url': row[5],
                'date_discovered': row[6]
            }

    def get_latest_releases_by_macos(self, release_type: Optional[str] = None) -> Dict[str, Optional[Dict]]:
        """Получить последние релизы для каждой версии macOS"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT DISTINCT macos_version FROM releases")
            macos_versions = [row[0] for row in cursor.fetchall()]

        result = {}
        for mv in macos_versions:
            result[mv] = self.get_latest_release(release_type=release_type, macos_version=mv)
        return result

    def mark_as_notified(self, version: str, build: str, release_type: str,
                        macos_version: str = "Sequoia"):
        """Отметить релиз как уведомленный"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE releases
                SET notified = 1
                WHERE version = ? AND build = ? AND release_type = ? AND macos_version = ?
            """, (version, build, release_type, macos_version))
            conn.commit()

    def add_check_history(self, releases_found: int, new_releases: int, status: str):
        """Добавить запись в историю проверок"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO check_history (check_time, releases_found, new_releases, status)
                VALUES (?, ?, ?, ?)
            """, (datetime.now().isoformat(), releases_found, new_releases, status))
            conn.commit()

    def get_last_check(self) -> Optional[Dict]:
        """Получить информацию о последней проверке"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT check_time, releases_found, new_releases, status
                FROM check_history
                ORDER BY id DESC
                LIMIT 1
            """)
            
            row = cursor.fetchone()
            if row:
                return {
                    'check_time': row[0],
                    'releases_found': row[1],
                    'new_releases': row[2],
                    'status': row[3]
                }
            return None

    def count_releases(self, macos_version: Optional[str] = None) -> int:
        """Подсчитать общее количество релизов в БД"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            if macos_version:
                cursor.execute("SELECT COUNT(*) FROM releases WHERE macos_version = ?", (macos_version,))
            else:
                cursor.execute("SELECT COUNT(*) FROM releases")
            return cursor.fetchone()[0]

    def count_releases_by_macos(self) -> Dict[str, int]:
        """Подсчитать количество релизов по версиям macOS"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT macos_version, COUNT(*) as count
                FROM releases
                GROUP BY macos_version
            """)
            return {row[0]: row[1] for row in cursor.fetchall()}
