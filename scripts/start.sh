#!/usr/bin/env bash
# Быстрый запуск MVP (инфраструктура в Docker, API и UI локально)
set -euo pipefail
cd "$(dirname "$0")/.."

if [ ! -f .env ]; then
  echo "Создайте .env из .env.example и заполните YC_API_KEY / YC_FOLDER_ID"
  exit 1
fi

echo "==> Поднимаем Qdrant, Neo4j, MinIO..."
docker compose up -d qdrant neo4j minio

echo "==> Ждём готовности сервисов (15 сек)..."
sleep 15

echo "==> Backend..."
cd backend
if [ ! -d .venv ]; then
  python3 -m venv .venv
  .venv/bin/pip install -r requirements.txt -q
fi

echo ""
echo "Запустите в отдельных терминалах:"
echo "  1) API:      cd backend && .venv/bin/uvicorn app.main:app --reload --port 8000"
echo "  2) Frontend: cd frontend && npm install && npm run dev"
echo ""
echo "Откройте: http://localhost:5173"
echo "API docs: http://localhost:8000/docs"
