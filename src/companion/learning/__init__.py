"""Learning package reserved for M3."""

from companion.learning.context import LearningContextBuilder
from companion.learning.errors import (
    LearningItemNotDueError,
    LearningItemNotFoundError,
    ReviewInputLanguageError,
)
from companion.learning.repository import LearningRepository
from companion.learning.schemas import (
    LearningErrorType,
    LearningItemSchema,
    LearningKind,
    LearningSignalCandidate,
    LearningSignalConfidence,
    LearningSignalExtraction,
    LearningSignalObservation,
    LearningSignalReason,
    LearningSignalRequest,
    ReviewAnswerRequest,
    ReviewQuestion,
    ReviewResult,
)
from companion.learning.service import LearningService

__all__ = [
    "LearningItemNotDueError",
    "LearningItemNotFoundError",
    "ReviewInputLanguageError",
    "LearningContextBuilder",
    "LearningItemSchema",
    "LearningKind",
    "LearningErrorType",
    "LearningSignalCandidate",
    "LearningSignalConfidence",
    "LearningSignalExtraction",
    "LearningSignalObservation",
    "LearningSignalReason",
    "LearningSignalRequest",
    "LearningRepository",
    "LearningService",
    "ReviewAnswerRequest",
    "ReviewQuestion",
    "ReviewResult",
]
