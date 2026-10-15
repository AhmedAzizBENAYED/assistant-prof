import io
import zipfile

import pytest
from corpus_gen.logo import logo_png
from corpus_gen.package import (
    FIXED_DATE,
    IGNORABLE,
    MC,
    PARA_ID,
    TEXT_ID,
    W14,
    IdAllocator,
    W,
    add_word_ids,
    finalize,
    fix_core_properties,
)
from corpus_gen.typography import fr
from lxml import etree

BARE_HEADER = (
    f'<w:hdr xmlns:w="{W}" w:conformance="transitional"><w:p><w:r><w:t>a</w:t></w:r></w:p>'
    "<w:tbl><w:tr><w:tc><w:p/></w:tc></w:tr></w:tbl></w:hdr>"
).encode()


def test_ids_are_added_with_namespace_declarations() -> None:
    xml = add_word_ids(BARE_HEADER, part="word/header1.xml", ids=IdAllocator("x"))
    root = etree.fromstring(xml)
    assert root.nsmap["w14"] == W14
    assert root.nsmap["mc"] == MC
    assert root.get(IGNORABLE) == "w14"
    paragraphs = list(root.iter(f"{{{W}}}p"))
    assert len(paragraphs) == 2  # nested table paragraphs included
    assert all(p.get(PARA_ID) and p.get(TEXT_ID) for p in paragraphs)
    assert root.findtext(f".//{{{W}}}t") == "a"  # children kept
    assert root.get(f"{{{W}}}conformance") == "transitional"  # attributes kept


def test_existing_ignorable_list_is_extended_not_replaced() -> None:
    xml = (
        f'<w:document xmlns:w="{W}" xmlns:mc="{MC}" '
        f'xmlns:wp14="http://schemas.microsoft.com/office/word/2010/wordprocessingDrawing" '
        f'mc:Ignorable="wp14"><w:body><w:p/></w:body></w:document>'
    ).encode()
    root = etree.fromstring(add_word_ids(xml, part="word/document.xml", ids=IdAllocator("x")))
    assert root.get(IGNORABLE) == "wp14 w14"
    again = etree.fromstring(add_word_ids(etree.tostring(root), part="p", ids=IdAllocator("x")))
    assert again.get(IGNORABLE) == "wp14 w14"


def test_allocator_is_deterministic_and_skips_collisions() -> None:
    first, second = IdAllocator("seed"), IdAllocator("seed")
    assert first.allocate("k") == second.allocate("k")
    # The same key again collides with the first value: the next free value is used.
    assert int(first.allocate("k"), 16) == int(second.allocate("k"), 16)
    assert first.allocate("k") != second.allocate("j")
    assert IdAllocator("other").allocate("k") != IdAllocator("seed").allocate("k")


def test_allocator_never_repeats_and_stays_below_0x80000000() -> None:
    ids = IdAllocator("seed")
    values = {int(ids.allocate("same"), 16) for _ in range(50)}
    assert len(values) == 50
    assert all(0 < v <= 0x7FFFFFFF for v in values)


def test_core_properties_are_fixed_even_when_missing() -> None:
    xml = (
        b'<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/'
        b'metadata/core-properties"/>'
    )
    fixed = fix_core_properties(xml).decode()
    assert fixed.count(FIXED_DATE) == 2
    assert 'xsi:type="dcterms:W3CDTF"' in fixed


def test_finalize_without_ids_only_fixes_metadata() -> None:
    source = io.BytesIO()
    with zipfile.ZipFile(source, "w") as package:
        package.writestr("word/document.xml", BARE_HEADER)
        package.writestr("docProps/core.xml", b'<cp:coreProperties xmlns:cp="urn:x"/>')
    result = finalize(source.getvalue(), seed="s", word_ids=False)
    with zipfile.ZipFile(io.BytesIO(result)) as package:
        assert package.read("word/document.xml") == BARE_HEADER
        assert [i.create_system for i in package.infolist()] == [0, 0]
    assert result == finalize(source.getvalue(), seed="s", word_ids=False)


def test_logo_is_a_png() -> None:
    png = logo_png()
    assert png.startswith(b"\x89PNG\r\n\x1a\n")
    assert png == logo_png()


@pytest.mark.parametrize(
    ("plain", "typographic"),
    [
        ("Nom : Ali", "Nom\u00a0: Ali"),
        ("Pourquoi ? Parce que ! Oui ; non", "Pourquoi\u202f? Parce que\u202f! Oui\u202f; non"),
        ("l'école", "l\u2019école"),
        ("« que »", "«\u00a0que\u00a0»"),
    ],
)
def test_french_typography(plain: str, typographic: str) -> None:
    assert fr(plain) == typographic


def test_default_namespace_is_refused() -> None:
    xml = f'<document xmlns="{W}"><p/></document>'.encode()
    with pytest.raises(ValueError, match="unexpected default namespace"):
        add_word_ids(xml, part="word/document.xml", ids=IdAllocator("x"))
