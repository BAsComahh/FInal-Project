"""Discrete reachable poses with witnessed translations and centre pivots."""

import itertools
import math

from . import geometry as g
from .scene import find_unit, rule_warnings, special_rules, validate_scene

ORDERS = ('advance', 'double', 'back', 'sidestep_left', 'sidestep_right', 'change_facing', 'halt')


def _angles(step, limit):
    positive = [i * step for i in range(1, int(limit / step) + 1)]
    if not positive or abs(positive[-1] - limit) > g.EPS:
        positive.append(float(limit))
    return [-v for v in positive[::-1]] + [0.0] + positive


def reachable_poses(scene, unit_id, order='advance', angle_step_deg=30, distance_steps=4):
    scene = validate_scene(scene)
    unit = find_unit(scene, unit_id)
    if order not in ORDERS:
        raise ValueError(f"order must be one of {', '.join(ORDERS)}")
    if isinstance(angle_step_deg, bool) or not isinstance(angle_step_deg, (int, float)) or not math.isfinite(angle_step_deg) or not 1 <= angle_step_deg <= 180:
        raise ValueError('angle_step_deg must be a finite number from 1 to 180')
    if isinstance(distance_steps, bool) or not isinstance(distance_steps, int) or not 1 <= distance_steps <= 20:
        raise ValueError('distance_steps must be an integer from 1 to 20')
    warnings = rule_warnings(scene, [unit])
    warnings.extend([
        'Movement is a discrete subset with witness paths, not a continuous reachable area or a full legality verdict.',
        'Geometry applies only to registered units/terrain; missing objects and estimated facing can change the result.',
    ])
    result = {'status': 'unavailable', 'order': order, 'reason': '', 'poses': [], 'warnings': warnings}

    def unavailable(reason):
        result['reason'] = reason
        return result

    if unit['front_edge'] is None:
        return unavailable('Unit front_edge is unknown.')
    state = unit['state']
    if order != 'halt':
        if state['engaged'] is None:
            return unavailable('Engaged state is unknown; confirm it before querying this order.')
        if state['engaged']:
            return unavailable('Engaged units may only Halt, Reform or Withdraw; the latter two are outside this prototype (mini-book p19).')
        if order not in ('back', 'change_facing'):
            if state['wavering'] is None:
                return unavailable('Wavering state is unknown; confirm it before querying this order.')
            if state['wavering']:
                return unavailable('A Wavering unit may only Halt, Change Facing or Back (mini-book p33).')
    if unit['unit_kind'] is None and order != 'halt':
        return unavailable('unit_kind is unknown.')
    rules = special_rules(unit)
    if (unit['unit_kind'] == 'individual' or 'individual' in rules) and order != 'halt':
        return unavailable('Individual free facing before an order is not implemented (mini-book p35); ordinary movement is not substituted.')
    if unit['unit_kind'] == 'war_engine' and order == 'double':
        return unavailable('War Engines cannot move At the Double (mini-book p35).')
    if unit['speed_in'] is None and order not in ('halt', 'change_facing'):
        return unavailable('Unit speed_in is unknown.')
    fly = 'fly' in rules
    board = scene['board_size_mm']
    original = unit['corners_mm']
    original_center = g.center(original)
    _, _, normal, _ = g.front_frame(original, unit['front_edge'])
    original_heading = math.degrees(math.atan2(normal[1], normal[0])) % 360
    offsets = [g.sub(p, original_center) for p in original]
    other_units = [u for u in scene['units'] if u['unit_id'] != unit_id]
    enemies = [u for u in other_units if unit['side'] is None or u['side'] is None or u['side'] != unit['side']]
    if any(u['side'] is None for u in other_units) or unit['side'] is None:
        warnings.append('Unknown-side units are treated as enemies for translation traversal; contact endpoints remain allowed.')
    blocked_kinds = {'blocking'}
    if order == 'double':
        blocked_kinds.add('obstacle')
        if 'pathfinder' not in rules:
            blocked_kinds.add('difficult')
    if unit['unit_kind'] == 'war_engine':
        blocked_kinds.add('obstacle')
    # Fly ignores traversal; its destination still has to clear actual Blocking Terrain.
    end_kinds = {'blocking'} if fly else blocked_kinds
    end_terrain = [triangle for t in scene['terrain'] if t['kind'] in end_kinds for triangle in g.triangles(t['polygon_mm'])]
    travel_terrain = [] if fly else [triangle for t in scene['terrain'] if t['kind'] in blocked_kinds for triangle in g.triangles(t['polygon_mm'])]
    endpoint_obstacles = [u['corners_mm'] for u in other_units] + end_terrain
    travel_obstacles = [] if fly else [u['corners_mm'] for u in enemies] + travel_terrain
    shape_cache, clear_cache, travel_cache = {}, {}, {}

    def key(pose):
        return (round(pose[0], 7), round(pose[1], 7), round(pose[2] % 360, 7))

    def shape(pose):
        heading = round(pose[2] % 360, 7)
        if heading not in shape_cache:
            theta = math.radians(heading - original_heading)
            co, si = math.cos(theta), math.sin(theta)
            shape_cache[heading] = [(co * x - si * y, si * x + co * y) for x, y in offsets]
        return [[pose[0] + x, pose[1] + y] for x, y in shape_cache[heading]]

    def on_board(poly):
        return all(-g.EPS <= p[0] <= board[0] + g.EPS and -g.EPS <= p[1] <= board[1] + g.EPS for p in poly)

    def clear(pose):
        k = key(pose)
        if k not in clear_cache:
            poly = shape(pose)
            clear_cache[k] = on_board(poly) and not any(g.convex_overlap(poly, obstacle) for obstacle in endpoint_obstacles)
        return clear_cache[k]

    def translate(pose, distance):
        if distance <= g.EPS:
            return pose
        theta = math.radians(pose[2])
        direction = (math.cos(theta), math.sin(theta))
        if order == 'back':
            direction = (-direction[0], -direction[1])
        elif order == 'sidestep_left':
            direction = (direction[1], -direction[0])
        elif order == 'sidestep_right':
            direction = (-direction[1], direction[0])
        dest = (pose[0] + distance * direction[0], pose[1] + distance * direction[1], pose[2])
        k = (key(pose), round(distance, 7))
        if k not in travel_cache:
            before, after = shape(pose), shape(dest)
            swept = g.hull(before + after)
            travel_cache[k] = on_board(before) and on_board(after) and not any(g.convex_overlap(swept, obstacle) for obstacle in travel_obstacles)
        return dest if travel_cache[k] else None

    poses = {}
    initial = (*original_center, original_heading)

    def save(pose, path):
        if not clear(pose):
            return
        k = key(pose)
        if k not in poses:
            poses[k] = {'center_mm': [pose[0], pose[1]], 'corners_mm': shape(pose),
                        'front_edge': unit['front_edge'], 'heading_deg': pose[2] % 360,
                        'path': [{'center_mm': [p[0], p[1]], 'heading_deg': p[2] % 360} for p in path]}

    if order == 'halt':
        save(initial, [initial])
    elif order == 'change_facing':
        for angle in sorted({0.0, *[i * angle_step_deg for i in range(1, math.ceil(360 / angle_step_deg))]}):
            dest = (initial[0], initial[1], (initial[2] + angle) % 360)
            save(dest, [initial] if angle == 0 else [initial, dest])
    else:
        pivots = 2 if order == 'advance' else 1
        angles = _angles(angle_step_deg, 90)
        candidate_count = len(angles) ** pivots * math.comb(distance_steps + pivots + 1, pivots + 1)
        if candidate_count > 30000:
            raise ValueError('Sampling would exceed 30,000 candidate paths; increase angle_step_deg or reduce distance_steps')
        budget = unit['speed_in'] * 25.4 * (2 if order == 'double' else 0.5 if order in ('back', 'sidestep_left', 'sidestep_right') else 1)
        increment = budget / distance_steps
        for lengths in itertools.product(range(distance_steps + 1), repeat=pivots + 1):
            if sum(lengths) > distance_steps:
                continue
            for turns in itertools.product(angles, repeat=pivots):
                pose, path = initial, [initial]
                valid = True
                for i, length in enumerate(lengths):
                    dest = translate(pose, increment * length)
                    if dest is None:
                        valid = False
                        break
                    if length and math.dist(dest[:2], pose[:2]) > g.EPS:
                        path.append(dest)
                    pose = dest
                    if i < pivots and turns[i]:
                        pose = (pose[0], pose[1], (pose[2] + turns[i]) % 360)
                        # The swept rotation is deliberately not collision checked (p15).
                        if not clear(pose):
                            valid = False
                            break
                        path.append(pose)
                if valid:
                    save(pose, path)
    result.update(status='estimated', poses=list(poses.values()),
                  reason=f'Discrete {order} centre poses with valid witness paths under the supplied mini-rulebook geometry; {angle_step_deg:g} degree pivot grid, {distance_steps} distance divisions.' if poses else 'No sampled endpoint has a clear, in-board witness path; this does not prove the order impossible.')
    if fly:
        warnings.append('Fly traversal is supported; intermediate pivot endpoints are conservatively required clear as in p15, so some Fly paths allowed by p37 may be omitted.')
    return result
