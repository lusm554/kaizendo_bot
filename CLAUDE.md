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
- Firestore: база `(default)` создана в `us-central1`, коллекция `habits`

Создать Firestore базу (один раз, уже сделано):
```bash
gcloud firestore databases create --project=kaizendo-bot --location=us-central1
```

Пересборка и деплой из source:
```bash
BOT_TOKEN=$(grep BOT_TOKEN .env | cut -d= -f2)
WEBHOOK_SECRET=$(grep WEBHOOK_SECRET .env | cut -d= -f2)
OPENROUTER_API_KEY=$(grep OPENROUTER_API_KEY .env | cut -d= -f2)
gcloud run deploy kaizendo-bot \
  --source . \
  --region us-central1 \
  --project kaizendo-bot \
  --allow-unauthenticated \
  --max-instances 1 \
  --set-env-vars "BOT_TOKEN=${BOT_TOKEN},WEBHOOK_URL=https://kaizendo-bot-522564501368.us-central1.run.app,WEBHOOK_SECRET=${WEBHOOK_SECRET},OPENROUTER_API_KEY=${OPENROUTER_API_KEY}"
```

Только обновить одну env-переменную (без пересборки):
```bash
OPENROUTER_API_KEY=$(grep OPENROUTER_API_KEY .env | cut -d= -f2)
gcloud run services update kaizendo-bot \
  --region us-central1 \
  --project kaizendo-bot \
  --update-env-vars "OPENROUTER_API_KEY=${OPENROUTER_API_KEY}"
```

Логи:
```bash
gcloud run logs read --service kaizendo-bot --region us-central1 --project kaizendo-bot
```

Проверить webhook:
```bash
curl "https://api.telegram.org/bot${BOT_TOKEN}/getWebhookInfo"
```

# GitHub Actions (CI/CD)

> **Важно:** при любом изменении, которое затрагивает деплой (новые env-переменные,
> зависимости, команды запуска, порты), проверь нужно ли обновить `.github/workflows/ci-cd.yml`.

Воркфлоу: `.github/workflows/ci-cd.yml`
- `test` job: запускает `uv run pytest -v` на каждый push/PR
- `deploy` job: деплоит в Cloud Run только при push в master и после успешных тестов

Необходимые секреты в репозитории (Settings → Secrets → Actions):
- `GCP_SA_KEY` — JSON-ключ GCP Service Account
- `BOT_TOKEN` — токен бота
- `WEBHOOK_SECRET` — секрет вебхука
- `OPENROUTER_API_KEY` — ключ OpenRouter для LLM-парсинга

Просмотр запусков через `gh` CLI (авторизован как `lusm554`):
```bash
# Список последних запусков
gh run list --repo lusm554/kaizendo_bot

# Детали запуска
gh run view <run-id>

# Логи упавшего запуска
gh run view <run-id> --log-failed

# Смотреть в реальном времени
gh run watch <run-id>
```
