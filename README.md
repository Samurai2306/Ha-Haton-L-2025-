UAV Analytics — Аналитика полётов БПЛА (ETL + API + Веб)

**Назначение**
- Преобразовать разрозненные сообщения SHR/DEP/ARR в нормальные таблицы.
- Считать ключевые метрики по регионам/датам, строить прогноз на 14 дней.
- Предоставить REST‑API и веб‑интерфейс для просмотра, фильтрации и экспорта отчётов.

**Компоненты**
- `app.py` — чтение `2024.xlsx`, `2025.xlsx`, парсинг и нормализация в `flights_normalized.csv`, `daily_aggregates.csv`, `forecast_14d.csv`.
- `etl_from_csv.py` — QC/обогащение уже существующих CSV, пересчёт агрегатов, запись `qa_issues.csv`.
- `api/main.py` — FastAPI: `/metrics/*`, `/forecast`, `/flights`, `/export.*`, `/health`.
- `web/` — Next.js (страницы `/overview`, `/map`, `/trends`, `/about`), тёмная тема (неоморфизм).
- `uav_analytics/*` — модули QC/прогноза/гео.
- Docker: `Dockerfile.api`, `docker-compose.yml`.
- Скрипты: `scripts/setup_venv.sh`, `scripts/run_etl.sh`, `scripts/run_api.sh`, `scripts/run_all.sh`.

**Требования**
- Python 3.11+, pip, Node.js 18+/20+, npm, Docker (по желанию).

**Данные**
- Excel вход: `2024.xlsx`, `2025.xlsx` (лист 0).
- CSV выходы:
  - `flights_normalized.csv` — нормализованные и обогащённые полёты: `date`, `region`, `reg_num`, `dep_time_utc`, `arr_time_utc`, `duration_min`, `zone`, `zone_clean`, `altitude_raw`, `altitude_category`, `dep_point`, `arr_point`, `dep_lat/dep_lon`, `arr_lat/arr_lon`, `*_raw`.
  - `daily_aggregates.csv` — суточные метрики: `region`, `date`, `flights_cnt`, `avg/p50/p90_duration_min`.
  - `forecast_14d.csv` — прогноз: `region`, `date`, `yhat`, `method`.
  - `qa_issues.csv` — QC‑журнал: `issue_type`, `row_index`, `description`.

**QC/Обогащение (обязательно перед аналитикой)**
- Исключение из агрегирования строк без `date`/`region` (лог в `qa_issues.csv`).
- `duration_min` < 0 или > 1440 → `NaN` + лог.
- Дубликаты по `(date, region, reg_num, dep_time_utc, arr_time_utc)` → оставляем запись с бОльшим числом непустых полей.
- Категоризация высоты по `altitude_raw` (берётся максимум `MNNNN`):
  - `LOW` ≤ M0100, `MID` ≤ M0300, `HIGH` > M0300.
- Очистка зон: `zone_clean` (UPPERCASE, один пробел).
- Гео: компактные координаты (`5957N02905E`) → `dep_lat/dep_lon`, `arr_lat/arr_lon`.

**Прогноз**
- Если установлен `statsmodels` и достаточно истории: Holt‑Winters (сезонность 7). Иначе — скользящая средняя по 7 последним дням.
- В API прогноз формируется на лету; отдельный файл можно пересоздать по желанию.

**Быстрый старт (локально)**
- Установка Python‑зависимостей: `pip install -r requirements.txt`
- Сформировать CSV из Excel: `python3 app.py`
- Пост‑ETL из CSV (QC/обогащение/агрегаты): `python3 etl_from_csv.py`
- Запустить API: `uvicorn api.main:app --host :: --port 8000`
- Проверить API: `curl http://127.0.0.1:8000/health`
- Запустить веб:
  - `cd web`
  - `export NEXT_PUBLIC_API_BASE=http://127.0.0.1:8000`
  - `npm ci` (первый раз)
  - `npm run dev` → http://localhost:3000 (или 3001)

