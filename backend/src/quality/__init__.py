"""Report quality gate: read-only checks over an existing research run."""
from __future__ import annotations

from .engine import audit
from .parse import extract_citations, merge_sources, parse_sources, split_sections
from .render import render_quality_report, render_references

__all__ = [
    "audit",
    "extract_citations",
    "merge_sources",
    "parse_sources",
    "split_sections",
    "render_quality_report",
    "render_references",
]
