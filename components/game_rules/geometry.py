"""Small, dependency-free planar geometry; positive overlap excludes base contact."""

import math

EPS = 1e-7


def cross(a, b):
    return a[0] * b[1] - a[1] * b[0]


def sub(a, b):
    return (a[0] - b[0], a[1] - b[1])


def dot(a, b):
    return a[0] * b[0] + a[1] * b[1]


def area(poly):
    return sum(cross(a, b) for a, b in edges(poly)) / 2


def edges(poly):
    return zip(poly, poly[1:] + poly[:1])


def center(poly):
    return [sum(p[i] for p in poly) / len(poly) for i in (0, 1)]


def on_segment(p, a, b):
    ab, ap = sub(b, a), sub(p, a)
    return abs(cross(ab, ap)) <= EPS * max(1, math.hypot(*ab)) and dot(ap, sub(p, b)) <= EPS


def segment_hit(a, b, c, d):
    """Return one intersection point, including collinear contact, or None."""
    r, s = sub(b, a), sub(d, c)
    den = cross(r, s)
    if abs(den) > EPS:
        t, u = cross(sub(c, a), s) / den, cross(sub(c, a), r) / den
        if -EPS <= t <= 1 + EPS and -EPS <= u <= 1 + EPS:
            return [a[0] + t * r[0], a[1] + t * r[1]]
    else:
        for p, x, y in ((a, c, d), (b, c, d), (c, a, b), (d, a, b)):
            if on_segment(p, x, y):
                return list(p)
    return None


def inside(p, poly, boundary=True):
    odd = False
    for a, b in edges(poly):
        if on_segment(p, a, b):
            return boundary
        if (a[1] > p[1]) != (b[1] > p[1]):
            x = a[0] + (p[1] - a[1]) * (b[0] - a[0]) / (b[1] - a[1])
            if p[0] < x:
                odd = not odd
    return odd


def ray_hits(a, b, poly):
    return inside(a, poly) or inside(b, poly) or any(segment_hit(a, b, c, d) is not None for c, d in edges(poly))


def nearest(p, a, b):
    ab = sub(b, a)
    t = max(0, min(1, dot(sub(p, a), ab) / dot(ab, ab)))
    return [a[0] + t * ab[0], a[1] + t * ab[1]]


def closest_points(a, b):
    for p in a:
        if inside(p, b):
            return list(p), list(p)
    for p in b:
        if inside(p, a):
            return list(p), list(p)
    for p, q in edges(a):
        for r, s in edges(b):
            hit = segment_hit(p, q, r, s)
            if hit is not None:
                return hit, hit
    candidates = [(list(p), nearest(p, x, y)) for p in a for x, y in edges(b)]
    candidates += [(nearest(p, x, y), list(p)) for p in b for x, y in edges(a)]
    return min(candidates, key=lambda pair: dot(sub(*pair), sub(*pair)))


def hull(points):
    points = sorted(set(tuple(p) for p in points))
    halves = []
    for seq in (points, points[::-1]):
        chain = []
        for p in seq:
            while len(chain) >= 2 and cross(sub(chain[-1], chain[-2]), sub(p, chain[-1])) <= EPS:
                chain.pop()
            chain.append(p)
        halves.append(chain[:-1])
    return halves[0] + halves[1]


def convex_overlap(a, b):
    """Separating-axis check; contact without positive area is allowed."""
    for poly in (a, b):
        for p, q in edges(poly):
            v = sub(q, p)
            axis = (-v[1], v[0])
            pa, pb = [dot(x, axis) for x in a], [dot(x, axis) for x in b]
            if min(max(pa), max(pb)) - max(min(pa), min(pb)) <= EPS * max(1, math.hypot(*axis)):
                return False
    return True


def triangles(poly):
    """Ear clipping of an already validated simple polygon (either winding)."""
    remaining = list(poly if area(poly) > 0 else poly[::-1])
    result = []
    while len(remaining) > 3:
        for i in range(len(remaining)):
            tri = [remaining[i - 1], remaining[i], remaining[(i + 1) % len(remaining)]]
            if cross(sub(tri[1], tri[0]), sub(tri[2], tri[1])) <= EPS:
                continue
            if any(inside(p, tri) for j, p in enumerate(remaining) if j not in {i, (i - 1) % len(remaining), (i + 1) % len(remaining)}):
                continue
            result.append(tri)
            remaining.pop(i)
            break
        else:
            # Collinear boundary points are valid, but are not useful ears.
            for i in range(len(remaining)):
                if on_segment(remaining[i], remaining[i - 1], remaining[(i + 1) % len(remaining)]):
                    remaining.pop(i)
                    break
            else:
                raise ValueError("Terrain polygon could not be triangulated")
    result.append(remaining)
    return result


def front_frame(corners, edge):
    c = center(corners)
    a, b = corners[edge], corners[(edge + 1) % 4]
    f = [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2]
    w = math.dist(a, b)
    tangent = [(b[i] - a[i]) / w for i in (0, 1)]
    normal = sub(f, c)
    length = math.hypot(*normal)
    return f, tangent, [v / length for v in normal], w


def front_arc_clip(poly, corners, edge):
    """Clip to front-edge and two 45-degree corner half-planes."""
    f, tangent, normal, width = front_frame(corners, edge)
    result = list(poly)
    for side in (0, -1, 1):
        def value(p):
            v = sub(p, f)
            return dot(v, normal) + (side * dot(v, tangent) + width / 2 if side else 0)
        clipped = []
        for a, b in edges(result):
            va, vb = value(a), value(b)
            if va >= -EPS:
                clipped.append(a)
            if (va >= -EPS) != (vb >= -EPS):
                t = va / (va - vb)
                clipped.append([a[i] + t * (b[i] - a[i]) for i in (0, 1)])
        result = clipped
        if not result:
            break
    return result
