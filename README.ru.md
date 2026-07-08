# biohackbot

Pipeline для персонального медицинского корпуса: **установка → добавление PDF → парсинг → обогащение**.

[English](README.md) · [Русский](README.ru.md) · [中文](README.zh-CN.md)

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)

> **Не медицинская консультация.** Инструмент организует ваши документы локально. Не ставит диагнозы и не назначает лечение.

## Область применения и ограничения

- **Пакет:** `medbots-core` из этого репо; CLI — `medbots`.
- **Парсеры PDF:** рассчитаны на **российские бланки** — ЕМИАС, Медси, Гемотест. Другие вендоры — новый парсер ([docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)).
- **Без OCR:** сканы без текстового слоя не парсятся (нужен внешний OCR или приватный LLM-ingest).
- **OpenClaw / Telegram:** опциональный деплой на VPS ([deploy/RUNBOOK.md](deploy/RUNBOOK.md)); для локального корпуса не обязателен.
- **Демо без своих PDF:** [examples/demo-instance](examples/demo-instance).

---

## 1. Установка

```bash
git clone https://github.com/apodobe/biohackbot.git
cd biohackbot
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
medbots --help
```

## 2. Настройка (первый запуск)

Создайте **приватную** папку для данных (не внутри этого public-репо):

```bash
medbots init ~/my-health
```

Структура:

```
~/my-health/
├── bot_config.json
├── sources/emias/      ← сюда PDF
├── sources/medsi/
├── sources/gemotest/
└── structured_database/
    ├── manifest.json
    ├── PATIENT_PROFILE.json   ← укажите дату рождения
    ├── pdf_text/
    └── doc_text/
```

Отредактируйте `PATIENT_PROFILE.json`:

```json
{"dob": "1985-06-15", "full_name_ru": "John Smith", "country": "USA"}
```

## 3. Добавление документов

Скопируйте PDF анализов из ЕМИАС, Медси или Гемотест в соответствующую папку `sources/`.

Зарегистрируйте файлы в манифесте:

```bash
medbots scan --bot-root ~/my-health
# только один источник: --source emias
```

## 4. Парсинг PDF

Два шага: извлечь текст, затем разобрать в `doc_text/` и строки анализов.

```bash
medbots extract-text --bot-root ~/my-health
medbots structure --bot-root ~/my-health
# перепарсить всё: --force
# один вендор: --source gemotest
```

Поддерживаются: **ЕМИАС**, **Медси**, **Гемотест**.

### Apple Health (опционально)

На iPhone: Здоровье → профиль → Экспортировать все данные о здоровье → `export.zip`

```bash
medbots import-apple-health --zip ~/Downloads/export.zip --bot-root ~/my-health --copy-zip
medbots validate-apple-health --corpus ~/my-health/structured_database
```

Создаёт `fitness/BODY_METRICS.json`, `WORKOUTS.json`, `APPLE_HEALTH_SUMMARY.md`. Сырой `export.xml` **не сохраняется** — только агрегированный JSON.

## 5. Обогащение корпуса

Нормализация анализов, LOINC, дедупликация, индексы:

```bash
medbots pipeline --bot-root ~/my-health
medbots validate --corpus ~/my-health/structured_database
```

Результат: `LABS_NORMALIZED.json`, `DISCREPANCIES.json`, `CORPUS_INDEX.json` и markdown-сводки.

## 6. Опционально: VPS (только текст)

Синхронизация **JSON + текста** на сервер для приватного Q&A-бота (без PDF):

```bash
export VPS=root@YOUR_HOST
export CORPUS=~/my-health/structured_database
cd deploy && ./02-rsync-corpus.sh
```

Подробнее: [deploy/RUNBOOK.md](deploy/RUNBOOK.md)

---

## Команды CLI

| Команда | Назначение |
|---------|------------|
| `medbots init PATH` | Создать структуру instance |
| `medbots scan --bot-root PATH` | Добавить PDF из `sources/` в manifest |
| `medbots extract-text --bot-root PATH` | PDF → `pdf_text/*.txt` |
| `medbots import-apple-health --zip FILE --bot-root PATH` | Apple Health → `fitness/` |
| `medbots structure --bot-root PATH` | Текст → `doc_text/`, строки анализов |
| `medbots pipeline --bot-root PATH` | Merge labs, LOINC, dedup, индекс |
| `medbots validate --corpus PATH` | Проверка целостности |
| `medbots validate-apple-health --corpus PATH` | Проверка Apple Health |

## Демо без PDF

```bash
medbots structure --bot-root examples/demo-instance
medbots pipeline --bot-root examples/demo-instance
```

См. [examples/README.md](examples/README.md).

## Конфиденциальность

- Держите `~/my-health/` **локально** или в **private** git-репозитории.
- Не коммитьте данные пациента в этот public-репозиторий.
- См. [SECURITY.md](SECURITY.md).

## Документация

- [Архитектура](docs/ARCHITECTURE.md)
- [Руководство по парсерам](docs/PARSERS.ru.md) · [EN](docs/PARSERS.md)
- [LLM — когда нужны модели](docs/LLM_GUIDE.ru.md) · [EN](docs/LLM_GUIDE.md)
- [Схема файлов корпуса](docs/CORPUS.md)
- [License](LICENSE) — MIT, Copyright (c) 2026 Alexey Podobedov

**Автор:** [Alexey Podobedov](https://github.com/apodobe)
