from aiogram import F, Router
from aiogram.types import Message

from bot.models import HabitData
from bot.services.llm import LLMService
from bot.services.storage import StorageService

router = Router()


def _format_confirmation(data: HabitData) -> str:
    return (
        f"✓ Чтение — {data.duration_minutes} мин — "
        f"{data.author} «{data.book_title}»"
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
    result = await storage.find_by_bot_message_id(replied_message_id)
    if result is None:
        return

    doc_id, doc = result
    current = _habit_from_doc(doc)
    new_data = await llm.correct_habit(
        original_text=doc.get("raw_text", ""),
        correction_text=message.text,
        current=current,
    )
    if new_data is None:
        await message.answer("Не смог разобрать поправку")
        return

    await storage.update_habit(doc_id, new_data)
    await message.answer(_format_confirmation(new_data))


@router.message(F.text, ~F.reply_to_message, ~F.text.startswith("/"))
async def habit_handler(
    message: Message,
    llm: LLMService,
    storage: StorageService,
) -> None:
    data = await llm.parse_habit(message.text)
    if data is None:
        return

    sent = await message.answer(_format_confirmation(data))
    await storage.save_habit(
        data=data,
        raw_text=message.text,
        bot_message_id=sent.message_id,
        user_id=message.from_user.id,
    )
