"""Prepare pinned DVMNet assets in an ignored cache, without changing the Python environment."""

import argparse
from html.parser import HTMLParser
import importlib.metadata as metadata
import json
from pathlib import Path
import shutil
import subprocess
import sys
import urllib.parse
import urllib.request

from components.facing.dvmnet import REVISION, SOURCE_HASHES, WEIGHT_HASHES
from tools.setup_tracking import ROOT, PROTECTED, checksum, download, versions


def checkpoint_url():
    class Form(HTMLParser):
        def __init__(self):
            super().__init__()
            self.action, self.inputs = None, {}

        def handle_starttag(self, tag, attributes):
            attributes = dict(attributes)
            if tag == "form":
                self.action = attributes.get("action")
            if tag == "input" and "name" in attributes:
                self.inputs[attributes["name"]] = attributes.get("value", "")

    url = "https://drive.usercontent.google.com/download?id=1ENeRWvMNyvYN4QmhtEaAkvLR1FbQstp4&export=download"
    with urllib.request.urlopen(url, timeout=20) as response:
        if "text/html" not in response.headers.get("Content-Type", ""):
            return url
        page = response.read(100_000).decode("utf-8")
    form = Form()
    form.feed(page)
    if form.action != "https://drive.usercontent.google.com/download" or form.inputs.get("id") != "1ENeRWvMNyvYN4QmhtEaAkvLR1FbQstp4":
        raise ValueError("Official checkpoint download needs manual inspection; unexpected confirmation page")
    return form.action + "?" + urllib.parse.urlencode(form.inputs)


def setup(cache, reuse=None):
    cache = cache.resolve()
    before = versions(PROTECTED)
    assets = {"source/" + path: digest for path, digest in SOURCE_HASHES.items()}
    assets.update(WEIGHT_HASHES)
    assets.update({"source/croco/LICENSE": "2c701261a5f4a07764b29aa85caf2a6187408a53b59f2c2a10940d74c9f6c8f1",
                   "source/croco/NOTICE": "f63d27ce6c6134e816655693dbcb81fdbd279158ef681797fb6e1e217d353821"})
    for relative, digest in assets.items():
        path = cache / relative
        if path.is_file():
            if checksum(path) != digest:
                raise ValueError(f"Existing facing asset differs; inspect {path}")
            continue
        original = reuse / relative if reuse is not None else None
        if original is not None and original.is_file():
            if checksum(original) != digest:
                raise ValueError(f"Reuse asset differs from the pinned version: {original}")
            path.parent.mkdir(parents=True, exist_ok=True)
            partial = path.with_name(path.name + ".part")
            shutil.copyfile(original, partial)
            partial.replace(path)
        else:
            if relative == "models/checkpoint_co3d.ckpt":
                url = checkpoint_url()
            elif relative in WEIGHT_HASHES:
                url = "https://download.europe.naverlabs.com/ComputerVision/CroCo/CroCo_V2_ViTBase_BaseDecoder.pth"
            else:
                url = f"https://raw.githubusercontent.com/sailor-z/DVMNet/{REVISION}/" + relative.removeprefix("source/")
            download(url, path, expected=digest)
        print(f"Ready: {relative}", flush=True)
    dependencies = cache / "dependencies"
    installed = {d.metadata["Name"].lower(): d.version for d in metadata.distributions(path=[str(dependencies)])}
    if installed.get("einops") not in (None, "0.8.1"):
        raise ValueError("Facing cache has a different einops version; inspect it before updating")
    if "einops" not in installed:
        reusable = reuse / "dependencies" if reuse is not None else None
        if reusable is not None and (reusable / "einops-0.8.1.dist-info").is_dir():
            for name in ("einops", "einops-0.8.1.dist-info"):
                shutil.copytree(reusable / name, dependencies / name, dirs_exist_ok=True)
        else:
            subprocess.run([sys.executable, "-m", "pip", "--isolated", "install", "--target", str(dependencies),
                            "--no-deps", "--disable-pip-version-check", "einops==0.8.1"], check=True)
    after = versions(PROTECTED)
    if before != after:
        raise RuntimeError("Protected environment package versions changed")
    report = {"ready": True, "revision": REVISION, "assets": assets, "dependencies": {"einops": "0.8.1"},
              "environment_versions_unchanged": before == after,
              "license_note": "Upstream has no top-level license; retain CroCo LICENSE/NOTICE. Assets remain external and ignored."}
    (cache / "setup.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Facing assets ready: {cache}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache-dir", type=Path, default=ROOT / "outputs/model_cache/dvmnet")
    parser.add_argument("--reuse-experiment", type=Path, help="Reuse the existing downloaded experiment assets")
    args = parser.parse_args()
    setup(args.cache_dir, args.reuse_experiment)


if __name__ == "__main__":
    main()
