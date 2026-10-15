"""Regenerate the synthetic test corpus (``just corpus``, T-005a, ADR-031, ADR-041).

Writes the .docx files and their README into ``corpus/docs/`` (or ``--out-dir``).
"""

import argparse
import sys
from pathlib import Path

from corpus_gen.build import build_corpus
from corpus_gen.paths import DOCS_DIR


def main(argv: list[str] | None = None) -> int:
    """Build the corpus and list the written files."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, default=DOCS_DIR)
    args = parser.parse_args(argv)
    for path in build_corpus(args.out_dir):
        sys.stdout.write(f"{path}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
