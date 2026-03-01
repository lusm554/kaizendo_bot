import html
import uuid
from datetime import datetime, timezone

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot.models import HabitData
from bot.services.llm import LLMService
from bot.services.storage import StorageService

router = Router()

DELETE_KEYWORDS = {"удали", "удалить", "delete", "убери", "убрать"}

# Pending habits awaiting new-type confirmation via inline buttons.
# Key: callback UUID, Value: (HabitData, raw_text, user_id)
_pending_habits: dict[str, tuple[HabitData, str, int]] = {}


def _today_date() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _format_confirmation(data: HabitData) -> str:
    return (
        f"✓ {html.escape(data.summary)}\n"
        f"<i>↩ ответь на это сообщение, чтобы исправить или удалить</i>"
    )


def _habit_from_doc(doc: dict) -> HabitData:
    return HabitData(
        habit_type=doc["habit_type"],
        summary=doc.get("summary", ""),
        details=doc.get("details") or {},
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
        summary = current_doc.get("summary", "?")
        deleted_text = f"🗑 Удалено [{html.escape(summary)}]"
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

    if not storage.is_known_type(data.habit_type):
        callback_id = str(uuid.uuid4())
        _pending_habits[callback_id] = (data, message.text, message.from_user.id)
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="Да", callback_data=f"new_type:yes:{callback_id}"),
                InlineKeyboardButton(text="Нет", callback_data=f"new_type:no:{callback_id}"),
            ]
        ])
        await message.answer(
            f"Новый тип привычки: <b>{html.escape(data.habit_type)}</b>. Сохранить?",
            parse_mode="HTML",
            reply_markup=keyboard,
        )
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


@router.callback_query(F.data.startswith("new_type:"))
async def new_type_callback(
    callback: CallbackQuery,
    storage: StorageService,
) -> None:
    parts = callback.data.split(":", 2)
    if len(parts) != 3:
        await callback.answer("Ошибка")
        return

    action, callback_id = parts[1], parts[2]
    pending = _pending_habits.pop(callback_id, None)

    if pending is None:
        await callback.message.edit_text("Запрос устарел.")
        await callback.answer()
        return

    data, raw_text, user_id = pending

    if action == "no":
        await callback.message.edit_text("Отменено.")
        await callback.answer()
        return

    # action == "yes"
    await storage.add_known_type(data.habit_type)
    habit_id = str(uuid.uuid4())
    sent = await callback.message.edit_text(_format_confirmation(data), parse_mode="HTML")
    await storage.log_event(
        habit_id=habit_id,
        event_type="logged",
        data=data,
        raw_text=raw_text,
        bot_message_id=callback.message.message_id,
        user_id=user_id,
        date=_today_date(),
    )
    await callback.answer()


@router.message(Command("today"))
async def today_handler(message: Message, storage: StorageService) -> None:
    habits = await storage.get_today_habits(date=_today_date())
    if not habits:
        await message.answer("Сегодня ничего не записано.")
        return
    lines = [
        f"• {html.escape(h.get('summary', '?'))}"
        for h in habits
    ]
    await message.answer("\n".join(lines), parse_mode="HTML")
