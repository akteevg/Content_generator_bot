"""In-memory user state management for the bot."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class Idea:
    title: str
    description: str


@dataclass
class UserState:
    step: str = "waiting_niche"
    niche: Optional[str] = None
    goal: Optional[str] = None
    content_format: Optional[str] = None
    ideas: List[Idea] = field(default_factory=list)
    selected_index: Optional[int] = None


class StateManager:
    def __init__(self) -> None:
        self._storage: Dict[int, UserState] = {}

    def get(self, user_id: int) -> UserState:
        if user_id not in self._storage:
            self._storage[user_id] = UserState()
        return self._storage[user_id]

    def reset(self, user_id: int) -> UserState:
        self._storage[user_id] = UserState()
        return self._storage[user_id]

    def remove(self, user_id: int) -> None:
        self._storage.pop(user_id, None)

