"""Base-to-base distance and sampled, conservative mini-rulebook LOS."""

import math

from . import geometry as g
from .scene import find_unit, rule_warnings, special_rules, validate_scene


def measure_distance(scene, a_id, b_id):
    scene = validate_scene(scene)
    a, b = find_unit(scene, a_id), find_unit(scene, b_id)
    p, q = g.closest_points(a['corners_mm'], b['corners_mm'])
    distance = math.dist(p, q)
    return {'status': 'ok', 'distance_mm': distance, 'distance_in': distance / 25.4,
            'point_a_mm': p, 'point_b_mm': q}


def _height(unit, scene, warnings, observer=False):
    height = unit['height']
    hills = [t for t in scene['terrain'] if t['kind'] == 'hill' and g.inside(g.center(unit['corners_mm']), t['polygon_mm'])]
    if len(hills) > 1:
        warnings.append(f"{unit['unit_id']}: overlapping hill footprints; effective height is unknown.")
        return None
    if hills:
        extra = hills[0]['height']
        height = None if height is None or extra is None else height + extra
    if observer and height is not None and 'leaper' in special_rules(unit):
        height += 1
    return height


def _samples(a, b, count):
    return [[a[k] + i / (count - 1) * (b[k] - a[k]) for k in (0, 1)] for i in range(count)]


def _edge_samples(a, b, count, terrain):
    values = _samples(a, b, count)
    # Add footprint intersections so even a narrow terrain-contained endpoint is tried.
    for t in terrain:
        for p, q in g.edges(t['polygon_mm']):
            hit = g.segment_hit(a, b, p, q)
            if hit is not None:
                values.append(hit)
    return values


def line_of_sight(scene, a_id, b_id, samples=9):
    scene = validate_scene(scene)
    a, b = find_unit(scene, a_id), find_unit(scene, b_id)
    warnings = rule_warnings(scene, scene['units'])
    warnings.append('LOS searches finite front-edge/base-edge samples; a clear ray is a witness, unsuccessful sampling is inconclusive.')
    result = {'status': 'unavailable', 'reason': '', 'warnings': warnings}
    if isinstance(samples, bool) or not isinstance(samples, int) or not 2 <= samples <= 101:
        raise ValueError('samples must be an integer from 2 to 101')
    if a_id == b_id:
        result['reason'] = 'LOS requires two distinct units.'
        return result
    if a['front_edge'] is None:
        result['reason'] = 'Observer front_edge is unknown.'
        return result
    if not g.front_arc_clip(b['corners_mm'], a['corners_mm'], a['front_edge']):
        result.update(status='blocked', reason='The entire target base is outside the 45-degree arc from the observer front corners.')
        return result
    ah, bh = _height(a, scene, warnings, True), _height(b, scene, warnings)
    blockers = []
    for unit in scene['units']:
        if unit['unit_id'] not in (a_id, b_id):
            blockers.append((unit['corners_mm'], _height(unit, scene, warnings), False))
    for t in scene['terrain']:
        if t['kind'] != 'decorative':
            blockers.append((t['polygon_mm'], t['height'], True))
    relevant = []
    for poly, height, terrain in blockers:
        # One endpoint taller is sufficient even when the other height is unknown.
        if height is not None and any(h is not None and h > height for h in (ah, bh)):
            continue
        known = height is not None and ah is not None and bh is not None
        relevant.append((poly, known, terrain))
    edge = a['front_edge']
    origins = _edge_samples(a['corners_mm'][edge], a['corners_mm'][(edge + 1) % 4], samples, scene['terrain'])
    targets = [p for c, d in g.edges(b['corners_mm']) for p in _edge_samples(c, d, samples, scene['terrain'])]
    unknown_hit = False
    for p in origins:
        for q in targets:
            obstructed = False
            for poly, known, terrain in relevant:
                if terrain and (g.inside(p, poly) or g.inside(q, poly)):
                    continue
                if g.ray_hits(p, q, poly):
                    obstructed = True
                    unknown_hit |= not known
                    break
            if not obstructed:
                if scene.get('geometry_complete') is False:
                    result.update(status='uncertain', reason='A registered unit has no valid tray; occlusion geometry is incomplete.')
                    return result
                result.update(status='clear', reason='A sampled front-facing-to-target-base ray is clear under the registered scene and supported mini-rulebook assumptions.', line_mm=[p, q])
                return result
    result.update(status='uncertain', reason='No clear sampled ray was found; sampling cannot prove complete occlusion.' + (' Heights are unknown for some intersecting geometry.' if unknown_hit else ''))
    return result
