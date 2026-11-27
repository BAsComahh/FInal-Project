"""Unit-type catalog with per-type instance IDs allocated during registration."""

from copy import deepcopy
import json
from math import isfinite
from pathlib import Path


def _records(rows, key, name):
    if not isinstance(rows, list) or not rows:
        raise ValueError(f"{name} must be a non-empty list")
    records = {}
    for row in rows:
        if isinstance(row, str):
            row = {key: row}
        if not isinstance(row, dict):
            raise ValueError(f"Every {name} entry must be an object")
        value = row.get(key)
        if not isinstance(value, str) or not value.strip() or value != value.strip():
            raise ValueError(f"Every {name} entry needs a non-empty {key} without surrounding spaces")
        if value in records:
            raise ValueError(f"Duplicate {key}: {value}")
        if not isinstance(row.get("attributes", {}), dict):
            raise ValueError(f"attributes must be an object: {value}")
        records[value] = deepcopy(row)
    return records


def _list_metadata(payload, source):
    return {"source": str(source) if source is not None else None,
            "metadata": {key: deepcopy(value) for key, value in payload.items()
                         if key not in ("unit_types", "units", "lists")}}


class UnitRoster:
    def __init__(self, payload, *, source=None):
        if not isinstance(payload, dict):
            raise ValueError("Unit file must contain a JSON object")
        list_metadata = payload.get("lists", {})
        if not isinstance(list_metadata, dict) or any(key not in ("A", "B") or not isinstance(value, dict)
                                                     for key, value in list_metadata.items()):
            raise ValueError("lists must map A/B to metadata objects")
        self.types = _records(payload.get("unit_types"), "type_id", "unit_types")
        for type_id, record in self.types.items():
            if record.get("list_id") not in (None, "A", "B"):
                raise ValueError(f"list_id for {type_id} must be A or B")
            if record.get("list_id") is None:
                record.pop("list_id", None)
            dimension = record.get("dimension")
            if dimension is not None:
                if not isinstance(dimension, dict) or not all(key in dimension for key in ("width_mm", "depth_mm")):
                    raise ValueError(f"dimension for {type_id} must contain width_mm and depth_mm")
                for key in ("width_mm", "depth_mm"):
                    value = dimension[key]
                    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value) or value <= 0:
                        raise ValueError(f"dimension.{key} for {type_id} must be finite and positive")
        self.payload = deepcopy(payload)
        # Instances are produced by registration, including for older files
        # that still happen to contain a predeclared units list.
        self.payload.pop("units", None)
        self.source = source
        self.units = {}
        self.bindings = {}
        self.counters = {}

    @classmethod
    def load(cls, path):
        path = Path(path).resolve()
        try:
            payload = json.loads(path.read_text(encoding="utf-8-sig"))
        except (UnicodeError, json.JSONDecodeError) as error:
            raise ValueError(f"Invalid unit JSON: {path}: {error}") from error
        return cls(payload, source=str(path))

    @classmethod
    def from_snapshot(cls, payload):
        """Restore generated instance identities without allocating new numbers."""
        roster = cls(payload["roster"], source=payload.get("source"))
        roster.units = _records(payload.get("units"), "unit_id", "saved units")
        for uid, unit in roster.units.items():
            type_id = unit.get("type_id")
            if type_id not in roster.types:
                raise ValueError(f"Unknown saved type for {uid}")
            prefix = type_id + ("." if roster.types[type_id].get("list_id") else "")
            serial = uid.removeprefix(prefix) if uid.startswith(prefix) else ""
            if not serial.isdecimal() or int(serial) < 1:
                raise ValueError(f"Invalid saved unit ID: {uid}")
            unit.setdefault("attributes", {})
        rows = payload.get("bindings")
        if not isinstance(rows, list):
            raise ValueError("Saved bindings must be a list")
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError("Invalid saved object binding")
            obj, uid = row.get("object_id"), row.get("unit_id")
            if (isinstance(obj, bool) or not isinstance(obj, int) or obj < 1 or obj in roster.bindings
                    or uid not in roster.units or uid in roster.bindings.values()):
                raise ValueError("Saved bindings contain invalid or duplicate identities")
            roster.bindings[obj] = uid
        if set(roster.bindings.values()) != set(roster.units):
            raise ValueError("Each saved unit must have exactly one object binding")
        counters = payload.get("counters", {})
        if not isinstance(counters, dict) or any(key not in roster.types or isinstance(value, bool)
                or not isinstance(value, int) or value < 0 for key, value in counters.items()):
            raise ValueError("Invalid saved instance counters")
        roster.counters = dict(counters)
        return roster

    def _next(self, type_id):
        if type_id not in self.types:
            raise ValueError(f"Unknown type: {type_id}")
        number = self.counters.get(type_id, 0) + 1
        separator = "." if self.types[type_id].get("list_id") else ""
        while f"{type_id}{separator}{number}" in self.units:
            number += 1
        return number, f"{type_id}{separator}{number}"

    def next_unit_id(self, type_id):
        return self._next(type_id)[1]

    def bind(self, object_id, type_id):
        object_id = int(object_id)
        number, unit_id = self._next(type_id)
        current = self.bindings.get(object_id)
        if current is not None and self.units[current]["type_id"] == type_id:
            return current
        self.unbind(object_id)
        self.counters[type_id] = number
        self.units[unit_id] = {"unit_id": unit_id, "type_id": type_id, "attributes": {}}
        self.bindings[object_id] = unit_id
        return unit_id

    def unbind(self, object_id):
        unit_id = self.bindings.pop(object_id, None)
        if unit_id is not None:
            unit = self.units.pop(unit_id)
            type_id = unit["type_id"]
            number = int(unit_id[len(type_id):].removeprefix("."))
            self.counters[type_id] = min(self.counters.get(type_id, 0), number - 1)

    def reset_bindings(self):
        self.bindings.clear()
        self.units.clear()
        self.counters.clear()

    def retain_bindings(self, previous, *, type_ids=None):
        """Keep generated IDs for types still available after catalog reload."""
        allowed = set(self.types) if type_ids is None else set(type_ids) & self.types.keys()
        self.counters = {key: value for key, value in previous.counters.items() if key in allowed}
        for object_id, unit_id in previous.bindings.items():
            unit = previous.units[unit_id]
            if unit["type_id"] in allowed:
                self.units[unit_id] = deepcopy(unit)
                self.bindings[object_id] = unit_id

    def with_dimensions(self, dimensions):
        """Validate a detached size edit while retaining every instance and binding."""
        if not isinstance(dimensions, dict) or dimensions.keys() - self.types.keys():
            raise ValueError("Dimensions must map existing type IDs to sizes or null.")
        records = deepcopy(self.types)
        for type_id, dimension in dimensions.items():
            if dimension is None:
                records[type_id].pop("dimension", None)
            else:
                records[type_id]["dimension"] = deepcopy(dimension)
        payload = {**deepcopy(self.payload), "unit_types": list(records.values())}
        roster = UnitRoster(payload, source=self.source)
        roster.retain_bindings(self)
        return roster

    def with_list(self, list_id, payload, *, source=None):
        """Return a validated replacement for one side, preserving the other side's bindings."""
        if list_id not in ("A", "B"):
            raise ValueError("Choose list A or B.")
        incoming = UnitRoster(payload, source=source)
        side_values = [record.get("attributes", {}).get("side") for record in incoming.types.values()
                       if record.get("attributes", {}).get("side") is not None]
        if any(not isinstance(side, str) or not side.strip() for side in side_values):
            raise ValueError("Side labels in the imported catalog must be non-empty strings.")
        sides = {side.strip() for side in side_values}
        lists = {record["list_id"] for record in incoming.types.values() if record.get("list_id")}
        source_records = payload.get("sources", [])
        if not isinstance(source_records, list):
            raise ValueError("sources in an imported catalog must be a list.")
        if len(sides) > 1 or len(lists) > 1 or len(source_records) > 1:
            raise ValueError("Import one army per button. This JSON contains multiple sides; use a single-army catalog.")
        kept = {key: deepcopy(record) for key, record in self.types.items()
                if record.get("list_id", "A") != list_id}
        records = list(kept.values())
        for index, record in enumerate(incoming.types.values(), start=1):
            type_id = f"{list_id}{index}"
            if type_id in kept:
                kept_side = kept[type_id].get("list_id", "A")
                raise ValueError(
                    f"List {list_id} would generate type ID {type_id}, already used by list {kept_side}. "
                    f"Use a catalog for list {kept_side} with a different ID for that type before importing list {list_id}."
                )
            record = deepcopy(record)
            record.update(source_type_id=record["type_id"], type_id=type_id,
                          list_id=list_id, type_number=index)
            record["attributes"] = {**record.get("attributes", {}), "side": list_id}
            records.append(record)
        metadata = deepcopy(self.payload.get("lists", {}))
        if kept and "A" not in metadata and any(row.get("list_id", "A") == "A" for row in kept.values()):
            metadata["A"] = _list_metadata(self.payload, self.source)
        metadata[list_id] = _list_metadata(incoming.payload, incoming.source)
        records.sort(key=lambda record: (record.get("list_id", "A"), record.get("type_number", 0)))
        roster = UnitRoster({"unit_types": records, "lists": metadata})
        roster.retain_bindings(self, type_ids=kept)
        return roster

    def object_for(self, unit_id):
        return next((key for key, value in self.bindings.items() if value == unit_id), None)

    def annotation(self, object_id):
        unit_id = self.bindings.get(object_id)
        if unit_id is None:
            raise ValueError(f"Mask {object_id} has no unit label")
        unit = self.units[unit_id]
        return {"unit_id": unit_id, "type_id": unit["type_id"], "unit": deepcopy(unit),
                "unit_type": deepcopy(self.types[unit["type_id"]])}

    def snapshot(self):
        return {"roster": deepcopy(self.payload), "source": self.source,
                "units": deepcopy(list(self.units.values())), "counters": dict(self.counters),
                "bindings": [{"object_id": key, "unit_id": value}
                             for key, value in self.bindings.items()]}
