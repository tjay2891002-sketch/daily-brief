"""Importing this package registers all built-in adapters."""
from . import reddit, rss, youtube  # noqa: F401  (side effect: register adapters)
from .base import REGISTRY, get_adapter  # noqa: F401

__all__ = ["REGISTRY", "get_adapter", "reddit", "rss", "youtube"]
