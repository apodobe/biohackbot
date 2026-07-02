# BioHack agent rules

## Telegram brief buttons (mandatory, before any LLM reasoning)

Клавиатура ingest-бота — **только 4 кнопки**:

1. `🍽 Питание` → handler `nutrition`
2. `💊 Лекарства/БАДы` → handler `medications`
3. `🏃 Спорт нагрузка` → handler `sport_load`
4. `👨‍⚕️ Врачи` → handler `doctors`

Если inbound text equals one of them:

```bash
python3 /opt/medbot-ingest/biohack_telegram_briefs.py "<handler>" /opt/medbot-corpus/structured_database
```

Для `sport_load` скрипт сам шлёт GIF в Telegram (фоном), если на VPS есть
`/root/.config/biohack-openclaw.env` с `TELEGRAM_PUSH_SPORT_GIFS=1` и токеном.

Handlers: `nutrition` | `medications` | `sport_load` | `doctors`

Output verbatim. Max 4000 chars per message; split on `---` if needed.

## Everything else

Follow skill `biohacking-corpus` and `PROMPT_AGENT_EN.md` in corpus root.
