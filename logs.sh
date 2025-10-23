#!/bin/bash

# Скрипт для просмотра логов бота

echo "📋 Логи macOS Update Checker Bot"
echo "================================="
echo ""

if ! command -v docker-compose &> /dev/null; then
    echo "❌ Docker Compose не установлен!"
    exit 1
fi

# Показ логов
docker-compose logs -f --tail=100
