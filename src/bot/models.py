from dataclasses import dataclass, field


@dataclass
class HabitData:
    habit_type: str      # "чтение", "йога", "сон", "дневник", ...
    summary: str         # LLM-generated: "Чтение — 30 мин — Фромм «Искусство любить»"
    details: dict = field(default_factory=dict)  # arbitrary structured data
