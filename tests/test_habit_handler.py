import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from bot.models import HabitData
from bot.handlers.habits import (
    habit_handler, correction_handler, today_handler,
    new_type_callback, _pending_habits,
)


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


def _make_storage(known_types: set[str] | None = None) -> AsyncMock:
    storage = AsyncMock()
    storage.log_event = AsyncMock(return_value="event123")
    _known = known_types or set()
    storage.is_known_type = MagicMock(side_effect=lambda t: t in _known)
    storage.add_known_type = AsyncMock()
    return storage


def _make_callback(data: str, message_id: int = 500) -> AsyncMock:
    callback = AsyncMock()
    callback.data = data
    callback.message = AsyncMock()
    callback.message.message_id = message_id
    callback.message.edit_text = AsyncMock()
    callback.answer = AsyncMock()
    return callback


# --- habit_handler tests ---

@pytest.mark.asyncio
async def test_habit_handler_sends_confirmation_known_type():
    habit = HabitData("чтение", "Чтение — 30 мин — Эрих Фромм «Искусство Любить»")

    llm = AsyncMock()
    llm.parse_habit = AsyncMock(return_value=habit)

    storage = _make_storage(known_types={"чтение"})
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

    storage = _make_storage()
    message = _make_message("привет как дела")

    await habit_handler(message, llm=llm, storage=storage)

    message.answer.assert_not_called()
    storage.log_event.assert_not_called()


@pytest.mark.asyncio
async def test_habit_handler_new_type_asks_confirmation():
    habit = HabitData("йога", "Йога — 20 мин")

    llm = AsyncMock()
    llm.parse_habit = AsyncMock(return_value=habit)

    storage = _make_storage(known_types=set())  # йога is unknown
    message = _make_message("позанималась йогой 20 минут")

    await habit_handler(message, llm=llm, storage=storage)

    # Should ask confirmation, not log directly
    storage.log_event.assert_not_called()
    message.answer.assert_called_once()
    call_args = message.answer.call_args
    text = call_args.args[0]
    assert "йога" in text
    assert call_args.kwargs.get("reply_markup") is not None


# --- new_type_callback tests ---

@pytest.mark.asyncio
async def test_new_type_callback_yes_saves():
    habit = HabitData("йога", "Йога — 20 мин")
    callback_id = "test-uuid-1"
    _pending_habits[callback_id] = (habit, "позанималась йогой", 1)

    storage = _make_storage()
    callback = _make_callback(f"new_type:yes:{callback_id}")

    await new_type_callback(callback, storage=storage)

    storage.add_known_type.assert_called_once_with("йога")
    storage.log_event.assert_called_once()
    call_kwargs = storage.log_event.call_args.kwargs
    assert call_kwargs["event_type"] == "logged"
    assert call_kwargs["data"] == habit
    callback.message.edit_text.assert_called_once()
    assert callback_id not in _pending_habits


@pytest.mark.asyncio
async def test_new_type_callback_no_discards():
    habit = HabitData("йога", "Йога — 20 мин")
    callback_id = "test-uuid-2"
    _pending_habits[callback_id] = (habit, "позанималась йогой", 1)

    storage = _make_storage()
    callback = _make_callback(f"new_type:no:{callback_id}")

    await new_type_callback(callback, storage=storage)

    storage.add_known_type.assert_not_called()
    storage.log_event.assert_not_called()
    callback.message.edit_text.assert_called_once_with("Отменено.")
    assert callback_id not in _pending_habits


@pytest.mark.asyncio
async def test_new_type_callback_expired():
    storage = _make_storage()
    callback = _make_callback("new_type:yes:nonexistent-uuid")

    await new_type_callback(callback, storage=storage)

    storage.log_event.assert_not_called()
    callback.message.edit_text.assert_called_once_with("Запрос устарел.")


# --- correction_handler tests ---

@pytest.mark.asyncio
async def test_correction_handler_updates_and_confirms():
    original_doc = {
        "habit_id": "habit-uuid-1",
        "event_type": "logged",
        "habit_type": "чтение",
        "summary": "Чтение — 30 мин — Эрих Фромм «Искусство Любить»",
        "details": {"author": "Эрих Фромм", "book_title": "Искусство Любить", "duration_minutes": 30},
        "raw_text": "почитал фромма",
    }
    updated = HabitData(
        "чтение",
        "Чтение — 45 мин — Лев Толстой «Война и мир»",
        {"author": "Лев Толстой", "book_title": "Война и мир", "duration_minutes": 45},
    )

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
        "habit_type": "чтение",
        "summary": "Чтение — 30 мин",
        "details": {},
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
        "habit_type": "чтение",
        "summary": "Чтение — 30 мин — Эрих Фромм «Искусство Любить»",
        "details": {"author": "Эрих Фромм"},
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
    message.reply_to_message.edit_text.assert_called_once_with(
        "🗑 Удалено [Чтение — 30 мин — Эрих Фромм «Искусство Любить»]",
        parse_mode="HTML",
    )


# --- today_handler tests ---

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
            "summary": "Чтение — 15 мин — Эрих Фромм «Искусство любить»",
        },
        {
            "habit_id": "h2",
            "event_type": "corrected",
            "summary": "Йога — 45 мин",
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
    assert "Йога" in text
    assert "45 мин" in text


# --- storage known types tests ---

@pytest.mark.asyncio
async def test_storage_known_types():
    """Test load/add/is_known for StorageService known types."""
    from bot.services.storage import StorageService

    mock_doc = MagicMock()
    mock_doc.exists = True
    mock_doc.to_dict = MagicMock(return_value={"types": ["чтение", "йога"]})

    mock_db = AsyncMock()
    mock_db.document = MagicMock(return_value=AsyncMock())
    mock_db.document.return_value.get = AsyncMock(return_value=mock_doc)
    mock_db.document.return_value.set = AsyncMock()

    storage = StorageService(db=mock_db)

    # Initially empty
    assert not storage.is_known_type("чтение")

    # After load
    await storage.load_known_types()
    assert storage.is_known_type("чтение")
    assert storage.is_known_type("йога")
    assert not storage.is_known_type("сон")

    # After add
    await storage.add_known_type("сон")
    assert storage.is_known_type("сон")
