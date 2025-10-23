import requests
from bs4 import BeautifulSoup
import logging
import re
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)


class MacOSScraper:
    def __init__(self, url: str):
        self.url = url
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }

    def fetch_page(self) -> Optional[str]:
        """Получить HTML страницы"""
        try:
            response = requests.get(self.url, headers=self.headers, timeout=30)
            response.raise_for_status()
            logger.info("Страница успешно загружена")
            return response.text
        except Exception as e:
            logger.error(f"Ошибка при загрузке страницы: {e}")
            return None

    def parse_releases(self, html: str) -> List[Dict]:
        """Парсинг релизов со страницы"""
        soup = BeautifulSoup(html, 'lxml')
        releases = []

        # Ищем все ссылки на InstallAssistant.pkg
        links = soup.find_all('a', href=re.compile(r'InstallAssistant\.pkg'))
        
        for link in links:
            download_url = link.get('href')
            if not download_url:
                continue
            
            # Определяем тип релиза по контексту
            release_type = 'public'
            context_text = link.find_previous(['h2', 'h3', 'h4', 'p', 'strong'])
            if context_text:
                context = context_text.get_text().upper()
                if 'BETA' in context:
                    release_type = 'beta'
            
            # Находим родительскую строку таблицы
            row = link.find_parent('tr')
            if not row:
                logger.debug("Ссылка не в таблице, пропускаем")
                continue
            
            cells = row.find_all('td')
            if len(cells) < 2:
                logger.debug("Недостаточно ячеек в строке")
                continue
            
            # Извлекаем версию и build из текста строки
            row_text = row.get_text()
            
            # Парсим версию (15.1, 15.2.1 и т.д.)
            version_match = re.search(r'(\d+\.\d+(?:\.\d+)?)', row_text)
            if not version_match:
                logger.debug(f"Не найдена версия в строке: {row_text[:50]}")
                continue
            version = version_match.group(1)
            
            # Парсим build (24B83, 24C5057p и т.д.)
            build_match = re.search(r'\b([0-9]{2}[A-Z][0-9]{2,}[a-z]?)\b', row_text)
            if not build_match:
                logger.debug(f"Не найден build в строке: {row_text[:50]}")
                continue
            build = build_match.group(1)
            
            # Создаем запись о релизе
            release = {
                'version': version,
                'build': build,
                'release_type': release_type,
                'date_published': '',
                'download_url': download_url
            }
            
            # Проверяем на дубликаты
            if not any(r['version'] == version and r['build'] == build 
                     and r['release_type'] == release_type for r in releases):
                releases.append(release)
                logger.debug(f"Найден релиз: {version} ({build}) - {release_type}")

        logger.info(f"Всего найдено релизов: {len(releases)}")
        return releases

    def get_page_update_date(self, html: str) -> Optional[str]:
        """Извлечь дату обновления страницы"""
        soup = BeautifulSoup(html, 'lxml')
        
        # Ищем текст "UPDATED: ..."
        text = soup.get_text()
        match = re.search(r'UPDATED:\s*(\d{1,2}/\d{1,2}/\d{2,4})', text)
        if match:
            return match.group(1)
        
        return None

    def scrape(self) -> Dict:
        """Основной метод для парсинга страницы"""
        html = self.fetch_page()
        
        if not html:
            return {
                'success': False,
                'error': 'Не удалось загрузить страницу',
                'releases': [],
                'page_updated': None
            }

        releases = self.parse_releases(html)
        page_updated = self.get_page_update_date(html)

        return {
            'success': True,
            'error': None,
            'releases': releases,
            'page_updated': page_updated
        }
