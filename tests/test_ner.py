import pytest

spacy = pytest.importorskip("spacy")

from services.ner import NERService


@pytest.fixture(scope="module")
def ner():
    return NERService()


def test_extract_person_and_org(ner):
    entities = ner.extract("Tara met with Google engineers in Mountain View.")
    names = {name for name, _ in entities}
    types = {etype for _, etype in entities}
    assert "PERSON" in types
    assert "Tara" in names or any("tara" in n.lower() for n in names)


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
