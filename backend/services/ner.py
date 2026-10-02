import logging
import os
import re
from typing import List, Tuple

import spacy

logger = logging.getLogger(__name__)

DEFAULT_MODEL = os.environ.get("NER_MODEL", "en_core_web_sm")

SPACY_LABEL_MAP = {
    "PERSON": "PERSON",
    "ORG": "ORG",
    "GPE": "GPE",
    "DATE": "DATE",
}

# Page titles join their parts with separators ("Noosh Noshery - Menu - Yelp");
# spaCy reads the whole run as one entity unless the parts are split.
TITLE_SEPARATOR = re.compile(r"\s+[-|–—·:]\s+")
URL_FRAGMENT = re.compile(r"https?:|www\.|\.(com|org|net|io|edu)\b", re.IGNORECASE)


def title_to_text(title: str) -> str:
    """Turn a page title into sentences NER handles: split on separators and
    drop the trailing site name ("Yelp", "LinkedIn", "Google Search")."""
    parts = [p.strip() for p in TITLE_SEPARATOR.split(title) if p.strip()]
    if len(parts) > 1:
        parts = parts[:-1]
    return ". ".join(parts)


class NERService:
    """Extracts named entities from text using spaCy."""

    def __init__(self, model_name: str = DEFAULT_MODEL) -> None:
        self._nlp = spacy.load(
            model_name, disable=["tok2vec", "tagger", "parser",
                                  "attribute_ruler", "lemmatizer"]
        )

    def extract(self, text: str, source: str = "text") -> List[Tuple[str, str]]:
        """Return deduplicated (name, entity_type) pairs from text.

        Only returns entities whose spaCy label maps to one of the
        supported ENTITY_TYPES (PERSON, ORG, GPE, DATE).
        Deduplicates by (lowered name, type) within a single text.
        Pass source="title" for a browser page title.
        """
        if not text or not text.strip():
            return []
        if source == "title":
            text = title_to_text(text)
        doc = self._nlp(text)
        seen = set()
        entities = []
        for ent in doc.ents:
            mapped_type = SPACY_LABEL_MAP.get(ent.label_)
            if mapped_type is None:
                continue
            name = ent.text.strip()
            if not name or len(name) < 2 or not _plausible(name, mapped_type):
                continue
            key = (name.lower(), mapped_type)
            if key not in seen:
                seen.add(key)
                entities.append((name, mapped_type))
        return entities


def _plausible(name: str, entity_type: str) -> bool:
    # Names, organizations and places are capitalized; an all-lowercase hit
    # ("order", "menu") is a misfire. Dates ("next tuesday") may be lowercase.
    if entity_type != "DATE" and name == name.lower():
        return False
    return not URL_FRAGMENT.search(name)
