# kaizendo_bot

Telegram-бот для трекинга привычек одного пользователя через plain text.
Вдохновлён книгой «Атомные привычки» — маленькие ежедневные шаги складываются в результат.
Хранит историю как поток неизменяемых событий (event sourcing) в Firestore.

## Поток сообщений

```mermaid
sequenceDiagram
    participant U as User
    participant B as Bot
    participant L as LLM
    participant F as Firestore

    U->>B: "читал фромма 30 мин"
    B->>L: parse_habit(text)
    L-->>B: HabitData(habit_type, summary, details)
    alt новый тип привычки
        B->>U: "Новый тип: чтение. Сохранить? [Да][Нет]"
        U->>B: нажимает Да
        B->>F: add_known_type("чтение")
    end
    B->>U: ✓ Чтение — 30 мин — Фромм<br/>↩ ответь чтобы исправить
    B->>F: log_event(type="logged", bot_message_id=999)

    U->>B: reply: "нет, 45 мин"
    B->>F: find_habit_by_message_id(999)
    F-->>B: (habit_id, logged_doc)
    B->>L: correct_habit(original, correction, current)
    L-->>B: HabitData(summary="Чтение — 45 мин — Фромм")
    B->>U: edit_text("✓ Чтение — 45 мин — Фромм...")
    B->>F: log_event(type="corrected")

    U->>B: reply: "удали"
    B->>U: edit_text("🗑 Удалено [Чтение — 45 мин — Фромм]")
    B->>F: log_event(type="deleted")
```

## Жизненный цикл привычки

```mermaid
flowchart TD
    S(( )) -->|новый текст| parse[LLM parse]
    parse -->|известный тип| logged
    parse -->|новый тип| confirm{Подтвердить?}
    confirm -->|Да| logged
    confirm -->|Нет| E2(( ))
    logged -->|reply с правкой| corrected
    corrected -->|ещё одна правка| corrected
    logged -->|reply «удали»| deleted
    corrected -->|reply «удали»| deleted
    deleted --> E(( ))
```

## Ключевые файлы

```
src/bot/
├── main.py                  # точка входа, настройка webhook
├── models.py                # HabitData dataclass
├── handlers/
│   ├── basic.py             # /start, /ping, /today
│   └── habits.py            # обработка входящих сообщений и reply
└── services/
    ├── llm.py               # LLMService — парсинг и коррекция через OpenRouter
    └── storage.py           # StorageService — запись/чтение событий в Firestore
tests/
```
