"""Post-processing of a saved .docx: Word-style paragraph IDs and a byte-deterministic zip.

python-docx writes no ``w14:paraId``/``w14:textId`` and stamps the zip entries with the current
time. Word writes both IDs on every paragraph. :func:`finalize` adds them, together with the
``w14``/``mc`` namespace declarations and the ``mc:Ignorable`` entry, to every part that holds
paragraphs (body, headers, footers). It also fixes the ``docProps/core.xml`` dates and author
and every zip entry's timestamp, so two builds of the corpus are byte-identical.
"""

import hashlib
import io
import re
import zipfile

from lxml import etree

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
W14 = "http://schemas.microsoft.com/office/word/2010/wordml"
MC = "http://schemas.openxmlformats.org/markup-compatibility/2006"
CP = "http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
DC = "http://purl.org/dc/elements/1.1/"
DCTERMS = "http://purl.org/dc/terms/"
XSI = "http://www.w3.org/2001/XMLSchema-instance"

FIXED_DATE = "2026-09-01T08:00:00Z"
FIXED_ZIP_TIME = (2026, 9, 1, 8, 0, 0)
AUTHOR = "Assistant Prof (corpus synthétique)"

STORY_PART = re.compile(r"^word/(document|header\d+|footer\d+)\.xml$")
"""Parts that hold paragraphs in the T-005a corpus."""

MAX_ID = 0x7FFFFFFF
"""Word requires paragraph IDs below 0x80000000; 0 is not used."""

PARA_ID = f"{{{W14}}}paraId"
TEXT_ID = f"{{{W14}}}textId"
IGNORABLE = f"{{{MC}}}Ignorable"


class IdAllocator:
    """Deterministic 8-hex IDs in ``00000001`` to ``7FFFFFFF``, unique within one document."""

    def __init__(self, seed: str) -> None:
        self._seed = seed
        self._used: set[int] = set()

    def allocate(self, key: str) -> str:
        """Return the ID for ``key``; on collision, the next free value."""
        digest = hashlib.sha256(f"{self._seed}\0{key}".encode()).digest()
        value = int.from_bytes(digest[:4], "big") % MAX_ID + 1
        while value in self._used:
            value = value % MAX_ID + 1
        self._used.add(value)
        return f"{value:08X}"


def _serialize(root: etree._Element) -> bytes:
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def _declare_word2010(root: etree._Element) -> etree._Element:
    """Return ``root``, or a copy of it declaring ``w14`` and ``mc``, with ``w14`` ignorable.

    lxml cannot add a namespace declaration to an existing element: when one is missing, the
    root is rebuilt with the extended map and the children are moved into it.
    """
    nsmap: dict[str, str] = {}
    for prefix, uri in root.nsmap.items():
        if prefix is None:  # WordprocessingML parts always use prefixes
            raise ValueError(f"unexpected default namespace {uri} on {root.tag}")
        nsmap[prefix] = uri
    missing = {
        prefix: uri for prefix, uri in (("w14", W14), ("mc", MC)) if uri not in nsmap.values()
    }
    if missing:
        rebuilt = etree.Element(root.tag, nsmap=nsmap | missing)
        for name, value in root.items():
            rebuilt.set(name, value)
        rebuilt.text = root.text
        rebuilt.extend(list(root))
        root = rebuilt
        nsmap |= missing
    w14_prefix = next(prefix for prefix, uri in nsmap.items() if uri == W14)
    prefixes = (root.get(IGNORABLE) or "").split()
    if w14_prefix not in prefixes:
        root.set(IGNORABLE, " ".join([*prefixes, w14_prefix]))
    return root


def add_word_ids(xml: bytes, *, part: str, ids: IdAllocator) -> bytes:
    """Set ``w14:paraId``/``w14:textId`` on every paragraph of a part, as Word does."""
    root = _declare_word2010(etree.fromstring(xml))
    for index, paragraph in enumerate(root.iter(f"{{{W}}}p")):
        paragraph.set(PARA_ID, ids.allocate(f"{part}#{index}:para"))
        paragraph.set(TEXT_ID, ids.allocate(f"{part}#{index}:text"))
    return _serialize(root)


def fix_core_properties(xml: bytes) -> bytes:
    """Replace the creation/modification dates and authors with fixed values."""
    root = etree.fromstring(xml)
    fixed = {
        f"{{{DC}}}creator": AUTHOR,
        f"{{{CP}}}lastModifiedBy": AUTHOR,
        f"{{{CP}}}revision": "1",
        f"{{{DCTERMS}}}created": FIXED_DATE,
        f"{{{DCTERMS}}}modified": FIXED_DATE,
    }
    for tag, value in fixed.items():
        element = root.find(tag)
        if element is None:
            element = etree.SubElement(root, tag)
            if tag.startswith(f"{{{DCTERMS}}}"):
                element.set(f"{{{XSI}}}type", "dcterms:W3CDTF")
        element.text = value
    return _serialize(root)


def _fixed_info(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, date_time=FIXED_ZIP_TIME)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.create_system = 0  # ZipInfo defaults to the running OS, which would differ in CI
    info.external_attr = 0
    return info


def finalize(docx: bytes, *, seed: str, word_ids: bool) -> bytes:
    """Return ``docx`` rewritten deterministically, with Word-style IDs if ``word_ids``.

    Entry order is kept. ``seed`` (the file name) makes IDs differ between documents.
    """
    ids = IdAllocator(seed)
    out = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(docx)) as source, zipfile.ZipFile(out, "w") as target:
        for info in source.infolist():
            data = source.read(info)
            if word_ids and STORY_PART.match(info.filename):
                data = add_word_ids(data, part=info.filename, ids=ids)
            elif info.filename == "docProps/core.xml":
                data = fix_core_properties(data)
            target.writestr(_fixed_info(info.filename), data)
    return out.getvalue()
