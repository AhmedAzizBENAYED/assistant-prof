from collections import Counter
from functools import cache
from typing import Any

import pytest
from corpus_gen.documents import CORPUS
from corpus_gen.instructions import (
    Instruction,
    InstructionSet,
    Target,
    load_instructions,
    normalize_text,
)
from corpus_gen.paragraphs import iter_paragraphs
from corpus_gen.paths import DOCS_DIR, INSTRUCTIONS
from pydantic import ValidationError

INSTRUCTION_SET = load_instructions(INSTRUCTIONS)
CORPUS_NAMES = {entry.name for entry in CORPUS}


@cache
def normalized_paragraphs(name: str) -> tuple[str, ...]:
    return tuple(normalize_text(p.text) for p in iter_paragraphs(DOCS_DIR / name))


def text_targets(instruction: Instruction) -> list[str]:
    targets = [*instruction.selection, *instruction.expected.targets]
    return [target.text for target in targets if target.text is not None]


def test_instruction_file_size_and_coverage() -> None:
    instructions = INSTRUCTION_SET.instructions
    assert len(instructions) >= 30
    categories = Counter(instruction.category for instruction in instructions)
    assert set(categories) == {"formatting", "rewording", "generation", "creation", "question"}
    tags = Counter(tag for instruction in instructions for tag in instruction.tags)
    assert tags["hurried"] >= 5
    assert tags["near_miss"] >= 3
    assert sum(instruction.expected.fast_path for instruction in instructions) >= 6


@pytest.mark.parametrize("instruction", INSTRUCTION_SET.instructions, ids=lambda i: i.id)
def test_document_is_in_the_corpus(instruction: Instruction) -> None:
    assert instruction.document in CORPUS_NAMES


@pytest.mark.parametrize("instruction", INSTRUCTION_SET.instructions, ids=lambda i: i.id)
def test_every_text_target_matches_exactly_one_paragraph(instruction: Instruction) -> None:
    paragraphs = normalized_paragraphs(instruction.document)
    for excerpt in text_targets(instruction):
        needle = normalize_text(excerpt)
        matches = [text for text in paragraphs if needle in text]
        assert len(matches) == 1, f"{excerpt!r} matches {len(matches)} paragraphs"


# --- normalisation -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "normalized"),
    [
        ("Nom\u00a0: Ali", "Nom : Ali"),
        ("Bon courage\u202f!", "Bon courage !"),
        ("l\u2019auxiliaire", "l'auxiliaire"),
        ("  a\tb\n\nc  ", "a b c"),
        ("e\u0301te\u0301", "été"),  # decomposed accents → NFC
        ("«\u00a0que\u00a0»", "« que »"),
    ],
)
def test_normalize_text(raw: str, normalized: str) -> None:
    assert normalize_text(raw) == normalized


def test_normalize_text_is_case_sensitive_and_idempotent() -> None:
    assert normalize_text("Exercice") != normalize_text("exercice")
    once = normalize_text(" Dictée\u202f: l\u2019automne ")
    assert normalize_text(once) == once


# --- schema failures -----------------------------------------------------------------------------


def make(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": "I-999",
        "category": "formatting",
        "document": "01-styled-exam.docx",
        "instruction": "Mets les consignes en gras.",
        "expected": {"intent": "edit", "operations": ["set_font"], "fast_path": True},
    }
    return base | overrides


def test_valid_minimal_instruction() -> None:
    assert Instruction.model_validate(make()).expected.fast_path


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"id": "1"}, "String should match pattern"),
        ({"category": "layout"}, "Input should be"),
        ({"instruction": "  "}, "at least 1 character"),
        ({"surprise": 1}, "Extra inputs are not permitted"),
        (
            {"expected": {"intent": "edit", "operations": ["make_bold"]}},
            "Input should be",
        ),
        ({"expected": {"intent": "edit", "operations": []}}, "at least one operation"),
        (
            {"expected": {"intent": "edit", "operations": ["rewrite"], "fast_path": True}},
            "only builds simple formatting",
        ),
        (
            {
                "category": "rewording",
                "expected": {"intent": "edit", "operations": ["set_font"], "fast_path": True},
            },
            "only formatting instructions",
        ),
        (
            {"category": "question", "expected": {"intent": "question", "operations": ["delete"]}},
            "a question changes nothing",
        ),
        ({"category": "question"}, "requires intent `question`"),
        ({"expected": {"intent": "question"}}, "requires category `question`"),
        (
            {
                "category": "creation",
                "expected": {"intent": "create", "targets": [{"role": "titre"}]},
            },
            "a creation builds a new document",
        ),
        ({"category": "creation"}, "requires intent `create`"),
        ({"expected": {"intent": "create"}}, "requires category `creation`"),
        (
            {"expected": {"intent": "edit", "operations": ["rewrite"], "answer_contains": "20"}},
            "only applies to questions",
        ),
        ({"tags": ["near_miss"]}, "a near miss"),
        ({"tags": ["sloppy"]}, "Input should be"),
        ({"selection": [{"role": "consigne"}]}, "by text only"),
    ],
)
def test_invalid_instruction(overrides: dict[str, Any], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        Instruction.model_validate(make(**overrides))


@pytest.mark.parametrize(
    ("target", "message"),
    [
        ({}, "either `text` or `role`"),
        ({"text": "Exercice 1", "role": "section"}, "either `text` or `role`"),
        ({"text": "Exercice 1", "ordinal": 1}, "only applies to a role"),
        ({"role": "section", "ordinal": 0}, "greater than or equal to 1"),
        ({"role": "chapitre"}, "Input should be"),
        ({"id": "1A2B3C4D"}, "Extra inputs are not permitted"),  # never a block ID
    ],
)
def test_invalid_target(target: dict[str, Any], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        Target.model_validate(target)


def test_duplicated_ids_are_rejected() -> None:
    with pytest.raises(ValidationError, match="duplicated instruction ids: I-999"):
        InstructionSet.model_validate({"version": 1, "instructions": [make(), make()]})
