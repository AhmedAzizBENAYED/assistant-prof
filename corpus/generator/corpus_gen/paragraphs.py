"""Every paragraph of a .docx, in document order, part by part."""

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import docx
from docx.opc.constants import CONTENT_TYPE as CT
from docx.opc.part import XmlPart
from docx.oxml.ns import qn
from docx.oxml.text.paragraph import CT_P
from docx.text.paragraph import Paragraph

STORY_CONTENT_TYPES = frozenset({CT.WML_DOCUMENT_MAIN, CT.WML_HEADER, CT.WML_FOOTER})


@dataclass(frozen=True)
class PartParagraph:
    """A paragraph and the package part holding it."""

    part: str
    text: str


def iter_paragraphs(path: Path) -> Iterator[PartParagraph]:
    """Yield every paragraph of body, headers and footers, including those in table cells.

    Text follows python-docx: a tab character for w:tab, a newline for w:br.
    """
    document = docx.Document(str(path))
    parts = sorted(
        (part for part in document.part.package.iter_parts() if isinstance(part, XmlPart)),
        key=lambda part: str(part.partname),
    )
    for part in parts:
        if part.content_type not in STORY_CONTENT_TYPES:
            continue
        for element in part.element.iter(qn("w:p")):
            paragraph = Paragraph(cast(CT_P, element), None)  # type: ignore[arg-type]
            yield PartParagraph(part=str(part.partname), text=paragraph.text)
