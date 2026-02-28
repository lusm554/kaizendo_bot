import pytest
from unittest.mock import AsyncMock, MagicMock

from bot.models import HabitData
from bot.handlers.habits import habit_handler, correction_handler


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
    replied = MagicMock()
    replied.message_id = replied_id
    replied.from_user = MagicMock()
    replied.from_user.is_bot = True
    message.reply_to_message = replied
    return message


@pytest.mark.asyncio
async def test_habit_handler_sends_confirmation():
    habit = HabitData("reading", "Эрих Фромм", "Искусство Любить", 30)

    llm = AsyncMock()
    llm.parse_habit = AsyncMock(return_value=habit)

    storage = AsyncMock()
    storage.save_habit = AsyncMock(return_value="doc123")

    message = _make_message("почитал 30 мин фромма")

    await habit_handler(message, llm=llm, storage=storage)

    message.answer.assert_called_once_with(
        "✓ Чтение — 30 мин — Эрих Фромм «Искусство Любить»"
    )
    storage.save_habit.assert_called_once_with(
        data=habit,
        raw_text="почитал 30 мин фромма",
        bot_message_id=999,
        user_id=1,
    )


@pytest.mark.asyncio
async def test_habit_handler_ignores_non_habit_text():
    llm = AsyncMock()
    llm.parse_habit = AsyncMock(return_value=None)

    storage = AsyncMock()

    message = _make_message("привет как дела")

    await habit_handler(message, llm=llm, storage=storage)

    message.answer.assert_not_called()
    storage.save_habit.assert_not_called()


@pytest.mark.asyncio
async def test_correction_handler_updates_and_confirms():
    original_doc = {
        "habit_type": "reading",
        "author": "Эрих Фромм",
        "book_title": "Искусство Любить",
        "duration_minutes": 30,
        "raw_text": "почитал фромма",
    }
    updated = HabitData("reading", "Лев Толстой", "Война и мир", 45)

    storage = AsyncMock()
    storage.find_by_bot_message_id = AsyncMock(return_value=("doc123", original_doc))
    storage.update_habit = AsyncMock()

    llm = AsyncMock()
    llm.correct_habit = AsyncMock(return_value=updated)

    message = _make_reply_message("нет, Толстой Война и мир 45 мин", replied_id=42)

    await correction_handler(message, llm=llm, storage=storage)

    storage.find_by_bot_message_id.assert_called_once_with(42)
    llm.correct_habit.assert_called_once()
    storage.update_habit.assert_called_once_with("doc123", updated)
    message.answer.assert_called_once_with(
        "✓ Чтение — 45 мин — Лев Толстой «Война и мир»"
    )


@pytest.mark.asyncio
async def test_correction_handler_ignores_unknown_bot_message():
    storage = AsyncMock()
    storage.find_by_bot_message_id = AsyncMock(return_value=None)

    llm = AsyncMock()

    message = _make_reply_message("поправка", replied_id=99)

    await correction_handler(message, llm=llm, storage=storage)

    llm.correct_habit.assert_not_called()
    message.answer.assert_not_called()


@pytest.mark.asyncio
async def test_correction_handler_replies_on_unparseable_correction():
    original_doc = {
        "habit_type": "reading",
        "author": "Эрих Фромм",
        "book_title": "Искусство Любить",
        "duration_minutes": 30,
        "raw_text": "оригинал",
    }

    storage = AsyncMock()
    storage.find_by_bot_message_id = AsyncMock(return_value=("doc123", original_doc))
    storage.update_habit = AsyncMock()

    llm = AsyncMock()
    llm.correct_habit = AsyncMock(return_value=None)

    message = _make_reply_message("непонятная поправка", replied_id=55)

    await correction_handler(message, llm=llm, storage=storage)

    storage.update_habit.assert_not_called()
    message.answer.assert_called_once_with("Не смог разобрать поправку")
