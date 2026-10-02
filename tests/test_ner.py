import sys

# Remove conftest stubs so real spaCy and services.ner are used
for _mod in list(sys.modules):
    if _mod in ("spacy",) or _mod.startswith(("spacy.", "services.ner")):
        del sys.modules[_mod]

import pytest

spacy = pytest.importorskip("spacy")

from services.ner import NERService, title_to_text


@pytest.fixture(scope="module")
def ner():
    return NERService()


def test_extract_person_and_org(ner):
    entities = ner.extract("Barack Obama visited Google headquarters in Mountain View.")
    names = {name for name, _ in entities}
    types = {etype for _, etype in entities}
    assert "PERSON" in types
    assert "Barack Obama" in names


def test_extract_gpe(ner):
    entities = ner.extract("The conference is in Tokyo, Japan.")
    types = {etype for _, etype in entities}
    assert "GPE" in types


def test_extract_filters_unsupported_labels(ner):
    entities = ner.extract("The price was $500 million.")
    types = {etype for _, etype in entities}
    assert "MONEY" not in types


def test_extract_deduplicates_within_text(ner):
    entities = ner.extract("Tara called Tara and Tara answered.")
    tara_count = sum(1 for name, _ in entities if name.lower() == "tara")
    assert tara_count <= 1


def test_extract_empty_text(ner):
    assert ner.extract("") == []
    assert ner.extract("   ") == []


def test_extract_date(ner):
    entities = ner.extract("The meeting is on January 15, 2026.")
    types = {etype for _, etype in entities}
    assert "DATE" in types


def test_extract_skips_short_names(ner):
    entities = ner.extract("X and Y met at the park.")
    names = {name for name, _ in entities}
    assert not any(len(n) < 2 for n in names)


@pytest.mark.parametrize("title, expected", [
    ("Noosh Noshery - Menu - Mountain View - Yelp", "Noosh Noshery. Menu. Mountain View"),
    ("Best hikes near Santa Cruz | AllTrails", "Best hikes near Santa Cruz"),
    ("Priya Sharma — Google · LinkedIn", "Priya Sharma. Google"),
    ("Just one part", "Just one part"),
    ("well-known e-mail tips", "well-known e-mail tips"),  # hyphens inside words aren't separators
])
def test_title_to_text_splits_parts_and_drops_site_name(title, expected):
    assert title_to_text(title) == expected


def test_title_source_separates_title_parts(ner):
    entities = ner.extract("Noosh Noshery - Menu - Mountain View - Yelp", source="title")
    names = {name for name, _ in entities}
    assert not any("Yelp" in n or "Menu" in n for n in names)


def test_lowercase_and_url_like_hits_are_dropped(ner):
    for name, _ in ner.extract("Order from Trader Joe's arrives Wednesday. See www.example.com for details."):
        assert name != name.lower() or _ == "DATE"
        assert "www." not in name and ".com" not in name
