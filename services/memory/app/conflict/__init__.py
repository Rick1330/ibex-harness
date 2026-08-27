"""Memory write-path temporal conflict detection (interval-first)."""

from app.conflict.classifier import ConflictClassifier, NoopConflictClassifier
from app.conflict.intervals import ValidityInterval, intervals_overlap
from app.conflict.service import ConflictService
from app.conflict.subjects import extract_subject_key, normalize_subject_key, subjects_match
from app.conflict.types import (
    CandidateMemory,
    ConflictDecision,
    ConflictEvaluation,
    ConflictOutcome,
    IncomingMemory,
    SupersedeApply,
)

__all__ = [
    "CandidateMemory",
    "ConflictClassifier",
    "ConflictDecision",
    "ConflictEvaluation",
    "ConflictOutcome",
    "ConflictService",
    "IncomingMemory",
    "NoopConflictClassifier",
    "SupersedeApply",
    "ValidityInterval",
    "extract_subject_key",
    "intervals_overlap",
    "normalize_subject_key",
    "subjects_match",
]
