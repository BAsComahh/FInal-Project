"""Read text-based Mantic Companion army lists into registration type catalogs."""

from copy import deepcopy
import hashlib
from io import BytesIO
import json
from pathlib import Path
import re

from .units import UnitRoster


_HEADER = re.compile(r"^(?P<name>.+?)\s+Sp\s+Me\s+Sh\s+De\s+US\s+Att\s+Ne\s+Ht\s+Pts$")
_PROFILE = re.compile(
    r"^(?P<classification>.+?)\s+(?P<speed>\d+(?:\.\d+)?)\s+"
    r"(?P<melee>\d+\+|-)\s+(?P<shooting>\d+\+|-)\s+(?P<defence>\d+\+|-)\s+"
    r"(?P<strength>\d+)\s+(?P<attacks>\d+)\s+(?P<nerve>(?:\d+|-)(?:/(?:\d+|-))?)\s+"
    r"(?P<height>\d+)\s+\[(?P<points>\d+)\]$"
)
_OPTION = re.compile(r"^(?P<label>.+?)\s+\[(?P<points>\d+)\]$")
_WEAPON = re.compile(r'^(.+?)\s*\((\d+(?:\.\d+)?)\s*["\u201d\u2033]\)$')
_TOTALS = {"units": r"Total Units:\s*(\d+)", "points": r"Total Points:\s*(\d+)",
           "unit_strength": r"Total Unit Strength:\s*(\d+)"}


def _split_rules(text):
    # Keep qualifiers such as Elite(Combat, Ranged) together.
    parts, start, depth = [], 0, 0
    for index, char in enumerate(text):
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth < 0:
                raise ValueError(f"Unbalanced parentheses in rules or traits: {text}")
        elif char == "," and depth == 0:
            parts.append(text[start:index].strip())
            start = index + 1
    parts.append(text[start:].strip())
    if depth:
        raise ValueError(f"Unbalanced parentheses in rules or traits: {text}")
    return [part for part in parts if part]


def _details(lines):
    rules, traits, options, weapons, unparsed = [], [], [], [], []
    section = None
    for line in lines:
        line = " ".join(line.split())
        if line.startswith("Special Rules:"):
            content = line.removeprefix("Special Rules:").strip()
            rule_text, separator, trait_text = content.partition("Traits:")
            rules.append(rule_text)
            section = traits if separator else rules
            if separator:
                traits.append(trait_text)
        elif line.startswith("Traits:"):
            traits.append(line.removeprefix("Traits:").strip())
            section = traits
        elif match := _OPTION.fullmatch(line):
            label = match["label"]
            option = {"label": label, "name": label, "points": int(match["points"])}
            if value := re.fullmatch(r"(.+?)\s*\((\d+)\)", label):
                option.update(name=value[1].strip(), value=int(value[2]))
            options.append(option)
            section = None
        elif match := _WEAPON.fullmatch(line):
            weapons.append({"name": match[1].strip(), "range_in": float(match[2])})
            section = None
        elif section is not None:
            section.append(line)
        else:
            unparsed.append(line)
    return {"special_rules": _split_rules(" ".join(rules)), "traits": _split_rules(" ".join(traits)),
            "options": options, "weapons": weapons, "unparsed_details": unparsed}


def _finish_entry(current):
    profile = current["profile"]
    details = _details(current["source"]["details"])
    classification = profile["classification"]
    formation = re.search(r"\b(Troop|Regiment|Horde|Legion)$", classification)
    formation = formation[1] if formation else "Hero" if re.search(r"\bHero\b", classification) else "Single"
    kind = "individual" if any(rule.casefold() == "individual" for rule in details["special_rules"]) else (
        "war_engine" if re.search(r"\bWar (?:Engine|Eng)\b", classification, re.I) else "ordinary")
    nerve = profile["nerve"]
    attributes = {"speed_in": float(profile["speed"]), "height": int(profile["height"]),
                  "melee": None if profile["melee"] == "-" else profile["melee"],
                  "shooting": None if profile["shooting"] == "-" else profile["shooting"],
                  "defence": None if profile["defence"] == "-" else profile["defence"],
                  "unit_strength": int(profile["strength"]), "attacks": int(profile["attacks"]),
                  "nerve": int(nerve) if nerve.isdigit() else None if nerve == "-" else nerve,
                  "points": int(profile["points"]), "unit_kind": kind, "side": current["side"],
                  **{key: details[key] for key in ("special_rules", "traits", "options", "weapons")}}
    name = f"{current['unit_name']} / {formation}"
    if details["options"]:
        name += " / " + ", ".join(option["label"] for option in details["options"])
    return {"name": name, "unit_name": current["unit_name"], "formation": formation,
            "classification": classification, "attributes": attributes,
            "unparsed_details": details["unparsed_details"], "source": current["source"]}


