# Когда нужны LLM: уровни моделей и правила

Где языковые модели **не нужны**, какой уровень брать для clawbot/OpenClaw, и какие файлы отдавать дорогим моделям в зависимости от размера корпуса.

**Главное:** цепочка `scan` → `extract-text` → `structure` → `pipeline` работает **без API LLM**. LLM — для **Q&A-бота**, **опционального ingest сканов** и **ревью/синтеза** уже структурированных файлов.

См. также: [Руководство по парсерам](PARSERS.ru.md)

---

## Быстрая таблица: шаг → LLM?

| Шаг | Команда / файл | LLM? | Уровень |
|-----|----------------|------|---------|
| Регистрация PDF | `medbots scan` | Нет | — |
| Текст из PDF | `medbots extract-text` | Нет | — |
| Парсеры вендоров | `medbots structure` | Нет | — |
| Apple Health | `medbots import-apple-health` | Нет | — |
| Сборка анализов | `medbots pipeline` | Нет | — |
| Черновики целей/БАДов/протоколов | pipeline (`extracted_by: composer`) | Нет* | — |
| Черновик расхождений | `DISCREPANCIES.json` | Нет* | — |
| LHM v1 | `LIVING_HEALTH_SUMMARY.md` | Нет | — |
| Навигация | `CORPUS_INDEX.json` | Нет | — |
| Кнопки Telegram (4 пресета) | shell-скрипты | Нет | — |
| Свободные вопросы OpenClaw | агент на VPS | **Да** | Средний |
| Скан/PDF без текста | Grok ingest (приватно) | **Да** | Быстрый |
| Ревью черновиков | ручная сессия в чате | **Да** | Лёгкий → тяжёлый |
| Полный аудит / LHM v2 | ручная сессия | **Да** | Тяжёлый |

\*Шаги с меткой `composer` — **локальный Python** (regex/правила), не вызов API. Перед клиническим использованием их нужно проверить человеком ± LLM.

---

## Уровни моделей

| Уровень | Примеры | Стоимость | Для чего |
|---------|---------|-----------|----------|
| **0 — Локально** | только medbots | Бесплатно | Весь ingest и нормализация |
| **1 — Быстрые** | Grok fast-reasoning, Gemini Flash, GPT-4o-mini | Низкая | JSON-чистка, дедуп, 1–3 скана |
| **2 — Средние** | Grok 4.x (OpenClaw по умолчанию), Gemini Pro, GPT-4o | Средняя | Ежедневный Q&A в Telegram, точечные вопросы |
| **3 — Тяжёлые** | Claude Opus, GPT-4.1, long-context Gemini | Высокая | Кросс-доменный синтез, генетика, narrative по DISCREPANCIES, LHM v2, квартальный аудит |

**Правило:** начинайте с минимального уровня; повышайте, если не хватает контекста из нескольких файлов или медицинской связности.

---

## OpenClaw / clawbot (Q&A на VPS)

Шаблон деплоя: [deploy/RUNBOOK.md](../deploy/RUNBOOK.md).

### Без LLM

- `rsync` корпуса (только текст + JSON)
- Скрипт обзора корпуса
- 4 кнопки brief (питание, лекарства, спорт, врачи) — **готовый текст из скрипта**
- `jq`, `rg`, `cat` в skill

### С LLM

- Свободные вопросы пользователя
- Сводка из нескольких файлов
- «Что изменилось за год», тренды, противоречия

### Модель для OpenClaw

В приватном деплое по умолчанию **`xai/grok-4.3`** для агента `biohacking` — нормальный баланс для русскоязычного Q&A с цитированием файлов.

| PDF в корпусе | Модель OpenClaw | Заметки |
|---------------|-----------------|---------|
| &lt; 20 | Grok 4.x / GPT-4o-mini | LHM + срез LABS обычно помещаются |
| 20–80 | Grok 4.x / GPT-4o | Сначала skill + `rg`, не весь JSON |
| 80+ | Средний tier + **жёсткий read order** | Не грузить весь `doc_text/` |
| + генетика | Средний для Q&A; **тяжёлый для интерпретации** | Отдельная сессия |

**Повышать до уровня 3**, если: таблицы трендов за много лет, сверка &gt;10 визитов, рекомендации из разрозненных консультаций.

**Понижать до уровня 1**, если: «какой гемоглобин 2024-03-01?» — один `jq`, модель только форматирует ответ.

### Обязательное поведение бота

1. Первая строка ответа — **какие файлы использованы**
2. Порядок чтения: `CORPUS_INDEX.json` → `DISCREPANCIES.json` → `LIVING_HEALTH_SUMMARY.md` → JSON по доменам → `doc_text/` по необходимости
3. Не врач — без новых назначений
4. Шаблон: [prompts/PROMPT_AGENT.template.md](prompts/PROMPT_AGENT.template.md)

---

## Файлы: кто создаёт vs кто должен ревьюить

### Локально (без LLM)

