from dataclasses import dataclass


@dataclass
class HabitData:
    habit_type: str          # e.g. "reading"
    author: str              # e.g. "Эрих Фромм"
    book_title: str          # e.g. "Искусство Любить"
    duration_minutes: int    # e.g. 30
