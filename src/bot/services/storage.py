from google.cloud import firestore

from bot.models import HabitData

COLLECTION = "habit_events"
META_DOC = "meta/known_habit_types"


class StorageService:
    def __init__(self, db: firestore.AsyncClient | None = None):
        self._db = db or firestore.AsyncClient()
        self._known_types: set[str] = set()

    async def load_known_types(self) -> None:
        """Load known habit types from Firestore into local cache."""
        doc = await self._db.document(META_DOC).get()
        if doc.exists:
            self._known_types = set(doc.to_dict().get("types", []))

    def is_known_type(self, habit_type: str) -> bool:
        """Check if a habit type is already known (cached)."""
        return habit_type in self._known_types

    async def add_known_type(self, habit_type: str) -> None:
        """Add a new habit type to Firestore and local cache."""
        self._known_types.add(habit_type)
        await self._db.document(META_DOC).set(
            {"types": firestore.ArrayUnion([habit_type])}, merge=True
        )

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
        """
        doc_ref = self._db.collection(COLLECTION).document()
        await doc_ref.set({
            "habit_id": habit_id,
            "event_type": event_type,
            "habit_type": data.habit_type if data else None,
            "summary": data.summary if data else None,
            "details": data.details if data else None,
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
        """Return the latest event for habit_id, or None if deleted/not found."""
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
        """Return all active habits for the given UTC date."""
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
