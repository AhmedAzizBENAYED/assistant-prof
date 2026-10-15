from pathlib import Path

import pytest
from corpus_gen.build import build_corpus


@pytest.fixture(scope="session")
def fresh_corpus(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The corpus built from the current generator into a temporary directory."""
    out_dir = tmp_path_factory.mktemp("corpus")
    build_corpus(out_dir)
    return out_dir
