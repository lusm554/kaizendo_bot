from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

router = Router()


@router.message(Command("ping"))
async def ping_handler(message: Message) -> None:
    await message.answer("pong!")
