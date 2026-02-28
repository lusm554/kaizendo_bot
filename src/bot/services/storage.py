from google.cloud import firestore

from bot.models import HabitData

COLLECTION = "habits"


class StorageService:
    def __init__(self, db: firestore.AsyncClient | None = None):
        self._db = db or firestore.AsyncClient()

    async def save_habit(
        self,
        data: HabitData,
        raw_text: str,
        bot_message_id: int,
        user_id: int,
    ) -> str:
        doc_ref = self._db.collection(COLLECTION).document()
        await doc_ref.set(
            {
                "habit_type": data.habit_type,
                "author": data.author,
                "book_title": data.book_title,
                "duration_minutes": data.duration_minutes,
                "raw_text": raw_text,
                "timestamp": firestore.SERVER_TIMESTAMP,
                "bot_message_id": bot_message_id,
                "user_id": user_id,
            }
        )
        return doc_ref.id

    async def update_habit(self, doc_id: str, data: HabitData) -> None:
        doc_ref = self._db.collection(COLLECTION).document(doc_id)
        await doc_ref.update(
            {
                "habit_type": data.habit_type,
                "author": data.author,
                "book_title": data.book_title,
                "duration_minutes": data.duration_minutes,
            }
        )

    async def find_by_bot_message_id(self, message_id: int) -> tuple[str, dict] | None:
        query = (
            self._db.collection(COLLECTION)
            .where("bot_message_id", "==", message_id)
            .limit(1)
        )
        docs = query.stream()
        async for doc in docs:
            return doc.id, doc.to_dict()
        return None
