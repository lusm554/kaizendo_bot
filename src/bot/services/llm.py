import json
import os
import re

import aiohttp

from bot.models import HabitData

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = "google/gemini-2.5-flash-lite"

SYSTEM_PROMPT = """You are a habit tracking assistant. Extract habit data from the user's message.

Return a JSON object with these fields:
- habit_type: string (e.g. "reading", "exercise", "meditation")
- author: string (full normalized name, e.g. "Эрих Фромм")
- book_title: string (normalized title, e.g. "Искусство Любить")
- duration_minutes: integer

If the message does not describe a completed habit, return null.
Return only valid JSON, no markdown fences."""

CORRECTION_SYSTEM_PROMPT = """You are a habit tracking assistant. The user is correcting a previously parsed habit entry.
Given the original message, the current parsed data, and the user's correction, return updated JSON.

Return a JSON object with these fields:
- habit_type: string
- author: string (full normalized name)
- book_title: string (normalized title)
- duration_minutes: integer

If you cannot parse the correction, return null.
Return only valid JSON, no markdown fences."""


def _parse_json(content: str) -> dict | None:
    content = content.strip()
    # Strip markdown code fences if present
    content = re.sub(r"^```(?:json)?\s*", "", content)
    content = re.sub(r"\s*```$", "", content)
    content = content.strip()
    if content.lower() == "null":
        return None
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        return None


def _dict_to_habit(data: dict) -> HabitData | None:
    try:
        return HabitData(
            habit_type=str(data["habit_type"]),
            author=str(data["author"]),
            book_title=str(data["book_title"]),
            duration_minutes=int(data["duration_minutes"]),
        )
    except (KeyError, ValueError, TypeError):
        return None


class LLMService:
    def __init__(self, session: aiohttp.ClientSession, api_key: str | None = None):
        self._session = session
        self._api_key = api_key or os.environ["OPENROUTER_API_KEY"]

    async def _complete(self, messages: list[dict]) -> str | None:
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        payload = {"model": MODEL, "messages": messages}
        async with self._session.post(OPENROUTER_URL, headers=headers, json=payload) as resp:
            if resp.status != 200:
                return None
            data = await resp.json()
            return data["choices"][0]["message"]["content"]

    async def parse_habit(self, text: str) -> HabitData | None:
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": text},
        ]
        content = await self._complete(messages)
        if content is None:
            return None
        parsed = _parse_json(content)
        if parsed is None:
            return None
        return _dict_to_habit(parsed)

    async def correct_habit(
        self, original_text: str, correction_text: str, current: HabitData
    ) -> HabitData | None:
        current_json = json.dumps(
            {
                "habit_type": current.habit_type,
                "author": current.author,
                "book_title": current.book_title,
                "duration_minutes": current.duration_minutes,
            },
            ensure_ascii=False,
        )
        user_content = (
            f"Original message: {original_text}\n"
            f"Current parsed data: {current_json}\n"
            f"User correction: {correction_text}"
        )
        messages = [
            {"role": "system", "content": CORRECTION_SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ]
        content = await self._complete(messages)
        if content is None:
            return None
        parsed = _parse_json(content)
        if parsed is None:
            return None
        return _dict_to_habit(parsed)
