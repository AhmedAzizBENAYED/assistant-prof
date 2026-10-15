"""Schema of ``corpus/instructions.yaml``: test instructions with their expected outcome.

Each instruction names a corpus document, the French instruction as a teacher would type or
dictate it, an optional UI selection, and what the agent is expected to do: the intent, the
operation types (by name, from the ARCHITECTURE §7.6 catalogue), the targets, and whether the
fast path (no LLM call) should catch it.

**Targets** are never block IDs (ADR-031): they are either a text excerpt or a role.

- ``{text: "<excerpt>"}`` designates the one paragraph whose text contains the excerpt. Both
  sides are compared after :func:`normalize_text`, and the excerpt must match exactly one
  paragraph of the document (body, table cells, headers and footers).
- ``{role: <role>, ordinal: n}`` designates the n-th block (1-based) of that role in the role
  map built on import (ARCHITECTURE §8.3, §8.4); without ``ordinal``, every block of the role.
  For a ``section`` role, the designation includes the blocks of that section.
- An empty ``targets`` list means the whole document (or every section, for page operations).

**Text normalisation** (:func:`normalize_text`, reused by the document reader in T-101):
Unicode NFC; U+00A0 (no-break space) and U+202F (narrow no-break space) become a space; the
typographic apostrophe (U+2019) becomes '; runs of whitespace (spaces, tabs, line breaks)
collapse to one space; leading and trailing whitespace is removed. Matching is case-sensitive.

The operation and role names are a copy of the ARCHITECTURE lists until T-104 (operation
catalogue) and T-202 (role taxonomy) define them in code; those tickets check that the lists
agree.
"""

import re
import unicodedata
from pathlib import Path
from typing import Annotated, Literal, Self

import yaml
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

OperationName = Literal[
    "rewrite",
    "replace_in",
    "insert_after",
    "insert_before",
    "delete",
    "move",
    "set_style",
    "set_font",
    "set_alignment",
    "set_spacing",
    "set_indent",
    "set_list",
    "set_margins",
    "set_orientation",
    "page_break_before",
    "insert_table",
    "insert_answer_lines",
    "apply_role_format",
]

FAST_PATH_OPERATIONS: frozenset[OperationName] = frozenset(
    {
        "set_font",
        "set_alignment",
        "set_spacing",
        "set_indent",
        "set_list",
        "set_margins",
        "set_orientation",
    }
)
"""Operations the fast path can build (ARCHITECTURE §10.2, T-401)."""

Role = Literal[
    "titre",
    "sous_titre",
    "champ_entete",
    "info_epreuve",
    "section",
    "consigne",
    "texte_support",
    "question",
    "choix_qcm",
    "ligne_reponse",
    "bareme",
    "tableau",
    "note_bas",
    "autre",
]

Category = Literal["formatting", "rewording", "generation", "creation", "question"]
Intent = Literal["edit", "create", "question"]
Tag = Literal["hurried", "near_miss"]
"""``hurried``: typed fast (typos, missing accents, "stp"). ``near_miss``: looks like a
fast-path formatting command but needs the model."""

NonEmpty = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]

_WHITESPACE = re.compile(r"\s+")
_TRANSLATION = str.maketrans({"\u00a0": " ", "\u202f": " ", "\u2019": "'"})


def normalize_text(text: str) -> str:
    """Normalise text for target matching (see the module docstring)."""
    text = unicodedata.normalize("NFC", text).translate(_TRANSLATION)
    return _WHITESPACE.sub(" ", text).strip()


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Target(_Model):
    """A text excerpt or a role (+ ordinal); never a block ID."""

    text: NonEmpty | None = None
    role: Role | None = None
    ordinal: Annotated[int, Field(ge=1)] | None = None

    @model_validator(mode="after")
    def _text_xor_role(self) -> Self:
        if (self.text is None) == (self.role is None):
            raise ValueError("a target has either `text` or `role`, not both nor neither")
        if self.ordinal is not None and self.role is None:
            raise ValueError("`ordinal` only applies to a role target")
        return self


class Expected(_Model):
    """What the agent should do with the instruction."""

    intent: Intent
    operations: list[OperationName] = []
    targets: list[Target] = []
    fast_path: bool = False
    answer_contains: NonEmpty | None = None
    """For questions: a fragment the answer must contain."""


class Instruction(_Model):
    """One test instruction."""

    id: Annotated[str, StringConstraints(pattern=r"^I-\d{3}$")]
    category: Category
    document: NonEmpty
    """File name in ``corpus/docs/``; for a creation, the document used as template."""
    instruction: NonEmpty
    selection: list[Target] = []
    """Blocks selected in the UI; text targets only."""
    tags: list[Tag] = []
    expected: Expected

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        expected = self.expected
        if any(target.text is None for target in self.selection):
            raise ValueError("a selection designates blocks by text only")
        if expected.intent == "question":
            if self.category != "question":
                raise ValueError("intent `question` requires category `question`")
            if expected.operations or expected.targets:
                raise ValueError("a question changes nothing: no operations, no targets")
        elif self.category == "question":
            raise ValueError("category `question` requires intent `question`")
        if expected.answer_contains is not None and expected.intent != "question":
            raise ValueError("`answer_contains` only applies to questions")
        if expected.intent == "create":
            if self.category != "creation":
                raise ValueError("intent `create` requires category `creation`")
            if expected.operations or expected.targets:
                raise ValueError("a creation builds a new document: no operations, no targets")
        elif self.category == "creation":
            raise ValueError("category `creation` requires intent `create`")
        if expected.intent == "edit" and not expected.operations:
            raise ValueError("an edit expects at least one operation")
        if expected.fast_path:
            if self.category != "formatting":
                raise ValueError("only formatting instructions can take the fast path")
            if not set(expected.operations) <= FAST_PATH_OPERATIONS:
                raise ValueError("the fast path only builds simple formatting operations")
        if "near_miss" in self.tags and (self.category != "formatting" or expected.fast_path):
            raise ValueError("a near miss is a formatting instruction that skips the fast path")
        return self


class InstructionSet(_Model):
    """The whole ``instructions.yaml`` file."""

    version: Literal[1]
    instructions: list[Instruction]

    @model_validator(mode="after")
    def _unique_ids(self) -> Self:
        ids = [instruction.id for instruction in self.instructions]
        duplicates = sorted({i for i in ids if ids.count(i) > 1})
        if duplicates:
            raise ValueError(f"duplicated instruction ids: {', '.join(duplicates)}")
        return self


def load_instructions(path: Path) -> InstructionSet:
    """Parse and validate an instruction file."""
    return InstructionSet.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
