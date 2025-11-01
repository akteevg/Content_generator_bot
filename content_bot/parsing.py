"""Utilities for parsing AI responses."""

from __future__ import annotations

import json
import re
from typing import List

from .state import Idea


class IdeaParsingError(RuntimeError):
    """Raised when the response with ideas cannot be interpreted."""


def _extract_json_array(raw: str) -> str | None:
    match = re.search(r"\[.*\]", raw, flags=re.DOTALL)
    if not match:
        return None
    return raw[match.start(): match.end()]


def parse_ideas(raw: str) -> List[Idea]:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        extracted = _extract_json_array(raw)
        if not extracted:
            raise IdeaParsingError("Ответ с идеями не является валидным JSON")
        try:
            payload = json.loads(extracted)
        except json.JSONDecodeError as exc:
            raise IdeaParsingError("Ответ с идеями не является валидным JSON") from exc

    if not isinstance(payload, list):
        raise IdeaParsingError("Ожидался JSON-массив с идеями")

    ideas: List[Idea] = []
    for index, item in enumerate(payload, start=1):
        if not isinstance(item, dict):
            raise IdeaParsingError(f"Элемент №{index} не является объектом")
        title = item.get("title")
        description = item.get("description")
        if not title or not description:
            raise IdeaParsingError(f"У идеи №{index} отсутствуют необходимые поля")
        ideas.append(Idea(title=str(title).strip(), description=str(description).strip()))

    if len(ideas) < 1:
        raise IdeaParsingError("AI не вернул ни одной идеи")

    return ideas

