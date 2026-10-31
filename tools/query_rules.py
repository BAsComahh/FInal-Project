"""Query a registered scene without loading detection or segmentation models."""

import argparse
import json
from pathlib import Path
import sys

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from components.game_rules import line_of_sight, measure_distance, reachable_poses


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('scene', type=Path)
    parser.add_argument('--mode', required=True, choices=('distance', 'los', 'movement'))
    parser.add_argument('--units', required=True, nargs='+', help='Two unit IDs for distance/LOS; one for movement')
    parser.add_argument('--order', default='advance')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args(argv)
    expected = 1 if args.mode == 'movement' else 2
    if len(args.units) != expected:
        parser.error(f'{args.mode} requires {expected} unit ID(s)')
    try:
        scene = json.loads(args.scene.read_text(encoding='utf-8-sig'))
        if args.mode == 'movement':
            result = reachable_poses(scene, args.units[0], args.order)
        else:
            query = measure_distance if args.mode == 'distance' else line_of_sight
            result = query(scene, *args.units)
        content = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(content + '\n', encoding='utf-8')
        if hasattr(sys.stdout, 'reconfigure'):
            sys.stdout.reconfigure(encoding='utf-8')
        print(content)
    except (OSError, ValueError) as exc:
        parser.exit(2, f'query_rules: {exc}\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
