import json
import pytest
from unittest.mock import AsyncMock, MagicMock

from bot.models import HabitData
from bot.services.llm import LLMService


def _make_llm_service(response_content: str) -> LLMService:
    """Build an LLMService with a mocked aiohttp session."""
    mock_resp = AsyncMock()
    mock_resp.status = 200
    mock_resp.json = AsyncMock(
        return_value={
            "choices": [{"message": {"content": response_content}}]
        }
    )

    mock_cm = AsyncMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_cm.__aexit__ = AsyncMock(return_value=False)

    session = MagicMock()
    session.post = MagicMock(return_value=mock_cm)

    return LLMService(session=session, api_key="test-key")


@pytest.mark.asyncio
async def test_parse_habit_returns_habit_data():
    payload = {
        "habit_type": "чтение",
        "summary": "Чтение — 30 мин — Эрих Фромм «Искусство Любить»",
        "details": {"author": "Эрих Фромм", "book_title": "Искусство Любить", "duration_minutes": 30},
    }
    llm = _make_llm_service(json.dumps(payload, ensure_ascii=False))
    result = await llm.parse_habit("почитал 30 мин фромма искусство любить")
    assert result == HabitData(
        habit_type="чтение",
        summary="Чтение — 30 мин — Эрих Фромм «Искусство Любить»",
        details={"author": "Эрих Фромм", "book_title": "Искусство Любить", "duration_minutes": 30},
    )


@pytest.mark.asyncio
async def test_parse_habit_returns_none_for_null():
    llm = _make_llm_service("null")
    result = await llm.parse_habit("привет как дела")
    assert result is None


@pytest.mark.asyncio
async def test_parse_habit_returns_none_for_invalid_json():
    llm = _make_llm_service("not valid json at all")
    result = await llm.parse_habit("какой-то текст")
    assert result is None


@pytest.mark.asyncio
async def test_parse_habit_strips_markdown_fences():
    payload = {
        "habit_type": "чтение",
        "summary": "Чтение — 45 мин — Лев Толстой «Война и мир»",
        "details": {"author": "Лев Толстой", "book_title": "Война и мир", "duration_minutes": 45},
    }
    content = f"```json\n{json.dumps(payload, ensure_ascii=False)}\n```"
    llm = _make_llm_service(content)
    result = await llm.parse_habit("читал толстого войну и мир 45 мин")
    assert result == HabitData(
        habit_type="чтение",
        summary="Чтение — 45 мин — Лев Толстой «Война и мир»",
        details={"author": "Лев Толстой", "book_title": "Война и мир", "duration_minutes": 45},
    )


@pytest.mark.asyncio
async def test_parse_habit_without_details():
    payload = {
        "habit_type": "йога",
        "summary": "Йога — 20 мин",
    }
    llm = _make_llm_service(json.dumps(payload, ensure_ascii=False))
    result = await llm.parse_habit("позанималась йогой 20 минут")
    assert result == HabitData(
        habit_type="йога",
        summary="Йога — 20 мин",
        details={},
    )


@pytest.mark.asyncio
async def test_correct_habit_returns_updated_data():
    updated = {
        "habit_type": "чтение",
        "summary": "Чтение — 45 мин — Лев Толстой «Война и мир»",
        "details": {"author": "Лев Толстой", "book_title": "Война и мир", "duration_minutes": 45},
    }
    llm = _make_llm_service(json.dumps(updated, ensure_ascii=False))
    current = HabitData(
        habit_type="чтение",
        summary="Чтение — 30 мин — Эрих Фромм «Искусство Любить»",
        details={"author": "Эрих Фромм", "book_title": "Искусство Любить", "duration_minutes": 30},
    )
    result = await llm.correct_habit(
        original_text="почитал 30 мин фромма",
        correction_text="нет, Толстой Война и мир 45 мин",
        current=current,
    )
    assert result == HabitData(
        habit_type="чтение",
        summary="Чтение — 45 мин — Лев Толстой «Война и мир»",
        details={"author": "Лев Толстой", "book_title": "Война и мир", "duration_minutes": 45},
    )


@pytest.mark.asyncio
async def test_correct_habit_returns_none_on_null():
    llm = _make_llm_service("null")
    current = HabitData("чтение", "Чтение — 30 мин", {})
    result = await llm.correct_habit("оригинал", "непонятная поправка", current)
    assert result is None