**Скрипты (удобно)**
- `bash scripts/setup_venv.sh` — создать `.venv` и поставить deps.
- `bash scripts/run_etl.sh` — пост‑ETL из CSV (использует `FILE_FLIGHTS`, если задан).
- `bash scripts/run_api.sh` — API с IPv6/IPv4.
- `bash scripts/run_all.sh` — venv → (ETL при наличии CSV) → API → web.

**Работа только с CSV (без Excel)**
- Укажите свой файл: `export FILE_FLIGHTS=/полный/путь/к/вашему.csv`
- Выполните: `python3 etl_from_csv.py`
- Запустите API и веб, как выше.

**API (FastAPI)**
- Запуск: `uvicorn api.main:app --host :: --port 8000`
- Авторизация (опц.): `export API_TOKEN=секрет` и отправляйте `Authorization: Bearer секрет`.
- CORS: `export CORS_ORIGINS="*"` или список доменов.
- Эндпоинты:
  - `GET /health` → `{status, version}`
  - `GET /metrics/daily` — `date_from`, `date_to`, `region`, `zone` → [{date, region, flights_cnt, avg/p50/p90_duration_min}]
  - `GET /metrics/summary` — сводка: `{flights_total, regions_count, top_regions[], top_zones[]}`
  - `GET /flights` — `date_from`, `date_to`, `region`, `limit`, `offset` → `{total, items:[...]}`
  - `GET /forecast` — `region` (обяз.), `horizon` (по умолчанию 14) → `{region, items:[{date, yhat, method}]}`
  - `GET /export.csv`, `GET /export.pdf` — экспорт
- Примеры:
  - `curl "http://127.0.0.1:8000/metrics/daily?date_from=2025-01-01&date_to=2025-01-31"`
  - `curl "http://127.0.0.1:8000/flights?date_from=2025-01-01&date_to=2025-01-05&limit=5"`
  - `curl "http://127.0.0.1:8000/forecast?region=Екатеринбургский"`

**Веб‑клиент (Next.js)**
- Переменные окружения:
  - `NEXT_PUBLIC_API_BASE=http://127.0.0.1:8000`
  - `NEXT_PUBLIC_API_TOKEN=секрет` (если в API включён токен)
- Страницы:
  - `/overview` — KPI и таблицы
  - `/map` — таблица координат (если есть) и сводка по регионам
  - `/trends` — факт (60 дн.) + прогноз (14 дн.)
  - `/about` — проверка соединения, кликабельные ссылки на API
- Тема: тёмная (неоморфизм). Правки — `web/src/app/globals.css`.

**Docker**
- Только API: `docker compose up -d api`
- Переменные: `API_PORT`, `API_TOKEN`, `CORS_ORIGINS`, пути к CSV через переменные `FILE_*` (см. compose).
- CSV монтируются как тома в `/data/*.csv` внутри контейнера API.

**Обновление данных**
- Полный цикл: `python3 app.py && python3 etl_from_csv.py`
- Только CSV → ETL: `export FILE_FLIGHTS=/путь/к/вашему.csv && python3 etl_from_csv.py`

**Типичные проблемы**
- `ECONNREFUSED ::1:8000` в вебе → используйте IPv4 URL `http://127.0.0.1:8000` или запускайте API с `--host ::`.
- Порт 3000 занят → Next запустит 3001; открывайте порт из лога.
- `requirements.txt` «No such file» → вы в `web/`. Перейдите в корень и повторите.
- Пустая карта → нет координат в исходных данных; это нормально.

**Производительность**
- Сейчас: pandas + CSV в памяти.
- Для 1–5 млн записей: Parquet + DuckDB/Polars или колонночная БД, кэширование агрегатов.

**Доработки по запросу**
- Полноценная карта (Leaflet/кластеризация),
- Графики (Chart.js/Recharts),
- JWT вместо статического токена,
- CI (линтер/тесты/сборка образов).

