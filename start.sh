#!/bin/bash

# Скрипт для быстрого запуска бота

set -e

echo "🚀 Запуск macOS Update Checker Bot..."

# Проверка наличия config.py
if [ ! -f "config.py" ]; then
    echo "❌ Файл config.py не найден!"
    echo "📝 Создайте config.py на основе config.py.example"
    echo "   cp config.py.example config.py"
    exit 1
fi

# Проверка наличия Docker
if ! command -v docker &> /dev/null; then
    echo "❌ Docker не установлен!"
    echo "📥 Установите Docker: https://docs.docker.com/get-docker/"
    exit 1
fi

# Проверка наличия Docker Compose
if ! command -v docker-compose &> /dev/null; then
    echo "❌ Docker Compose не установлен!"
    echo "📥 Установите Docker Compose: https://docs.docker.com/compose/install/"
    exit 1
fi

# Создание директории для данных
mkdir -p data

# Запуск контейнера
echo "🐳 Запуск Docker контейнера..."
docker-compose up -d

# Ожидание запуска
sleep 2

# Проверка статуса
if docker-compose ps | grep -q "Up"; then
    echo "✅ Бот успешно запущен!"
    echo ""
    echo "📊 Статус: docker-compose ps"
    echo "📋 Логи:   docker-compose logs -f"
    echo "⏹️  Остановка: docker-compose down"
else
    echo "❌ Ошибка при запуске бота"
    echo "📋 Проверьте логи: docker-compose logs"
    exit 1
fi
