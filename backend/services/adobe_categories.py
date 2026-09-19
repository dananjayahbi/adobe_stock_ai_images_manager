"""Adobe Stock category codes for the CSV ``Category`` column.

The Contributor Portal expects the *numeric* code, not the name. The list is
fixed by Adobe, so it lives here rather than in the database.
"""

from __future__ import annotations

CATEGORY_CODES: dict[int, str] = {
    1: "Animals",
    2: "Buildings and Architecture",
    3: "Business",
    4: "Drinks",
    5: "The Environment",
    6: "States of Mind",
    7: "Food",
    8: "Graphic Resources",
    9: "Hobbies and Leisure",
    10: "Industry",
    11: "Landscapes",
    12: "Lifestyle",
    13: "People",
    14: "Plants and Flowers",
    15: "Culture and Religion",
    16: "Science",
    17: "Social Issues",
    18: "Sports",
    19: "Technology",
    20: "Transport",
    21: "Travel",
}

#: Fallback when the model's suggestion cannot be parsed: "Graphic Resources"
#: is the safest neutral bucket for abstract AI output.
DEFAULT_CATEGORY = 8

#: Map the model's free-text category name onto a numeric code.
_NAME_ALIASES: dict[str, int] = {
    "animal": 1,
    "animals": 1,
    "wildlife": 1,
    "architecture": 2,
    "building": 2,
    "buildings": 2,
    "business": 3,
    "corporate": 3,
    "drink": 4,
    "drinks": 4,
    "beverage": 4,
    "environment": 5,
    "nature": 5,
    "states of mind": 6,
    "emotion": 6,
    "abstract": 6,
    "food": 7,
    "graphic resources": 8,
    "background": 8,
    "texture": 8,
    "hobbies and leisure": 9,
    "leisure": 9,
    "hobby": 9,
    "industry": 10,
    "industrial": 10,
    "landscape": 11,
    "landscapes": 11,
    "lifestyle": 12,
    "people": 13,
    "person": 13,
    "portrait": 13,
    "plants and flowers": 14,
    "plant": 14,
    "flower": 14,
    "floral": 14,
    "culture and religion": 15,
    "culture": 15,
    "religion": 15,
    "science": 16,
    "social issues": 17,
    "sports": 18,
    "sport": 18,
    "technology": 19,
    "tech": 19,
    "transport": 20,
    "transportation": 20,
    "vehicle": 20,
    "travel": 21,
    "tourism": 21,
}


def resolve_category(value: object, default: int = DEFAULT_CATEGORY) -> int:
    """Coerce a model-provided category into a valid Adobe numeric code.

    Accepts an int, a numeric string, or a free-text name. Anything
    unrecognised falls back to ``default`` rather than producing an invalid CSV.
    """
    if value is None:
        return default

    if isinstance(value, bool):  # bool is an int subclass; reject explicitly
        return default

    if isinstance(value, (int, float)):
        code = int(value)
        return code if code in CATEGORY_CODES else default

    text = str(value).strip().lower()
    if not text:
        return default

    # A bare number, possibly embedded in prose like "Category 13".
    digits = "".join(ch for ch in text if ch.isdigit())
    if digits and len(digits) <= 2:
        code = int(digits)
        if code in CATEGORY_CODES:
            return code

    if text in _NAME_ALIASES:
        return _NAME_ALIASES[text]

    for alias, code in _NAME_ALIASES.items():
        if alias in text:
            return code

    return default


def category_name(code: int) -> str:
    """Human-readable name for a category code."""
    return CATEGORY_CODES.get(code, "Graphic Resources")


def all_categories() -> list[dict]:
    """Full category list for the frontend picker."""
    return [{"code": code, "name": name} for code, name in CATEGORY_CODES.items()]
