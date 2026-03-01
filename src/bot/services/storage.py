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
        """Append a new event document to habit_events collection.

        Each call creates a new document — nothing is overwritten (event sourcing).
        Returns the Firestore document ID of the created event.

        Args:
            habit_id: UUID shared across all events for the same habit instance.
            event_type: One of "logged", "corrected", "deleted".
            data: Habit payload. Pass None for "deleted" events.
            raw_text: Original user message. Only set for "logged" events.
            bot_message_id: Telegram message ID of the bot's reply. Only set for "logged" events.
            user_id: Telegram user ID of the author.
            date: UTC date string "YYYY-MM-DD" for daily grouping.
        """
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
        """Find the "logged" event that produced the given bot message.

        Returns (habit_id, event_doc) or None if not found.
        Used to link a user's reply back to the original habit.
        """
        query = (
            self._db.collection(COLLECTION)
            .where("bot_message_id", "==", message_id)
            .limit(1)
        )
        async for doc in query.stream():
            return doc.to_dict()["habit_id"], doc.to_dict()
        return None

    async def get_current_state(self, habit_id: str) -> dict | None:
        """Return the latest event for habit_id, or None if deleted/not found.

        Reads the most recent event. If its event_type is "deleted", returns None
        (the habit no longer exists). Otherwise returns the event dict as current state.
        """
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
        """Return all active habits for the given UTC date.

        Groups events by habit_id client-side, keeping only the latest event per habit.
        Excludes habits whose latest event_type is "deleted".
        """
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
