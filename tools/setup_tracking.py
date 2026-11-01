"""Fetch pinned optional tracking assets without changing the active Python environment.

Run with the project's sam3-demo Python: python tools/setup_tracking.py --backend all
"""

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata as metadata
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
import zipfile


ROOT = Path(__file__).resolve().parents[1]
DEPENDENCIES = ROOT / "outputs/tracking_dependencies"
CUTIE_REVISION = "ec5cdd4cf16f75c73ad785a2f96fb97dbad4125a"
EDGETAM_REPO = "yonigozlan/EdgeTAM-hf"
EDGETAM_REVISION = "c266ce53b3fc00f0f495b583f6a116c4e57f53bb"
EDGETAM_FILES = ["config.json", "model.safetensors", "preprocessor_config.json",
                 "processor_config.json", "video_preprocessor_config.json"]
PINS = {"cutie": ["hydra-core==1.3.2", "omegaconf==2.3.0", "antlr4-python3-runtime==4.9.3"],
        "edgetam": ["timm==1.0.30"]}
PROTECTED = ["torch", "torchvision", "transformers", "numpy", "huggingface-hub"]


def versions(names):
    result = {}
    for name in names:
        try:
            result[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            result[name] = None
    return result


def checksum(path, algorithm="sha256"):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, algorithm).hexdigest()


def file_record(path):
    return {"path": str(path), "bytes": path.stat().st_size, "sha256": checksum(path)}