| Файл | Кто |
|------|-----|
| `manifest.json`, `pdf_text/`, `doc_text/` | scan + extract + structure |
| `LABS_NORMALIZED.json` | pipeline |
| `fitness/*` | Apple Health import |
| `CORPUS_INDEX.json` | pipeline |
| `DISCREPANCIES.json` (черновик) | pipeline |
| `GOALS_REMINDERS.json`, `SUPPLEMENTS.json`, `PROTOCOLS.json` (черновики) | pipeline |
| `LIVING_HEALTH_SUMMARY.md` (v1) | pipeline |

### Рекомендуемое LLM-ревью

| Файл | Уровень | Когда | Задача |
|------|---------|-------|--------|
| `GOALS_REMINDERS.json` | 1 | После новых консультаций | Дедуп, приоритеты, `inactive` для устаревшего |
| `supplements/SUPPLEMENTS.json` | 1 | После упоминаний БАДов в doc_text | Дозы, схемы, дедуп |
| `biohacking/PROTOCOLS.json` | 1 | После документов по образу жизни | Дедуп, расписания из source |
| `DISCREPANCIES.json` | 1, затем **3** | Перед доверием алертам | Убрать ложные; Opus — `narrative_ru` для high |
| `LIVING_HEALTH_SUMMARY.md` | **3** | Раз в 6–12 мес или &gt;15 новых PDF | LHM v2: тренды, цели; ≤400 строк; только корпус |
| `nutrition/NUTRITION.json` | **3** | Если есть консультации нутрициолога | `clinical_context_ru` к рецептам |
| `genomics/*` | **3** | Отдельная сессия | Не смешивать с общим Q&A |
| `recommendations/*.md` | **3** | Планы тренировок и т.п. | Человекочитаемый narrative |

**Минимум для сессии ревью:**

```
CORPUS_INDEX.json
DISCREPANCIES.json
<файл под ревью>
цитированные doc_text из meta
```

Шаблон тяжёлого аудита: [prompts/PROMPT_OPUS.template.md](prompts/PROMPT_OPUS.template.md)

---

## Масштаб по объёму корпуса

После pipeline: `jq '.totals' structured_database/CORPUS_INDEX.json`

### Малый (&lt; 15 PDF, &lt; 300 строк анализов)

- Часто хватает только локального pipeline
- OpenClaw уровень 2 + LHM
- LLM-ревью: опционально только GOALS

### Средний (15–60 PDF, 300–1500 строк)

- После каждой пачки PDF — ревью уровня 1 всех composer-черновиков
- В боте не вставлять весь `LABS_NORMALIZED.json`; срезы через `jq`
- LHM v2 на уровне 3 — раз в 6–12 месяцев

### Большой (60+ PDF, 1500+ строк, 5+ лет анализов)

- **Домены по отдельности:** анализы / визиты / БАДы / fitness
- OpenClaw: `rg` по `doc_text/` до массового чтения
- Уровень 3 обязателен для narrative по `DISCREPANCIES.json`
- Держите краткий `AI_SYSTEM_BRIEF.md` (1 страница) для экономии токенов

### Apple Health

- Бот читает `APPLE_HEALTH_SUMMARY.md` + срезы `BODY_METRICS.json`
- Тяжёлая модель — только для длинного анализа нагрузки за годы

---

## Опционально: LLM ingest сканов

**Не в публичном репо** — приватный Telegram ingest + Grok.

Только если в `pdf_text/` есть `[NO_TEXT_LAYER`.

| Вход | Модель | Переменные |
|------|--------|------------|
| Текстовый PDF (fallback) | `grok-4-1-fast-reasoning` | `INGEST_LLM_MODEL` |
| Скан / фото | та же + vision | `XAI_API_KEY` |

Лучше скачать PDF с текстовым слоем из кабинета лаборатории, чем OCR через LLM.

---

## Контроль стоимости

1. Сначала **полный локальный pipeline**
2. **Индекс и DISCREPANCIES** — до открытия `doc_text/`
3. **Срезы JSON** — последние N значений по `canonical_key`
4. **Один домен на тяжёлую сессию**
5. **Скриптовые briefs** для повторяющихся вопросов
6. **Повторный pipeline**, а не «распарсь PDF ещё раз в ChatGPT»

---

## Workflow после новых данных

```bash
# 1. Локально (бесплатно)
medbots scan && medbots extract-text && medbots structure && medbots pipeline && medbots validate

# 2. Лёгкое ревью (уровень 1) — GOALS, SUPPLEMENTS, PROTOCOLS

# 3. Smoke-test OpenClaw — один фактологический вопрос с строкой «Источники: …»

# 4. Тяжёлый проход (уровень 3) — при многих high в DISCREPANCIES или раз в квартал
```

---

## Шаблоны промптов

Скопируйте в приватный `structured_database/` и подставьте свои пути:

- [PROMPT_AGENT.template.md](prompts/PROMPT_AGENT.template.md) — OpenClaw / ежедневный Q&A
- [PROMPT_OPUS.template.md](prompts/PROMPT_OPUS.template.md) — аудит / LHM v2
