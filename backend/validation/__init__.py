"""Validation engine package: components A-G + persistence runner."""

from backend.validation.engine import (
    benchmark_delta,
    check_geometric,
    decide_overall_status,
    observation_consistency,
    reference_agreement,
    spatial_fidelity,
    spectral_fidelity,
    uncertainty_quality,
)

__all__ = [
    "benchmark_delta", "check_geometric", "decide_overall_status",
    "observation_consistency", "reference_agreement", "spatial_fidelity",
    "spectral_fidelity", "uncertainty_quality",
]
