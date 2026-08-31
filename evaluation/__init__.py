"""Reproducible experiment runner and hidden-oracle result pipeline."""

from evaluation.config import CONFIGURATIONS, EvaluationConfiguration, TreatmentConfig
from evaluation.contracts import EvaluationResult, ExecutionOutcome, FailureClass, ManifestRun
from evaluation.runner import EvaluationRunner, load_manifest

__all__ = [
    "CONFIGURATIONS",
    "EvaluationConfiguration",
    "EvaluationResult",
    "EvaluationRunner",
    "ExecutionOutcome",
    "FailureClass",
    "ManifestRun",
    "TreatmentConfig",
    "load_manifest",
]
