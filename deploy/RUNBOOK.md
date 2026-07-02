# BioHackBot — развёртывание на VPS (YOUR_VPS_HOST)

Отдельный корпус от idamedbot (мама): `/opt/medbot-corpus/structured_database`.

**Деплой только через rsync с Mac** (`02-rsync-corpus.sh`). GitHub Actions и auto-deploy из git не используются.

**PDF на VPS не попадают:** rsync синхронизирует только подготовленный `structured_database/` (текст, JSON). Исключены `*.pdf` и `telegram_ingest/`. Папка `sources/` на сервер не копируется.

## 0. Переменные

```bash
export VPS=root@YOUR_VPS_HOST
```

## 1. Корпус (с Mac)

```bash
cd /path/to/your/biohackbot-instance/openclaw-vps-deploy
./02-rsync-corpus.sh
```

## 2. OpenClaw skill

```bash
./03-install-skill-on-vps.sh
```

### Q&A бот @your_medbot

1. На VPS: `cp biohack-openclaw.env.example /root/.config/biohack-openclaw.env` и заполнить токен + user id.
2. С Mac:

```bash
./04-configure-biohack-telegram.sh
```

3. Доступ только для `TELEGRAM_BIOHACK_ALLOWED_USER_IDS` (allowlist в OpenClaw).

### Второй Telegram-бот (Q&A) — legacy note

```bash
ssh "$VPS" 'openclaw gateway restart'
```

## 3. Ingest-бот (PDF / фото / текст)

```bash
./09-install-biohack-ingest-bot.sh
```

На VPS:

```bash
cp /opt/medbot-ingest/biohack-ingest-bot.env.example /root/.config/biohacking-ingest-bot.env
# заполнить TELEGRAM_INGEST_BOT_TOKEN, TELEGRAM_INGEST_ALLOWED_CHAT_IDS, XAI_API_KEY
systemctl enable --now biohacking-ingest-bot
```

## 4. Напоминания (cron)

Редактировать `structured_database/GOALS_REMINDERS.json`, затем rsync.

```bash
cp biohack-reminder.env.example -> /root/.config/biohack-reminder.env  # на VPS
./07-install-reminder-cron.sh
```

## 5. Git

```bash
cd /path/to/your/biohackbot-instance
git add . && git commit -m "..." && git push origin main
```

Опционально `INGEST_GIT_PUSH=1` на VPS для push после ingest.

## Пути

| Компонент | Путь на VPS |
|-----------|-------------|
| Corpus | `/opt/medbot-corpus/structured_database` |
| Ingest | `/opt/medbot-ingest/` |
| Skill | `/root/.openclaw/workspace/skills/biohacking-corpus/` |
| Ingest env | `/root/.config/biohacking-ingest-bot.env` |
| Reminder env | `/root/.config/biohack-reminder.env` |
