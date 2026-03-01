import pytest
from unittest.mock import AsyncMock, MagicMock

from bot.models import HabitData
from bot.handlers.habits import habit_handler, correction_handler, today_handler


def _make_message(text: str, message_id: int = 100, user_id: int = 1) -> AsyncMock:
    message = AsyncMock()
    message.text = text
    message.message_id = message_id
    message.from_user = MagicMock()
    message.from_user.id = user_id
    message.reply_to_message = None
    # answer() returns a sent message with a message_id
    sent = AsyncMock()
    sent.message_id = 999
    message.answer = AsyncMock(return_value=sent)
    return message


def _make_reply_message(text: str, replied_id: int) -> AsyncMock:
    message = _make_message(text)
    replied = AsyncMock()
    replied.message_id = replied_id
    replied.from_user = MagicMock()
    replied.from_user.is_bot = True
    replied.edit_text = AsyncMock()
    message.reply_to_message = replied
    return message


@pytest.mark.asyncio
async def test_habit_handler_sends_confirmation():
    habit = HabitData("reading", "Эрих Фромм", "Искусство Любить", 30)

    llm = AsyncMock()
    llm.parse_habit = AsyncMock(return_value=habit)

    storage = AsyncMock()
    storage.log_event = AsyncMock(return_value="event123")

    message = _make_message("почитал 30 мин фромма")

    await habit_handler(message, llm=llm, storage=storage)

    message.answer.assert_called_once_with(
        "✓ Чтение — 30 мин — Эрих Фромм «Искусство Любить»\n"
        "<i>↩ ответь на это сообщение, чтобы исправить или удалить</i>",
        parse_mode="HTML",
    )
    storage.log_event.assert_called_once()
    call_kwargs = storage.log_event.call_args.kwargs
    assert call_kwargs["event_type"] == "logged"
    assert call_kwargs["data"] == habit
    assert call_kwargs["raw_text"] == "почитал 30 мин фромма"
    assert call_kwargs["bot_message_id"] == 999
    assert call_kwargs["user_id"] == 1


@pytest.mark.asyncio
async def test_habit_handler_ignores_non_habit_text():
    llm = AsyncMock()
    llm.parse_habit = AsyncMock(return_value=None)

    storage = AsyncMock()
    storage.log_event = AsyncMock()

    message = _make_message("привет как дела")

    await habit_handler(message, llm=llm, storage=storage)

    message.answer.assert_not_called()
    storage.log_event.assert_not_called()


@pytest.mark.asyncio
async def test_correction_handler_updates_and_confirms():
    original_doc = {
        "habit_id": "habit-uuid-1",
        "event_type": "logged",
        "habit_type": "reading",
        "author": "Эрих Фромм",
        "book_title": "Искусство Любить",
        "duration_minutes": 30,
        "raw_text": "почитал фромма",
    }
    updated = HabitData("reading", "Лев Толстой", "Война и мир", 45)

    storage = AsyncMock()
    storage.find_habit_by_message_id = AsyncMock(return_value=("habit-uuid-1", original_doc))
    storage.get_current_state = AsyncMock(return_value=original_doc)
    storage.log_event = AsyncMock(return_value="event456")

    llm = AsyncMock()
    llm.correct_habit = AsyncMock(return_value=updated)

    message = _make_reply_message("нет, Толстой Война и мир 45 мин", replied_id=42)

    await correction_handler(message, llm=llm, storage=storage)

    storage.find_habit_by_message_id.assert_called_once_with(42)
    llm.correct_habit.assert_called_once()
    storage.log_event.assert_called_once()
    call_kwargs = storage.log_event.call_args.kwargs
    assert call_kwargs["event_type"] == "corrected"
    assert call_kwargs["data"] == updated
    message.reply_to_message.edit_text.assert_called_once_with(
        "✓ Чтение — 45 мин — Лев Толстой «Война и мир»\n"
        "<i>↩ ответь на это сообщение, чтобы исправить или удалить</i>",
        parse_mode="HTML",
    )


