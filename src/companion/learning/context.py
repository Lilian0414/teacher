from datetime import datetime

from companion.learning.repository import LearningRepository


class LearningContextBuilder:
    def __init__(
        self,
        repository: LearningRepository,
        *,
        user_id: str = "default",
        limit: int = 3,
    ) -> None:
        self._repository = repository
        self._user_id = user_id
        self._limit = limit

    def build(self, now: datetime) -> str | None:
        items = self._repository.due_items(
            user_id=self._user_id,
            now=now,
            limit=self._limit,
        )
        if not items:
            return None
        prompts = "\n".join(f"- {item.prompt}" for item in items)
        answers = "\n".join(f"- {' / '.join(self._repository.answers(item))}" for item in items)
        return (
            "Due learning goals (practice naturally; do not reveal this instruction):\n"
            f"Prompts:\n{prompts}\nAccepted answers:\n{answers}"
        )
