"""Locations of the corpus in the repository."""

from pathlib import Path

CORPUS_DIR = Path(__file__).resolve().parents[2]
DOCS_DIR = CORPUS_DIR / "docs"
INSTRUCTIONS = CORPUS_DIR / "instructions.yaml"