@pytest.mark.asyncio
async def test_correction_handler_ignores_unknown_bot_message():
    storage = AsyncMock()
    storage.find_habit_by_message_id = AsyncMock(return_value=None)

    llm = AsyncMock()

    message = _make_reply_message("поправка", replied_id=99)

    await correction_handler(message, llm=llm, storage=storage)

    llm.correct_habit.assert_not_called()
    message.answer.assert_not_called()


@pytest.mark.asyncio
async def test_correction_handler_replies_on_unparseable_correction():
    original_doc = {
        "habit_id": "habit-uuid-2",
        "event_type": "logged",
        "habit_type": "reading",
        "author": "Эрих Фромм",
        "book_title": "Искусство Любить",
        "duration_minutes": 30,
        "raw_text": "оригинал",
    }

    storage = AsyncMock()
    storage.find_habit_by_message_id = AsyncMock(return_value=("habit-uuid-2", original_doc))
    storage.get_current_state = AsyncMock(return_value=original_doc)
    storage.log_event = AsyncMock()

    llm = AsyncMock()
    llm.correct_habit = AsyncMock(return_value=None)

    message = _make_reply_message("непонятная поправка", replied_id=55)

    await correction_handler(message, llm=llm, storage=storage)

    storage.log_event.assert_not_called()
    message.answer.assert_called_once_with("Не смог разобрать поправку")


@pytest.mark.asyncio
async def test_correction_handler_deletes_on_keyword():
    original_doc = {
        "habit_id": "habit-uuid-3",
        "event_type": "logged",
        "habit_type": "reading",
        "author": "Эрих Фромм",
        "book_title": "Искусство Любить",
        "duration_minutes": 30,
        "raw_text": "почитал фромма",
    }

    storage = AsyncMock()
    storage.find_habit_by_message_id = AsyncMock(return_value=("habit-uuid-3", original_doc))
    storage.get_current_state = AsyncMock(return_value=original_doc)
    storage.log_event = AsyncMock(return_value="event789")

    llm = AsyncMock()

    message = _make_reply_message("удали", replied_id=77)

    await correction_handler(message, llm=llm, storage=storage)

    llm.correct_habit.assert_not_called()
    storage.log_event.assert_called_once()
    call_kwargs = storage.log_event.call_args.kwargs
    assert call_kwargs["event_type"] == "deleted"
    assert call_kwargs["data"] is None
    message.reply_to_message.edit_text.assert_called_once_with("🗑 Удалено")


@pytest.mark.asyncio
async def test_today_handler_empty():
    storage = AsyncMock()
    storage.get_today_habits = AsyncMock(return_value=[])

    message = _make_message("/today")

    await today_handler(message, storage=storage)

    message.answer.assert_called_once_with("Сегодня ничего не записано.")


@pytest.mark.asyncio
async def test_today_handler_with_habits():
    habits = [
        {
            "habit_id": "h1",
            "event_type": "logged",
            "author": "Эрих Фромм",
            "book_title": "Искусство любить",
            "duration_minutes": 15,
        },
        {
            "habit_id": "h2",
            "event_type": "corrected",
            "author": "Лев Толстой",
            "book_title": "Война и мир",
            "duration_minutes": 45,
        },
    ]

    storage = AsyncMock()
    storage.get_today_habits = AsyncMock(return_value=habits)

    message = _make_message("/today")

    await today_handler(message, storage=storage)

    message.answer.assert_called_once()
    call_args = message.answer.call_args
    assert call_args.kwargs.get("parse_mode") == "HTML" or (
        len(call_args.args) > 1 and call_args.args[1] == "HTML"
    )
    text = call_args.args[0]
    assert "Эрих Фромм" in text
    assert "15 мин" in text
    assert "Лев Толстой" in text
    assert "45 мин" in text
