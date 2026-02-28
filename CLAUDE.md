Бот Kaizen для трекинга привычек одного пользователя через plain text input с отображением инфографики в Telegram Mini Apps. Отсылка к книге "Атомные привычки".

# Стек
- Python 3.14, uv, aiogram

# Принципы
- Keep it simple
- TDD

# Бот
- Username: @kaizendo_bot
- Токен хранится в `.env` как `BOT_TOKEN`

# Тесты
```bash
uv run pytest -v
```

# Деплой (Cloud Run)
- GCP проект: `kaizendo-bot`
- Регион: `us-central1`
- URL: `https://kaizendo-bot-522564501368.us-central1.run.app`
- Webhook: `<URL>/webhook` (регистрируется автоматически при старте)

Пересборка и деплой из source:
```bash
BOT_TOKEN=$(grep BOT_TOKEN .env | cut -d= -f2)
gcloud run deploy kaizendo-bot \
  --source . \
  --region us-central1 \
  --project kaizendo-bot \
  --allow-unauthenticated \
  --set-env-vars "BOT_TOKEN=${BOT_TOKEN},WEBHOOK_URL=https://kaizendo-bot-522564501368.us-central1.run.app"
```

Только обновить env-переменные (без пересборки):
```bash
gcloud run services update kaizendo-bot \
  --region us-central1 \
  --project kaizendo-bot \
  --set-env-vars "BOT_TOKEN=...,WEBHOOK_URL=..."
```

Логи:
```bash
gcloud run logs read --service kaizendo-bot --region us-central1 --project kaizendo-bot
```

Проверить webhook:
```bash
curl "https://api.telegram.org/bot${BOT_TOKEN}/getWebhookInfo"
```
