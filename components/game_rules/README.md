# Mini-rulebook geometry prototype

`validate_scene`, `measure_distance`, `line_of_sight`, and `reachable_poses`
accept plain scene dictionaries. They import no model, UI, GPU backend, or
third-party library. Distances use millimetres internally and 25.4 mm/inch.
The screen plane is x-right/y-down. `heading_deg` describes the outward normal
of the declared front edge, clockwise from screen-right. Corners retain their
cyclic order and original front-edge index after a rotation.

The frontend keeps original-video pixel anchors for trays, terrain and facing.
`RuleState.scene(..., source_to_plane=...)` projects those anchors into one
current millimetre plane before calling these queries. Pixel distance is never
used as physical distance; calibration versions remain attached to observations.

```powershell
python tools/query_rules.py scene.json --mode distance --units A1 B1
python tools/query_rules.py scene.json --mode los --units A1 B1 --output los.json
python tools/query_rules.py scene.json --mode movement --units A1 --order double
```

The JSON scene has `ruleset: "kow4-mini"`, positive `board_size_mm: [width,
depth]`, `units`, and `terrain`. Units carry `unit_id`, four cyclic rectangular
`corners_mm`, `front_edge` (0..3 or null), `height`, `speed_in`, `side`,
`unit_kind` (`ordinary`, `war_engine`, `individual`, or null), `special_rules`,
and `state: {engaged, wavering}`. Missing numeric facts become null. Missing
state flags remain unknown; movement orders that could be prohibited are
unavailable until their relevant flags are confirmed. Terrain carries
`terrain_id`, a simple `polygon_mm`, `kind` (`blocking`, `difficult`,
`obstacle`, `hill`, `decorative`), and `height`. Heights are agreed game height
levels, not physical millimetres. Metadata, including `snapshot`, warnings and
facing provenance, is preserved; scene validation never recovers IDs.

Distances are exact base-to-base polygon geometry, including zero for touching
or overlapping bases. LOS clips the target against the front edge and two
45-degree rays from its front corners. A partly intersecting target qualifies;
LOS then searches from the observer front edge to all target base edges.
Blockers matter when at least as tall as both effective endpoint heights.
Unit height gains its hill height when its centre lies on the hill; Leaper
adds one to the observer only. Multiple overlapping hills have unknown
effective height rather than an invented stacking convention. Terrain is
ignored for the particular rays originating/ending in its footprint, as on
mini-book p25. Unknown heights obstruct candidate rays conservatively.
One clear sampled ray proves a witness under the registered scene; failure
returns `uncertain`. Only an analytically disjoint front arc yields `blocked`.
Tangency is treated conservatively as a LOS obstruction. This is LOS only,
not cover, ranged-attack permission, or charge eligibility.

Movement returns a discrete subset of reachable centres **and orientations**,
each with a piecewise translation/pivot witness. It never fills a convex hull
of endpoints. Default Advance enumerates 1,715 candidate paths before
deduplication: translation lengths on four equal budget divisions and two
independent pivots in 30-degree steps, including exact +/-90-degree pivots.
Double permits one pivot and twice Speed; Back/Side permit one pivot and half
Speed. Change Facing samples a full turn. Halt preserves the pose. All pivots
retain the centre; their rotational sweeps may pass through units, terrain,
and the table edge. Pivot endpoints and final endpoints must be clear and on
the table. Translation uses the exact convex swept footprint of the rectangle,
not point sampling. It may pass through friendly bases; its final endpoint
cannot overlap any unit. Unknown-side units block traversal. A zero-angle
split in a straight path is not an artificial pivot requiring clearance.
Positive-area overlap is distinct from boundary contact (mini-book pp12/15).
The supplied Engaged flag is never inferred from contact.

Supported special rules are Fly, Pathfinder, and Leaper. Fly ignores traversal
blockers but must end clear of units and Blocking Terrain; the prototype
conservatively also clears intermediate pivot endpoints. Pathfinder exempts
Difficult Terrain only when moving Double; Obstacles still block Double.
War Engines cannot Double and treat Obstacles as Blocking Terrain. Individual
movement is explicitly unavailable, since its free facing before the order is
not implemented. Unsupported special rules are reported in warnings and do
not establish full legality. Speed must already include any manually resolved
stat changes; auras, conditional bonuses and full-book exceptions are not
resolved here. Charge and all combat/recovery/identity logic are outside scope.

Sources: supplied *Kings of War IV Mini Rulebook*, printed pp10–12 (arc,
height, LOS, distance), pp14–15 (orders/interpenetration), p19 (Engaged),
pp24–25 (terrain/hills), p33 (Wavering), p35 (War Engines/Individuals), and
pp37–38 (Fly, Pathfinder, Leaper). The front-facing LOS interpretation also
agrees with [Mantic's fourth-edition ranged-phase article](https://www.manticgames.com/news/kings-of-war-4th-edition-the-ranged-phase/).
This implements that mini-book subset; it is not verified against every
current FAQ or the complete fourth-edition rulebook. Supplied scene warnings
must travel with results: omitted trays, unregistered objects, stale positions,
estimated front direction and 180-degree facing ambiguity remain limitations
of the observation. No accuracy result is claimed.
