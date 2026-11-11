"""A small alpha-beta chess engine with a CLI for playing and analysis."""

from .engine import Engine, SearchResult
from .evaluation import evaluate

__all__ = ["Engine", "SearchResult", "evaluate"]
