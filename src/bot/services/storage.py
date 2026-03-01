from google.cloud import firestore

from bot.models import HabitData

COLLECTION = "habit_events"


class StorageService:
    def __init__(self, db: firestore.AsyncClient | None = None):
        self._db = db or firestore.AsyncClient()

    async def log_event(
        self,
        habit_id: str,
        event_type: str,
        data: HabitData | None,
        raw_text: str | None,
        bot_message_id: int | None,
        user_id: int,
        date: str,
    ) -> str:
        doc_ref = self._db.collection(COLLECTION).document()
        await doc_ref.set({
            "habit_id": habit_id,
            "event_type": event_type,
            "habit_type": data.habit_type if data else None,
            "author": data.author if data else None,
            "book_title": data.book_title if data else None,
            "duration_minutes": data.duration_minutes if data else None,
            "raw_text": raw_text,
            "bot_message_id": bot_message_id,
            "user_id": user_id,
            "timestamp": firestore.SERVER_TIMESTAMP,
            "date": date,
        })
        return doc_ref.id

    async def find_habit_by_message_id(self, message_id: int) -> tuple[str, dict] | None:
        query = (
            self._db.collection(COLLECTION)
            .where("bot_message_id", "==", message_id)
            .limit(1)
        )
        async for doc in query.stream():
            return doc.to_dict()["habit_id"], doc.to_dict()
        return None

    async def get_current_state(self, habit_id: str) -> dict | None:
        query = (
            self._db.collection(COLLECTION)
            .where("habit_id", "==", habit_id)
            .order_by("timestamp", direction=firestore.Query.DESCENDING)
            .limit(1)
        )
        async for doc in query.stream():
            d = doc.to_dict()
            return None if d["event_type"] == "deleted" else d
        return None

    async def get_today_habits(self, date: str) -> list[dict]:
        query = (
            self._db.collection(COLLECTION)
            .where("date", "==", date)
            .order_by("timestamp", direction=firestore.Query.DESCENDING)
        )
        seen: dict[str, dict] = {}
        async for doc in query.stream():
            d = doc.to_dict()
            hid = d["habit_id"]
            if hid not in seen:
                seen[hid] = d
        return [d for d in seen.values() if d["event_type"] != "deleted"]
