import logging
from typing import List, Tuple

import spacy

logger = logging.getLogger(__name__)

SPACY_LABEL_MAP = {
    "PERSON": "PERSON",
    "ORG": "ORG",
    "GPE": "GPE",
    "DATE": "DATE",
}


class NERService:
    """Extracts named entities from text using spaCy."""

    def __init__(self, model_name: str = "en_core_web_sm") -> None:
        self._nlp = spacy.load(
            model_name, disable=["tok2vec", "tagger", "parser",
                                  "attribute_ruler", "lemmatizer"]
        )

    def extract(self, text: str) -> List[Tuple[str, str]]:
        """Return deduplicated (name, entity_type) pairs from text.

        Only returns entities whose spaCy label maps to one of the
        supported ENTITY_TYPES (PERSON, ORG, GPE, DATE).
        Deduplicates by (lowered name, type) within a single text.
        """
        if not text or not text.strip():
            return []
        doc = self._nlp(text)
        seen = set()
        entities = []
        for ent in doc.ents:
            mapped_type = SPACY_LABEL_MAP.get(ent.label_)
            if mapped_type is None:
                continue
            name = ent.text.strip()
            if not name or len(name) < 2:
                continue
            key = (name.lower(), mapped_type)
            if key not in seen:
                seen.add(key)
                entities.append((name, mapped_type))
        return entities
