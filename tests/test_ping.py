import pytest
from unittest.mock import AsyncMock
from bot.handlers.basic import ping_handler


@pytest.mark.asyncio
async def test_ping_replies_pong():
    message = AsyncMock()
    await ping_handler(message)
    message.answer.assert_called_once_with("pong!")
