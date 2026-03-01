import html
import uuid
from datetime import datetime, timezone

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import Message

from bot.models import HabitData
from bot.services.llm import LLMService
from bot.services.storage import StorageService

router = Router()

DELETE_KEYWORDS = {"удали", "удалить", "delete", "убери", "убрать"}


def _today_date() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _format_confirmation(data: HabitData) -> str:
    return (
        f"✓ Чтение — {data.duration_minutes} мин — "
        f"{html.escape(data.author)} «{html.escape(data.book_title)}»\n"
        f"<i>↩ ответь на это сообщение, чтобы исправить или удалить</i>"
    )


def _habit_from_doc(doc: dict) -> HabitData:
    return HabitData(
        habit_type=doc["habit_type"],
        author=doc["author"],
        book_title=doc["book_title"],
        duration_minutes=doc["duration_minutes"],
    )


@router.message(
    F.text,
    F.reply_to_message,
    F.reply_to_message.from_user.is_bot == True,  # noqa: E712
)
async def correction_handler(
    message: Message,
    llm: LLMService,
    storage: StorageService,
) -> None:
    replied_message_id = message.reply_to_message.message_id
    result = await storage.find_habit_by_message_id(replied_message_id)
    if result is None:
        return

    habit_id, logged_event = result

    current_doc = await storage.get_current_state(habit_id)
    if current_doc is None:
        return  # already deleted

    if message.text.strip().lower() in DELETE_KEYWORDS:
        await storage.log_event(
            habit_id=habit_id,
            event_type="deleted",
            data=None,
            raw_text=None,
            bot_message_id=None,
            user_id=message.from_user.id,
            date=_today_date(),
        )
        deleted_text = (
            f"🗑 Удалено [{html.escape(current_doc.get('author', '?'))} "
            f"«{html.escape(current_doc.get('book_title', '?'))}» "
            f"— {current_doc.get('duration_minutes', '?')} мин]"
        )
        await message.reply_to_message.edit_text(deleted_text, parse_mode="HTML")
        return

    current = _habit_from_doc(current_doc)
    new_data = await llm.correct_habit(
        original_text=logged_event.get("raw_text", ""),
        correction_text=message.text,
        current=current,
    )
    if new_data is None:
        await message.answer("Не смог разобрать поправку")
        return

    await storage.log_event(
        habit_id=habit_id,
        event_type="corrected",
        data=new_data,
        raw_text=None,
        bot_message_id=None,
        user_id=message.from_user.id,
        date=_today_date(),
    )
    await message.reply_to_message.edit_text(_format_confirmation(new_data), parse_mode="HTML")


@router.message(F.text, ~F.reply_to_message, ~F.text.startswith("/"))
async def habit_handler(
    message: Message,
    llm: LLMService,
    storage: StorageService,
) -> None:
    data = await llm.parse_habit(message.text)
    if data is None:
        return

    habit_id = str(uuid.uuid4())
    sent = await message.answer(_format_confirmation(data), parse_mode="HTML")
    await storage.log_event(
        habit_id=habit_id,
        event_type="logged",
        data=data,
        raw_text=message.text,
        bot_message_id=sent.message_id,
        user_id=message.from_user.id,
        date=_today_date(),
    )


@router.message(Command("today"))
async def today_handler(message: Message, storage: StorageService) -> None:
    habits = await storage.get_today_habits(date=_today_date())
    if not habits:
        await message.answer("Сегодня ничего не записано.")
        return
    lines = [
        f"• {html.escape(h.get('author', '?'))} «{html.escape(h.get('book_title', '?'))}»"
        f" — {h.get('duration_minutes', '?')} мин"
        for h in habits
    ]
    await message.answer("\n".join(lines), parse_mode="HTML")
