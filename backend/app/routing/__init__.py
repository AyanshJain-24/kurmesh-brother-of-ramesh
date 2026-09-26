"""Deterministic, evidence-bound prototype route generation.

This package creates route *candidates* only.  It never selects, approves, or
executes a route.
"""

from .generator import ALGORITHM_VERSION, build_candidate_paths, distance_nm

__all__ = ["ALGORITHM_VERSION", "build_candidate_paths", "distance_nm"]
