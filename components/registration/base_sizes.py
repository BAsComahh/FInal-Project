"""Resolve KoW v4 PDF profiles against the pinned official footprint matrix."""

from math import isfinite
import re


FAQ_URL = "https://www.manticgames.com/wp-content/uploads/2026/02/KoW-v4-FAQ-v1.0.pdf"
# FAQ's printed revision is v0.1; columns are Single Model, Troop, Regiment, Horde.
FOOTPRINTS = {
    "Infantry": ((40, 40), (100, 40), (100, 80), (200, 80)),
    "Infantry (Heavy)": ((40, 40), (125, 50), (125, 100), (250, 100)),
    "Large Infantry": ((40, 40), (120, 40), (120, 80), (240, 80)),
    "Large Infantry (Monstrous)": ((50, 50), (150, 50), (150, 100), (300, 100)),
    "Cavalry": ((50, 50), (125, 50), (125, 100), (250, 100)),
    "Large Cavalry": ((50, 50), (150, 50), (150, 100), (300, 100)),
    "Chariot": ((50, 100), None, (150, 100), None),
    "Monster": ((50, 50), None, None, None),
    "Monster (Titan)": ((75, 75), None, None, None),
}
_ALIASES = {
    alias: category for category, aliases in (
        ("Infantry", "inf|infantry"),
        ("Infantry (Heavy)", "hvyinf|heavyinf|heavyinfantry|infhvy|infheavy|infantryheavy"),
        ("Large Infantry", "lrginf|largeinf|largeinfantry"),
        ("Large Infantry (Monstrous)", "moninf|monstrousinf|monstrousinfantry|lrginfmonstrous|largeinfantrymonstrous"),
        ("Cavalry", "cav|cavalry"),
        ("Large Cavalry", "lrgcav|largecav|largecavalry"),
        ("Chariot", "cht|chariot|chariots"),
        ("Monster", "mon|monster"),
        ("Monster (Titan)", "titan|montitan|monstertitan"),
    ) for alias in aliases.split("|")
}
_SIZE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:mm\s*)?(?:[x×]\s*(\d+(?:\.\d+)?)\s*)?mm", re.I)
_NOTE = re.compile(r"\b(?:base(?:\s+size)?|(?:unit\s+)?footprint)\s*[:=(]\s*(.*?)\)?$", re.I)
_REVERSE_NOTE = re.compile(r"(?:mounted on (?:an? )?)?(\d.*?)\s+(?:square\s+)?base", re.I)


def infer_dimensions(classification, formation, details):
    """Return editable dimensions and separate evidence of their import value.

    Only explicit mm declarations and known profile categories are resolved.
    An unrecognised base note blocks the standard fallback, rather than hiding
    a possible exception behind an otherwise valid parent category.
    """
    evidence = {"classification": classification, "formation": formation}
    notes, sizes = [], set()
    invalid_note = False
    for raw in details:
        text = " ".join(raw.split())
        for clause in re.split(r",|\b(?:Special Rules|Traits):\s*", text, flags=re.I):
            clause = clause.strip().rstrip(".")
            note = _NOTE.search(clause) or _REVERSE_NOTE.fullmatch(clause)
            if note is None and not re.search(r"\b(?:base size|footprint)\b", clause, re.I):
                continue
            notes.append(note[0] if note else clause)
            size = _SIZE.fullmatch(note[1].strip()) if note else None
            if size is None:
                invalid_note = True
                continue
            width, depth = float(size[1]), float(size[2] or size[1])
            if not all(isfinite(value) and value > 0 for value in (width, depth)):
                invalid_note = True
                continue
            sizes.add((width, depth))
    value = None
    if notes:
        evidence.update(notes=notes, method="pdf_explicit")
        if not invalid_note and len(sizes) == 1:
            value = next(iter(sizes))
        else:
            evidence["reason"] = "Unsupported or conflicting base-size notes; provide an explicit size in the type catalog."
    else:
        category = re.sub(r"^(?:(?:core|aux(?:iliary)?|support|specialist|champion|warlord|commander)\b\s*(?:\(aux\))?\s*)+",
                          "", classification, flags=re.I)
        category = re.sub(r"\b(?:Troop|Regiment|Horde|Legion|Single(?: Model)?)\s*$", "", category, flags=re.I)
        category = re.sub(r"^Hero\b\s*|\s+\bHero$", "", category, flags=re.I)
        category = _ALIASES.get(re.sub(r"[\s().-]", "", category).casefold())
        column = {"Single": 0, "Hero": 0, "Troop": 1, "Regiment": 2, "Horde": 3}.get(formation)
        if category is not None and column is not None:
            value = FOOTPRINTS[category][column]
        evidence.update(method="rules_standard", unit_type=category, rules_url=FAQ_URL,
                        rules_revision="KoW v4 FAQ v0.1", page=1)
        if value is None:
            evidence["reason"] = "No supported standard footprint for this category and formation; provide an explicit size in the type catalog."
    if value is None:
        evidence["method"] = "unresolved"
        return {"dimension_inference": evidence}
    dimension = dict(width_mm=value[0], depth_mm=value[1])
    evidence.update(dimension)
    return {"dimension": dimension, "dimension_inference": evidence}
