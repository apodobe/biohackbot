# Руководство по парсерам

Как загрузить медицинские PDF и данные Apple Health в приватный инстанс.

**Корень инстанса** — `~/my-health/` (создаётся через `medbots init`). Пути ниже относительно него.

---

## Полный пайплайн

```
sources/*.pdf  ──scan──►  manifest.json
                ──extract-text──►  pdf_text/*.txt
                ──structure──►  doc_text/*.md + labs/*.jsonl
                ──pipeline──►  LABS_NORMALIZED.json, CORPUS_INDEX.json, …

export.zip  ──import-apple-health──►  fitness/*.json
```

Рекомендуемый порядок для PDF:

```bash
medbots scan --bot-root ~/my-health
medbots extract-text --bot-root ~/my-health
medbots structure --bot-root ~/my-health
medbots pipeline --bot-root ~/my-health
medbots validate --corpus ~/my-health/structured_database
```

Apple Health — **опционально**, отдельная команда (после `init`):

```bash
medbots import-apple-health --zip ~/Downloads/export.zip --bot-root ~/my-health --copy-zip
medbots validate-apple-health --corpus ~/my-health/structured_database
```

---

## Перед парсингом

1. **Создать инстанс:** `medbots init ~/my-health`
2. **Указать дату рождения** в `structured_database/PATIENT_PROFILE.json` — нужна для референсов и проверки Apple Health:

   ```json
   {"dob": "1985-06-15", "full_name_ru": "John Smith", "country": "USA"}
   ```

3. **Положить файлы** в нужную папку `sources/` (см. разделы по вендорам).
4. **`manifest.json` не редактировать вручную** — используйте `medbots scan`.

---

## 1. Scan — регистрация PDF

**Команда:** `medbots scan --bot-root ~/my-health`

**Действие:** Обходит `sources/emias/`, `sources/medsi/`, `sources/gemotest/`, считает SHA-256, добавляет новые записи в `manifest.json`. Дубликаты (путь или хеш) пропускает.

**Опции:**

| Флаг | Описание |
|------|----------|
| `--source emias` | Только один вендор (можно повторять) |
| `--corpus PATH` | Другой путь к `structured_database/` |

**Примеры:**

```bash
medbots scan --bot-root ~/my-health
medbots scan --bot-root ~/my-health --source gemotest
```

**Результат:** обновлённый `structured_database/manifest.json`.

---

## 2. Extract text — PDF → текст

**Команда:** `medbots extract-text --bot-root ~/my-health`

**Действие:** Для каждого PDF из manifest извлекает **текстовый слой** (PyMuPDF) в `structured_database/pdf_text/*.txt`.

**Важно:**

- PDF должен лежать по пути `{bot-root}/{source_pdf}` из manifest.
- Скан без текстового слоя → в файле будет `[NO_TEXT_LAYER: scanned PDF — OCR not included in this tool]`. Такие PDF **не распарсятся** на шаге `structure` — нужен OCR снаружи или PDF с текстом от лаборатории.

**Повторный запуск:** безопасен, перезаписывает `pdf_text/`.

---

## 3. Structure — парсеры PDF по вендорам

**Команда:** `medbots structure --bot-root ~/my-health`

**Действие:** Читает `pdf_text/`, выбирает парсер по `source_system` и `doc_type`, пишет:

- `structured_database/doc_text/YYYY-MM-DD_<type>.md` — документ с YAML frontmatter
- строки анализов в `structured_database/labs/` (JSONL)
- в manifest: `structured_locally_at`, `doc_text`, `grok_title`

**Опции:**

| Флаг | Описание |
|------|----------|
| `--force` | Перепарсить уже обработанные записи |
| `--dry-run` | Только разбор, без записи |
| `--source emias` | Ограничить вендором |

**Примеры:**

```bash
medbots structure --bot-root ~/my-health
medbots structure --bot-root ~/my-health --source medsi --force
medbots structure --bot-root ~/my-health --source gemotest --dry-run
```

### 3.1 ЕМИАС (`sources/emias/`)

**Структура:** плоская папка с PDF из портала ЕМИАС (Москва).

```bash
cp ~/Downloads/emias_*.pdf ~/my-health/sources/emias/
medbots scan --bot-root ~/my-health --source emias
medbots extract-text --bot-root ~/my-health
medbots structure --bot-root ~/my-health --source emias
```

**Типы документов:**

| Тип | Парсер | Результат |
|-----|--------|-----------|
| Анализы | `parse_emias_lab` | Таблица + `lab_rows` (COVID IgG/IgM, ПЦР, часть форматов Medsi внутри ЕМИАС) |
| Консультация | `parse_emias_consult_or_imaging` | Диагноз, заключение, рекомендации |
| УЗИ, функциональная диагностика | `parse_emias_consult_or_imaging` | Описание и заключение |

После `structure` обязательно: `medbots pipeline` → `LABS_NORMALIZED.json`.

### 3.2 Медси (`sources/medsi/`)

**Структура:** вложенные папки разрешены.

