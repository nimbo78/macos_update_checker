#!/bin/bash

# Скрипт для остановки бота

set -e

echo "⏹️  Остановка macOS Update Checker Bot..."

if ! command -v docker-compose &> /dev/null; then
    echo "❌ Docker Compose не установлен!"
    exit 1
fi

# Остановка контейнера
docker-compose down

echo "✅ Бот остановлен!"
