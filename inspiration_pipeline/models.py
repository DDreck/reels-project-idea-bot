"""Domain dataclasses for the inspiration pipeline."""
from dataclasses import dataclass


@dataclass(frozen=True)
class ReelMeta:
    pk: str
    shortcode: str
    url: str
    author: str
    caption: str
    taken_at: str  # ISO date, e.g. "2026-06-25"
    collection: str


@dataclass(frozen=True)
class Classification:
    category: str
    title: str
    summary: str
    key_points: list[str]
    domain: str  # "Health" | "Projects" | "none"
    is_new_category: bool = False
    category_description: str = ""

    @classmethod
    def from_json(cls, data: dict) -> "Classification":
        return cls(
            category=str(data["category"]),
            title=str(data["title"]),
            summary=str(data["summary"]),
            key_points=list(data["key_points"]),
            domain=str(data["domain"]),
            is_new_category=bool(data.get("is_new_category", False)),
            category_description=str(data.get("category_description", "")),
        )
