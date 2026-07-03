# hypothesis-gen-mvp

MVP системы генерации научно-технических гипотез для НИИ.  
Пайплайн: **проблема + ограничения → векторный поиск по локальным документам → LLM → ранжирование → отчёт**.

## Быстрый старт

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env        # заполните ключи
python -m app.ingest
python -m app.main --problem "Стабилизация границы Li/твердотельный электролит" \
                   --constraints "TRL 3-4, бюджет до 5 млн руб, без кобальта"
```

Результат — в папке `output/` (JSON + Markdown) и в stdout.

## Получение API-ключа Yandex AI Studio

1. Войдите в [консоль Yandex Cloud](https://console.cloud.yandex.ru/).
2. Создайте или выберите **каталог** — его ID (`b1g...`) нужен как `YANDEX_FOLDER_ID`.
3. В разделе **AI Studio** / **Foundation Models** включите доступ к моделям.
4. Создайте **API-ключ сервисного аккаунта** с ролями `ai.languageModels.user` (или `ai.editor`).
5. Скопируйте ключ в `.env`:

```env
YANDEX_API_KEY=AQVN...
YANDEX_FOLDER_ID=b1g...
```

Документация: [Yandex AI Studio — OpenAI-compatible API](https://yandex.cloud/ru/docs/ai-studio/concepts/openai-compatibility).

Используемые модели по умолчанию:
- Chat: `gpt://{folder_id}/yandexgpt/latest`
- Embeddings (документы): `emb://{folder_id}/text-search-doc/latest`
- Embeddings (запрос): `emb://{folder_id}/text-search-query/latest`

Endpoint: `https://llm.api.cloud.yandex.net/v1`

## Демо-данные

В `data/raw/` уже лежат два файла про твердотельные батареи:
- `solid_state_batteries_review.md` — обзор материалов SSE
- `nanocoatings_patent_landscape.txt` — патентный ландшафт нанопокрытий

Добавьте свои `.txt`, `.md` или `.pdf` в ту же папку и переиндексируйте.

## Команды

| Команда | Описание |
|---|---|
| `python -m app.ingest` | Загрузка файлов из `data/raw/`, чанкинг, эмбеддинги, запись в ChromaDB |
| `python -m app.main --problem "..." [--constraints "..."]` | Полный пайплайн генерации гипотез |
| `python -m app.main ... --json` | Дополнительно вывести гипотезы в stdout как JSON |
| `pytest` | Smoke-тесты (без реальных вызовов API) |

## Структура

```
app/
├── main.py          # CLI, оркестрация пайплайна
├── config.py        # .env, пути, веса ранжирования
├── ingest.py        # загрузка → чанкинг → ChromaDB
├── retrieval.py     # векторный поиск
├── llm_client.py    # Yandex AI Studio (chat + embeddings)
├── generate.py      # промпт + парсинг гипотез
├── ranking.py       # composite score по фиксированным весам
└── report.py        # JSON + Markdown отчёт
data/raw/             # исходные документы
data/chroma/          # persistent ChromaDB (генерируется)
output/               # сгенерированные отчёты
```

## Формат гипотезы

```json
{
  "hypothesis": "формулировка",
  "mechanism": "предполагаемый механизм",
  "sources": ["имя_файла.md"],
  "novelty_score": 7,
  "risk_score": 4,
  "expected_value_score": 8,
  "reasoning": "обоснование",
  "composite_score": 0.742
}
```

## Что сознательно не входит в MVP

- Граф знаний / Neo4j
- Веб-UI / Streamlit
- Экспорт в Jira/YouTrack
- LangGraph и прочая оркестрация
- Мульти-провайдерная абстракция LLM

## Тесты

```bash
pytest -v
```

Тесты проверяют чанкинг, парсинг JSON, ранжирование и smoke-тест пайплайна с моками — без расхода API-квоты.