def _parse_pages(pages, *, side=None):
    """Parse the supported table layout; reject incomplete lists instead of exporting them."""
    entries, declared = [], {}
    heading = current = None
    done = False
    for page_number, text in enumerate(pages, start=1):
        for line_number, raw in enumerate(text.splitlines(), start=1):
            line = " ".join(raw.split())
            if not line:
                continue
            totals = {key: int(match[1]) for key, pattern in _TOTALS.items()
                      if (match := re.search(pattern, line))}
            if totals:
                if current is not None:
                    entries.append(_finish_entry(current))
                    current = None
                declared.update(totals)
                if "points" in totals:
                    done = True
                    break
                continue
            if match := _HEADER.fullmatch(line):
                if current is not None:
                    entries.append(_finish_entry(current))
                    current = None
                heading = match["name"]
                continue
            if match := _PROFILE.fullmatch(line):
                if heading is None:
                    raise ValueError(f"Unit profile has no supported header at page {page_number}, line {line_number}.")
                if current is not None:
                    entries.append(_finish_entry(current))
                current = {"unit_name": re.sub(r"\s*\[\d+\]$", "", heading).strip(),
                           "profile": match.groupdict(), "side": side,
                           "source": {"page": page_number, "line": line_number, "heading": heading,
                                      "profile": raw.strip(), "details": []}}
                continue
            if re.fullmatch(r"\d+(?:st|nd|rd|th) Battalion", line) or line.startswith("Powered by TCPDF"):
                continue
            if heading is not None and re.match(r"(?:Champion|Core|Support|Specialist)\b.*\[\d+\]$", line):
                raise ValueError(f"Unsupported unit profile at page {page_number}, line {line_number}: {line}")
            if current is not None:
                current["source"]["details"].append(raw.strip())
        if done:
            break
    if current is not None:
        entries.append(_finish_entry(current))
    if not entries:
        raise ValueError("No supported Mantic Companion unit table found. Scanned PDFs and OCR are not supported.")
    actual = {"units": len(entries), "points": sum(entry["attributes"]["points"] for entry in entries),
              "unit_strength": sum(entry["attributes"]["unit_strength"] for entry in entries)}
    for key in _TOTALS:
        if key not in declared:
            raise ValueError(f"PDF is missing its declared total {key}; completeness cannot be checked.")
        if declared[key] != actual[key]:
            raise ValueError(f"PDF total {key} mismatch: declared {declared[key]}, parsed {actual[key]}.")
    return entries, actual


def _read_pdf(path, side):
    from pypdf import PdfReader, __version__
    from pypdf.errors import PyPdfError

    path = Path(path).resolve()
    content = path.read_bytes()
    if not content.startswith(b"%PDF-"):
        raise ValueError(f"Expected a PDF file: {path}")
    try:
        reader = PdfReader(BytesIO(content))
        if reader.is_encrypted:
            raise ValueError("Encrypted PDFs are not supported.")
        pages = [page.extract_text(extraction_mode="layout", layout_mode_space_vertically=False) or ""
                 for page in reader.pages]
        entries, totals = _parse_pages(pages, side=side)
        source = {"pdf": str(path), "sha256": hashlib.sha256(content).hexdigest(),
                  "title": reader.metadata.title if reader.metadata else None,
                  "pages": len(pages), "side": side, "totals": totals, "totals_verified": True,
                  "text_backend": f"pypdf {__version__}"}
    except (PyPdfError, ValueError) as error:
        raise ValueError(f"{path.name}: {error}") from error
    return entries, source


def _type_id(index):
    result = ""
    while index >= 0:
        index, remainder = divmod(index, 26)
        result = chr(ord("A") + remainder) + result
        index -= 1
    return result


def read_unit_list_pdfs(paths, *, sides=None):
    """Return a type catalog for one or more PDFs; instances stay registration-generated.

    ``sides`` optionally supplies one explicit side label per PDF. Missing tray
    dimensions and dynamic states are omitted, rather than guessed.
    """
    paths = [paths] if isinstance(paths, (str, Path)) else list(paths)
    if not paths:
        raise ValueError("Provide at least one army-list PDF.")
    sides = [None] * len(paths) if sides is None else list(sides)
    if len(sides) != len(paths) or any(side is not None and (not isinstance(side, str) or not side.strip()) for side in sides):
        raise ValueError("Supply one non-empty side label per PDF, or leave sides unspecified.")
    sources, groups = [], {}
    for source_index, (path, side) in enumerate(zip(paths, sides)):
        entries, source = _read_pdf(path, side.strip() if side is not None else None)
        sources.append(source)
        for entry in entries:
            original = entry.pop("source")
            fingerprint = (source_index, json.dumps(entry, sort_keys=True, ensure_ascii=False))
            if fingerprint not in groups:
                groups[fingerprint] = {"type_id": _type_id(len(groups)), **deepcopy(entry),
                                       "listed_count": 0, "source_entries": []}
            record = groups[fingerprint]
            record["listed_count"] += 1
            record["source_entries"].append({"source_index": source_index, **original})
    warnings = ["Tray dimensions are not printed in these PDFs; add dimension.width_mm/depth_mm before tray fitting.",
                "Listed counts are reference metadata; registration still generates instance IDs without enforcing counts.",
                "Parsed special rules and purchased options are retained; this does not establish rule-engine support."]
    for record in groups.values():
        if record["unparsed_details"]:
            warnings.append(f"Type {record['type_id']} contains unparsed detail lines; review unparsed_details and source_entries.")
    result = {"format": "mantic-companion-pdf-catalog-v1", "sources": sources,
              "unit_types": list(groups.values()), "warnings": warnings,
              "summary": {"unit_types": len(groups), **{key: sum(source["totals"][key] for source in sources) for key in _TOTALS}}}
    UnitRoster(result)
    return result


def read_unit_list_pdf(path, *, side=None):
    """Read one army-list PDF; see read_unit_list_pdfs for multiple armies."""
    return read_unit_list_pdfs([path], sides=[side])