```bash
cp -r ~/Downloads/medsi/*.pdf ~/my-health/sources/medsi/2024/
medbots scan --bot-root ~/my-health --source medsi
medbots extract-text --bot-root ~/my-health
medbots structure --bot-root ~/my-health --source medsi
```

**Маршрутизация:**

| Содержимое | Парсер |
|------------|--------|
| Анализы крови/биохимия | `parse_medsi_lab` (блоки `Исследование - (L…)`) |
| ЭКГ, ЭхоКГ | consult/imaging (functional) |
| УЗИ, дуплекс | consult/imaging (imaging) |
| Прочие приёмы | consultation |

### 3.3 Гемотест (`sources/gemotest/`)

**Структура:** плоская или вложенная папка PDF из лаборатории Гемотест.

```bash
cp ~/Downloads/gemotest_*.pdf ~/my-health/sources/gemotest/
medbots scan --bot-root ~/my-health --source gemotest
medbots extract-text --bot-root ~/my-health
medbots structure --bot-root ~/my-health --source gemotest
```

**Поддерживаемые форматы бланков** (выбор автоматический):

| Формат | Когда |
|--------|-------|
| Числовые блоки | Стандарт: результат + референс построчно |
| Четырёхколоночная таблица | «Показатель / Результат / Ед. / Референсные значения» |
| Копrogram | Анализ кала |
| Качественная таблица | Положительно/отрицательно без чисел |

---

## 4. Apple Health

**Команда:**

```bash
medbots import-apple-health \
  --zip ~/Downloads/export.zip \
  --bot-root ~/my-health \
  --copy-zip
```

**Экспорт с iPhone:**

1. **Здоровье** → фото профиля → **Экспортировать все данные о здоровье**
2. Сохранить `export.zip` на Mac
3. Запустить команду выше

**Действие:**

- Потоковое чтение `export.xml` **внутри zip** — полный XML **не сохраняется** в корпус
- Агрегирует метрики, тренировки, ECG
- При повторном импорте **заменяет** только записи `source: apple_health`, ручные данные не трогает

**Файлы** (`structured_database/fitness/`):

| Файл | Содержимое |
|------|------------|
| `BODY_METRICS.json` | Шаги, сон, вес, % жира, пульс покоя, HRV, VO2max |
| `WORKOUTS.json` | Тренировки |
| `ECG_RECORDS.json` | ECG с Apple Watch |
| `APPLE_HEALTH_META.json` | Статистика импорта, quality |
| `APPLE_HEALTH_SUMMARY.md` | Краткая сводка |

**Опции:**

| Флаг | Описание |
|------|----------|
| `--copy-zip` | Копия архива в `sources/apple_health/` |
| `--corpus PATH` | Другой путь к structured_database |

**Проверка:**

```bash
medbots validate-apple-health --corpus ~/my-health/structured_database
```

**Не входит в pipeline** — только ручной CLI (`apple_health: false` в `bot_config.json`).

---

## 5. Pipeline — после парсинга PDF

**Команда:** `medbots pipeline --bot-root ~/my-health`

Обязателен после `structure`:

| Шаг | Назначение |
|-----|------------|
| `merge_labs_corpus` | Сборка `LABS_NORMALIZED.json` |
| `apply_loinc_map` | LOINC по `labs/LOINC_MAP.tsv` |
| `dedup_labs` | Дедупликация анализов |
| `extract_goals_from_doc_text` | Цели из консультаций (если включено) |
| `write_corpus_index` | `CORPUS_INDEX.json` |

Флаги в `bot_config.json` → `features`.

---

## Troubleshooting

| Симптом | Причина | Решение |
|---------|---------|---------|
| `missing PDF` | Файл не в `sources/` | Скопировать PDF, `scan` |
| `[NO_TEXT_LAYER` | Скан без текста | OCR или PDF с текстовым слоем |
| `empty text` | Пустой extract | Проверить PDF, повторить extract |
| `missing pdf_text` | Не запускали extract | `medbots extract-text` |
| Запись пропущена | Уже `structured_locally_at` | `--force` |
| Нет строк в LABS_NORMALIZED | Не запускали pipeline | `medbots pipeline` |
| Apple Health `quality=fail` | Битый/пустой zip | Переэкспорт с iPhone |

**Полная проверка корпуса:**

```bash
medbots validate --corpus ~/my-health/structured_database
```

---

## Краткая таблица CLI

| Команда | Вход | Выход |
|---------|------|-------|
| `medbots scan` | PDF в `sources/` | `manifest.json` |
| `medbots extract-text` | PDF из manifest | `pdf_text/*.txt` |
| `medbots structure` | `pdf_text/` | `doc_text/`, labs |
| `medbots import-apple-health` | `export.zip` | `fitness/` |
| `medbots validate-apple-health` | `fitness/` | OK / ошибки |
| `medbots pipeline` | корпус | `LABS_NORMALIZED.json` |
| `medbots validate` | корпус | отчёт |

См. также: [Схема файлов корпуса](CORPUS.md) · [LLM — уровни моделей](LLM_GUIDE.ru.md)
