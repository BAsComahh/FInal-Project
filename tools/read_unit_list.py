"""Read Mantic Companion army-list PDFs and export a registration type catalog."""

import argparse
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from components.registration import read_unit_list_pdfs


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdfs", nargs="+", type=Path, help="One or more text-based army-list PDFs")
    parser.add_argument("--sides", nargs="+", help="Optional side labels, one per PDF in the same order")
    parser.add_argument("--output", type=Path,
                        default=Path(__file__).resolve().parents[1] / "outputs/unit_lists/units.json")
    args = parser.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    try:
        if args.output.resolve() in [path.resolve() for path in args.pdfs]:
            raise ValueError("The output must not overwrite an input PDF.")
        if args.output.suffix.lower() != ".json":
            raise ValueError("The output must be a .json file.")
        catalog = read_unit_list_pdfs(args.pdfs, sides=args.sides)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory(prefix=".pending_unit_list_", dir=args.output.parent) as temporary:
            pending = Path(temporary) / "units.json"
            pending.write_text(json.dumps(catalog, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
            pending.replace(args.output)
        for source in catalog["sources"]:
            totals = source["totals"]
            print(f"{Path(source['pdf']).name}: {totals['units']} units / {totals['points']} points / US {totals['unit_strength']} (verified)")
        print("Type Qty  Sp  Ht   Pts  Tray mm     Unit / formation / purchased options")
        for record in catalog["unit_types"]:
            attributes = record["attributes"]
            size = record.get("dimension")
            footprint = f"{size['width_mm']:g}x{size['depth_mm']:g}" if size else "unknown"
            print(f"{record['type_id']:<4} {record['listed_count']:>3} {attributes['speed_in']:>3g} {attributes['height']:>3} "
                  f"{attributes['points']:>5}  {footprint:<11} {record['name']}")
        print(f"Saved: {args.output.resolve()}")
        for warning in catalog["warnings"]:
            print(f"Note: {warning}")
        return 0
    except (ImportError, OSError, ValueError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    raise SystemExit(main())
