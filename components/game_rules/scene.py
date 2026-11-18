"""Validate the JSON scene boundary without guessing missing rules facts."""

import copy
import math
from numbers import Real

from . import geometry as g

OBSTACLE_HEIGHT = 1.0


def _number(value, name, minimum=0, nullable=False):
    if value is None and nullable:
        return None
    if isinstance(value, bool) or not isinstance(value, Real) or not math.isfinite(value) or value < minimum:
        raise ValueError(f"{name} must be a finite number >= {minimum}" + (" or null" if nullable else ""))
    return float(value)


def _polygon(value, name, rectangle=False):
    if not isinstance(value, list) or len(value) < 3 or (rectangle and len(value) != 4):
        raise ValueError(f"{name} must contain {'four' if rectangle else 'at least three'} cyclic points")
    p = []
    for point in value:
        if not isinstance(point, (list, tuple)) or len(point) != 2:
            raise ValueError(f"{name} points must be [x, y]")
        p.append([_number(v, name, minimum=-float('inf')) for v in point])
    if len(set(tuple(v) for v in p)) != len(p) or abs(g.area(p)) <= g.EPS:
        raise ValueError(f"{name} must have distinct vertices and nonzero area")
    for i, (a, b) in enumerate(g.edges(p)):
        for j, (c, d) in enumerate(g.edges(p)):
            if j > i and j not in {(i + 1) % len(p), (i - 1) % len(p)} and g.segment_hit(a, b, c, d) is not None:
                raise ValueError(f"{name} must be simple and cyclic (no crossed edges)")
    # Reject adjacent edges that double back; harmless collinear points remain valid.
    for i in range(len(p)):
        a, b, c = p[i - 1], p[i], p[(i + 1) % len(p)]
        if abs(g.cross(g.sub(b, a), g.sub(c, b))) <= g.EPS and g.dot(g.sub(a, b), g.sub(c, b)) > 0:
            raise ValueError(f"{name} has overlapping adjacent edges")
    if rectangle:
        vectors = [g.sub(b, a) for a, b in g.edges(p)]
        signs = [g.cross(vectors[i], vectors[(i + 1) % 4]) for i in range(4)]
        if not (all(v > g.EPS for v in signs) or all(v < -g.EPS for v in signs)):
            raise ValueError(f"{name} must be a convex cyclic rectangle")
        for a, b in zip(vectors, vectors[1:] + vectors[:1]):
            if abs(g.dot(a, b)) > 1e-5 * math.hypot(*a) * math.hypot(*b):
                raise ValueError(f"{name} must be rectangular (orthogonal adjacent edges)")
    return p


def _identifier(value, name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a nonempty string")
    return value


def validate_unit_profile(unit, state, name):
    for field in ('height', 'speed_in'):
        unit[field] = _number(unit.get(field), name + '.' + field, nullable=True)
    side = unit.setdefault('side', None)
    if side is not None:
        _identifier(side, name + '.side')
    kind = unit.setdefault('unit_kind', None)
    if kind not in (None, 'ordinary', 'war_engine', 'individual'):
        raise ValueError(f"{name}.unit_kind is invalid")
    rules = unit.setdefault('special_rules', [])
    if not isinstance(rules, list) or any(not isinstance(r, str) or not r.strip() for r in rules):
        raise ValueError(f"{name}.special_rules must be a list of nonempty strings")
    if not isinstance(state, dict):
        raise ValueError(f"{name}.state must be an object")
    for field in ('engaged', 'wavering'):
        value = state.setdefault(field, None)
        if value is not None and not isinstance(value, bool):
            raise ValueError(f"{name}.state.{field} must be boolean or null")


def validate_scene(scene):
    """Return a detached, normalized scene; null metadata stays unknown."""
    if not isinstance(scene, dict) or scene.get('ruleset') != 'kow4-mini':
        raise ValueError("scene.ruleset must be 'kow4-mini'")
    result = copy.deepcopy(scene)
    board = result.get('board_size_mm')
    if not isinstance(board, (list, tuple)) or len(board) != 2:
        raise ValueError("board_size_mm must be [width, depth]")
    result['board_size_mm'] = [_number(v, 'board_size_mm', g.EPS) for v in board]
    for collection, key in (('units', 'unit_id'), ('terrain', 'terrain_id')):
        values = result.get(collection, [])
        if not isinstance(values, list) or any(not isinstance(v, dict) for v in values):
            raise ValueError(f"{collection} must be a list of objects")
        result[collection] = values
        ids = [_identifier(v.get(key), key) for v in values]
        if len(set(ids)) != len(ids):
            raise ValueError(f"Duplicate {key}")
    warnings = result.setdefault('warnings', [])
    if not isinstance(result.get('geometry_complete', True), bool):
        raise ValueError("geometry_complete must be a boolean")
    if not isinstance(warnings, list) or any(not isinstance(v, str) for v in warnings):
        raise ValueError("warnings must be a list of strings")
    for unit in result['units']:
        name = unit['unit_id']
        unit['corners_mm'] = _polygon(unit.get('corners_mm'), name + '.corners_mm', rectangle=True)
        edge = unit.setdefault('front_edge', None)
        if edge is not None and (isinstance(edge, bool) or not isinstance(edge, int) or edge not in range(4)):
            raise ValueError(f"{name}.front_edge must be 0..3 or null")
        validate_unit_profile(unit, unit.setdefault('state', {}), name)
    for terrain in result['terrain']:
        name = terrain['terrain_id']
        terrain['polygon_mm'] = _polygon(terrain.get('polygon_mm'), name + '.polygon_mm')
        if terrain.get('kind') not in ('blocking', 'difficult', 'obstacle', 'hill', 'decorative'):
            raise ValueError(f"{name}.kind is invalid")
        height = _number(terrain.get('height'), name + '.height', nullable=True)
        if terrain['kind'] == 'obstacle':
            if height is not None and height != OBSTACLE_HEIGHT:
                raise ValueError(f"{name}.height must be {OBSTACLE_HEIGHT:g} for Obstacle terrain")
            height = OBSTACLE_HEIGHT
        terrain['height'] = height
    return result


def find_unit(scene, unit_id):
    for unit in scene['units']:
        if unit['unit_id'] == unit_id:
            return unit
    raise ValueError(f"Unknown unit_id: {unit_id}")


def special_rules(unit):
    return {r.strip().casefold() for r in unit['special_rules']}


def rule_warnings(scene, units):
    warnings = list(scene['warnings'])
    supported = {'fly', 'pathfinder', 'leaper'}
    for unit in units:
        unsupported = sorted(special_rules(unit) - supported)
        if unsupported:
            warnings.append(f"{unit['unit_id']}: unsupported special rules: {', '.join(unsupported)}; results do not establish full rules legality.")
    return warnings