def download(url, path, expected=None, algorithm="sha256"):
    """Keep interrupted data in .part; publish only a complete, verified download."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file():
        if expected and not checksum(path, algorithm).startswith(expected):
            raise ValueError(f"Checksum mismatch in existing {path}; inspect it before retrying")
        return file_record(path)
    partial = path.with_name(path.name + ".part")
    offset = partial.stat().st_size if partial.exists() else 0
    request = urllib.request.Request(url, headers={"User-Agent": "project-tracking-setup/1.0"})
    if offset:
        request.add_header("Range", f"bytes={offset}-")
    try:
        response = urllib.request.urlopen(request, timeout=20)
    except urllib.error.HTTPError as exc:
        if exc.code != 416:
            raise
        request.remove_header("Range")
        response = urllib.request.urlopen(request, timeout=20)
    with response:
        resumed = response.status == 206
        if resumed and not response.headers.get("Content-Range", "").startswith(f"bytes {offset}-"):
            raise ValueError(f"Unexpected HTTP range for {path.name}; retained {partial}")
        length = response.headers.get("Content-Length")
        total = (offset if resumed else 0) + int(length) if length else None
        with partial.open("ab" if resumed else "wb") as stream:
            shutil.copyfileobj(response, stream, length=1024 * 1024)
    if total is not None and partial.stat().st_size != total:
        raise ValueError(f"Incomplete download; rerun to resume {partial}")
    if expected and not checksum(partial, algorithm).startswith(expected):
        raise ValueError(f"Checksum mismatch; inspect {partial} before retrying")
    partial.replace(path)
    return file_record(path)


def install_dependencies(backends):
    DEPENDENCIES.mkdir(parents=True, exist_ok=True)
    installed = {dist.metadata.get("Name", "").lower().replace("_", "-"): dist.version
                 for dist in metadata.distributions(path=[str(DEPENDENCIES)])}
    wanted = [pin for backend in backends for pin in PINS[backend]]
    pending = []
    for pin in wanted:
        name, version = pin.split("==")
        if name in installed and installed[name] != version:
            raise ValueError(f"{DEPENDENCIES} has {name}=={installed[name]}, expected {pin}; inspect this isolated directory")
        if name not in installed:
            pending.append(pin)
    if pending:
        command = [sys.executable, "-m", "pip", "--isolated", "install", "--target", str(DEPENDENCIES),
                   "--no-deps", "--disable-pip-version-check", "--no-input", "--retries", "0",
                   "--timeout", "20", "--index-url", "https://pypi.org/simple", *pending]
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode:
            raise RuntimeError("Optional dependency install failed: " + (result.stderr or result.stdout)[-3000:])
    installed = {dist.metadata.get("Name", "").lower().replace("_", "-"): dist.version
                 for dist in metadata.distributions(path=[str(DEPENDENCIES)])}
    if any(installed.get(pin.split("==")[0]) != pin.split("==")[1] for pin in wanted):
        raise RuntimeError("Optional dependency versions do not match the requested pins")
    return {"path": str(DEPENDENCIES), "packages": wanted, "pip_no_deps": True}


def cutie_source(cache):
    url = f"https://github.com/hkchengrex/Cutie/archive/{CUTIE_REVISION}.zip"
    archive = cache / "cutie" / f"source-{CUTIE_REVISION}.zip"
    record = download(url, archive)
    destination = ROOT / "vendor/cutie"
    destination.mkdir(parents=True, exist_ok=True)
    prefix = f"Cutie-{CUTIE_REVISION}/"
    with zipfile.ZipFile(archive) as bundle:
        # Validate every destination before writing any upstream source files.
        files = []
        for entry in bundle.infolist():
            if not entry.filename.startswith(prefix):
                raise ValueError("Unexpected root in Cutie source archive")
            relative = PurePosixPath(entry.filename[len(prefix):])
            target = (destination / str(relative)).resolve()
            if not target.is_relative_to(destination.resolve()) or "\\" in entry.filename:
                raise ValueError("Unsafe path in Cutie source archive")
            if (entry.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError("Unexpected symbolic link in Cutie source archive")
            if not entry.is_dir():
                files.append((entry, target))
        for entry, target in files:
            content = bundle.read(entry)
            if target.exists():
                if target.read_bytes() != content:
                    raise ValueError(f"Local Cutie source differs from pinned upstream: {target}")
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            partial = target.with_name(target.name + ".part")
            partial.write_bytes(content)
            partial.replace(target)
    (destination / ".source_revision").write_text(CUTIE_REVISION + "\n", encoding="utf-8")
    return {"path": str(destination), "revision": CUTIE_REVISION, "url": url, "archive": record}


def edgetam_snapshot(cache):
    from huggingface_hub import snapshot_download

    # Hub's supported downloader retains .incomplete data and atomically publishes blobs.
    path = Path(snapshot_download(EDGETAM_REPO, revision=EDGETAM_REVISION, cache_dir=str(cache),
                                  allow_patterns=EDGETAM_FILES, token=False, max_workers=2))
    return {"repo_id": EDGETAM_REPO, "revision": EDGETAM_REVISION, "path": str(path),
            "files": [file_record(path / name) for name in EDGETAM_FILES]}


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--backend", choices=["cutie", "edgetam", "all"], default="all")
    parser.add_argument("--cache-dir", type=Path, default=ROOT / "outputs/model_cache")
    args = parser.parse_args()
    cache = args.cache_dir.resolve()
    cache.mkdir(parents=True, exist_ok=True)
    backends = ["cutie", "edgetam"] if args.backend == "all" else [args.backend]
    report = {"created_utc": datetime.now(timezone.utc).isoformat(), "python": sys.executable,
              "backends": backends, "cache_dir": str(cache), "versions_before": versions(PROTECTED),
              "source_pins": {"cutie": {"repo": "https://github.com/hkchengrex/Cutie", "revision": CUTIE_REVISION},
                              "edgetam": {"repo": f"https://huggingface.co/{EDGETAM_REPO}", "revision": EDGETAM_REVISION}},
              "requested_dependencies": {name: PINS[name] for name in backends}, "steps": {}}

    def attempt(name, operation):
        print(f"Setting up {name}...", flush=True)
        try:
            report["steps"][name] = {"status": "ready", **operation()}
        except Exception as exc:
            # Public downloads need no authentication; strip query strings from any error URLs.
            message = re.sub(r"(https?://[^\s?'\"<>]+)\?[^\s'\"<>]+", r"\1?<redacted>", str(exc))
            report["steps"][name] = {"status": "failed", "error": f"{type(exc).__name__}: {message}"}
            print(f"{name}: {report['steps'][name]['error']}", file=sys.stderr, flush=True)

    attempt("optional_dependencies", lambda: install_dependencies(backends))
    if "cutie" in backends:
        attempt("cutie_source", lambda: cutie_source(cache))
        assets = [
            ("cutie-base-mega.pth", "https://github.com/hkchengrex/Cutie/releases/download/v1.0/cutie-base-mega.pth", "a6071de6136982e396851903ab4c083a", "md5"),
            ("resnet18-5c106cde.pth", "https://download.pytorch.org/models/resnet18-5c106cde.pth", "5c106cde", "sha256"),
            ("resnet50-19c8e357.pth", "https://download.pytorch.org/models/resnet50-19c8e357.pth", "19c8e357", "sha256"),
        ]
        for name, url, expected, algorithm in assets:
            attempt(name, lambda n=name, u=url, e=expected, a=algorithm:
                    {**download(u, cache / "cutie" / n, e, a), "url": u,
                     "expected_checksum": e, "checksum_algorithm": a})
    if "edgetam" in backends:
        attempt("edgetam_snapshot", lambda: edgetam_snapshot(cache))
    report["versions_after"] = versions(PROTECTED)
    report["environment_versions_unchanged"] = report["versions_before"] == report["versions_after"]
    report["ready"] = report["environment_versions_unchanged"] and all(
        row["status"] == "ready" for row in report["steps"].values())
    destination = cache / f"setup_{args.backend}.json"
    partial = destination.with_suffix(".json.part")
    partial.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    partial.replace(destination)
    print(f"Setup report: {destination}")
    if not report["ready"]:
        print("Setup incomplete. Check the report, restore public network access, and rerun this command.", file=sys.stderr)
    return 0 if report["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
