# Фабрика гипотез

Система генерации, проверки и приоритизации научно-исследовательских гипотез для НИИ и промышленных лабораторий (металлургия, обогащение руд, материаловедение).

**Стек:** FastAPI · YandexGPT · Qdrant (RAG) · Neo4j (граф) · Streamlit / React UI

## Что умеет

1. **Ingest** — парсинг PDF, DOCX, XLSX, изображений (OCR), индексация в Qdrant + Neo4j
2. **RAG** — гибридный поиск с приоритетом материалов предприятия (`Пример 1–4`)
3. **Генерация** — 3 гипотезы с цитатами, механизмом, roadmap и графом влияния
4. **Судья** — независимая валидация: чеклист ТЗ, overlap цитат, ограничения, LLM-оценки
5. **Прозрачность** — в UI видно **почему судья одобрил или отклонил** (`decision_rationale`)
6. **JQI** — целевая метрика качества прогона (цель ≥ 75)

## Архитектура

```
Документы (data/) → Ingest → Qdrant + Neo4j
                              ↓
Задача + ограничения → RAG retrieval → YandexGPT (генерация)
                              ↓
                    Судья + ранжирование → UI / экспорт PDF
```

## Быстрый старт

### 1. Окружение

```bash
cp .env.example .env
```

Заполните в `.env`:

| Переменная | Где взять |
|------------|-----------|
| `YC_API_KEY` | Yandex Cloud → сервисный аккаунт → API-ключ |
| `YC_FOLDER_ID` | ID каталога в [консоли Yandex Cloud](https://console.cloud.yandex.ru/) |

Роль сервисного аккаунта: `ai.languageModels.user`.

### 2. Docker (рекомендуется)

```bash
docker-compose up --build
```

| Сервис | URL |
|--------|-----|
| API | http://localhost:8000 |
| React UI | http://localhost:5173 |
| Streamlit | `./scripts/run_streamlit.sh` → http://localhost:18493 |
| Qdrant | http://localhost:6333 |
| Neo4j | http://localhost:7474 |
| MinIO | http://localhost:9001 |

### 3. Локально (без Docker для API)

```bash
docker-compose up qdrant neo4j minio -d

cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Streamlit:

```bash
./scripts/run_streamlit.sh
```

## Демо-сценарии (`data/`)

| ID | Папка | Задача |
|----|-------|--------|
| `kgmk` | `Пример 1/` | Хвосты КГМК, флотация |
| `nof` | `Пример 2/` | НОФ, вкраплённая медь |
| `textbook` | `Дополнительные материалы/` | Учебники по флотации |

В каждой папке «Пример N»: **docx** (гипотезы мозгового штурма) + **xlsx** (KPI хвостов).

### CLI

```bash
cd backend
python -m app.demo --scenario 2 --json   # КГМК
python -m app.demo --scenario 3          # НОФ
```

### API

```bash
curl -X POST "http://localhost:8000/ingest/batch?directory=Пример%201"
curl -X POST "http://localhost:8000/ingest/batch?directory=Дополнительные%20материалы"

curl -X POST http://localhost:8000/hypotheses/generate \
  -H "Content-Type: application/json" \
  -d '{
    "problem": "Повышение извлечения меди из хвостов КГМК при оптимизации флотации",
    "constraints": "pH 8-10, без капитальных вложений, TRL 4"
  }'
```

После изменения парсера переиндексируйте примеры (удалите JSON в `data/processed/` или ingest без `only_missing`).

## Почему судья принял решение

В ответе API у каждой гипотезы:

```json
{
  "judge_verdict": {
    "approved": true,
    "overall_score": 8.1,
    "decision_rationale": [
      "Цитата из источника подтверждена в RAG-контексте (пересечение ≥ 30%)",
      "✓ Ссылки на источники",
      "✓ Проверяемая формулировка (конкретная, с параметрами)",
      "Оценки судьи: проверяемость 8.0, доказательства 7.5, релевантность 8.0",
      "Опора на источник `geokniga-...`: «КМЦ 0,3—0,5 кг/т…»"
    ]
  },
  "reasoning": "… аргумент генератора при создании (не вердикт судьи)"
}
```

| Поле | Кто пишет | Смысл |
|------|-----------|--------|
| `reasoning` | Генератор | Почему модель **предложила** гипотезу |
| `decision_rationale` | Судья | Почему гипотеза **одобрена/отклонена** |

Отображается в Streamlit (вкладка «Результаты») и React UI (блок «Почему судья одобрил»).

## Метрика JQI

```
JQI = 100 × (0.50 × approval_rate + 0.35 × avg_score/10 + 0.15 × grounding_rate)
```

Цель: **≥ 75**. Настраивается в `.env` (`JUDGE_QUALITY_TARGET`).

## Замер точности

```bash
cd backend
python scripts/measure_accuracy.py
python scripts/analyze_accuracy.py
```

## API

| Метод | Путь | Описание |
|-------|------|----------|
| POST | `/ingest` | Загрузка файла |
| POST | `/ingest/batch?directory=…` | Индексация папки из `data/` |
| POST | `/hypotheses/generate` | Генерация + судья |
| GET | `/hypotheses/{id}` | Детали гипотезы |
| POST | `/hypotheses/{id}/feedback` | Фидбэк эксперта |
| GET | `/export/report` | PDF / DOCX |
| GET | `/export/tasks` | CSV / JSON для Jira |
| GET | `/demo/examples` | Демо-сценарии |
| GET | `/health` | Статус сервисов |

## Структура репозитория

```
backend/app/
  ingest/          # parser, tabular, docx_parse, pipeline
  rag/             # retrieval, example boost, text_overlap
  hypotheses/      # generator, prompts, sanitize
  judge/           # validator, checklist, rationale
  scoring/         # ranker
  api/             # FastAPI routers
streamlit/         # основной UI для демо
frontend/          # React UI
data/
  Пример 1–4/      # эталоны (docx + xlsx)
  processed/       # кэш ingest
  hypotheses/      # сохранённые прогоны
  batch_analysis/  # отчёты точности
```

## Форматы данных

| Формат | Парсинг |
|--------|---------|
| PDF | Текст + OCR (Tesseract) для сканов |
| DOCX | Абзацы, таблицы, нумерованные гипотезы |
| XLSX | Универсальные таблицы + KPI-сводка |
| PNG/JPG | OCR |
| TXT/MD | Да |

OCR (macOS): `brew install tesseract tesseract-lang poppler`

## Тесты

```bash
cd backend
pip install -r requirements.txt
pytest -v
```

## Переменные окружения

Полный список — в `.env.example`.
