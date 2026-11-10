"""Load pinned external DVMNet in a private namespace, preserving its model math."""

import ast
import hashlib
from pathlib import Path
import sys
import types

import numpy as np

from components.homography import transform_points
from .geometry import masked_source_crop, select_front_edge

REVISION = "cebe92cc31c2db66e8f4cd86f5462b751415eb29"
SOURCE_HASHES = {
    "modules/dvmnet_modules.py": "118f24fc7227828bab66309446c00748501d5ff91b84cd8ca7ec3e58071a6069",
    "utils.py": "ab8b76f7ff110406f76089bb413ebf4d9e016dd898c2693d77447259912b6acc",
    "croco/models/blocks.py": "3f634e51154c75800df681c6f37fd74e979386483346cccf3cf33b97e35b4080",
    "croco/models/pos_embed.py": "7e3acdf9f7cdfc24598632505f941f01e72f6680ef8f4ad611df64d7f61f7555",
    "croco/models/croco.py": "2df8bfb0c2491472a44ac9ef7096a530a05373822f1013074fea4888e5af086a",
    "croco/models/masking.py": "d1c13bc306b2bae4be22fcb7123f8ec5821ad7c9d409d93a83ff3cb07fee1768",
}
WEIGHT_HASHES = {
    "models/checkpoint_co3d.ckpt": "1931682066ea69d894adf98922a7b18aaf30e698ab2ccc892da8742418156e8a",
    "source/croco/CroCo_V2_ViTBase_BaseDecoder.pth": "f5f338ebca4257372d543941065801ef518cea9abced737f742f094a60f8a650",
}


def _official_network(cache):
    package = "_tabletop_dvmnet_" + hashlib.sha256(str(cache).encode()).hexdigest()[:12]
    if package + ".core" in sys.modules:
        return sys.modules[package + ".core"].DVMNet
    source = cache / "source"
    for path, digest in SOURCE_HASHES.items():
        if hashlib.sha256((source / path).read_bytes()).hexdigest() != digest:
            raise ValueError(f"DVMNet source differs from pinned upstream: {path}")
    for suffix in ("", ".models"):
        module = types.ModuleType(package + suffix)
        module.__path__ = []  # No CUDA extension imports; official torch RoPE fallback is used.
        sys.modules[module.__name__] = module

    class Imports(ast.NodeTransformer):
        def visit_ImportFrom(self, node):
            if node.module == "pytorch3d.transforms":
                return None  # These names are unused by the inference network.
            if node.module == "utils" or (node.module or "").startswith("models."):
                node.module = package + "." + node.module
            return node

        def visit_Call(self, node):
            self.generic_visit(node)
            if (isinstance(node.func, ast.Name) and node.func.id == "print" and node.args
                    and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str)
                    and node.args[0].value.startswith("Warning, cannot find cuda-compiled version of RoPE2D")):
                node.args[0].value = "DVMNet: using torch RoPE on the selected inference device."
            if (isinstance(node.func, ast.Attribute) and node.func.attr == "load" and node.args
                    and isinstance(node.args[0], ast.Constant)
                    and node.args[0].value == "./croco/CroCo_V2_ViTBase_BaseDecoder.pth"):
                node.args[0].value = str(source / "croco/CroCo_V2_ViTBase_BaseDecoder.pth")
                node.keywords.extend([ast.keyword(arg="weights_only", value=ast.Constant(True)),
                                      ast.keyword(arg="mmap", value=ast.Constant(True))])
            return node

    paths = [("utils.py", ".utils"), ("croco/models/blocks.py", ".models.blocks"),
             ("croco/models/pos_embed.py", ".models.pos_embed"), ("croco/models/masking.py", ".models.masking"),
             ("croco/models/croco.py", ".models.croco"), ("modules/dvmnet_modules.py", ".core")]
    try:
        for path, suffix in paths:
            filename = source / path
            tree = ast.parse(filename.read_text(encoding="utf-8"))
            # Upstream script setup must not change the application's import path or TF32 policy.
            tree.body = [node for node in tree.body if not ast.unparse(node).startswith(
                ("sys.path.append(", "torch.backends.cuda.matmul.allow_tf32 ="))]
            tree = ast.fix_missing_locations(Imports().visit(tree))
            module = types.ModuleType(package + suffix)
            module.__file__ = str(filename)
            sys.modules[module.__name__] = module
            exec(compile(tree, str(filename), "exec"), module.__dict__)
    except Exception:
        for name in list(sys.modules):
            if name == package or name.startswith(package + "."):
                del sys.modules[name]
        raise
    return sys.modules[package + ".core"].DVMNet


class FacingEstimator:
    def __init__(self, cache, device=None, *, margin_deg=20.0):
        self.cache, self.device = Path(cache).resolve(), device
        self.margin_deg = float(margin_deg)
        if not np.isfinite(self.margin_deg) or not 0 <= self.margin_deg < 90:
            raise ValueError("Facing edge margin must be in [0, 90) degrees")
        self.model = self.error = self.preprocess = None

    def load(self):
        if self.model is not None:
            return
        import torch
        from torchvision import transforms

        dependencies = self.cache / "dependencies"
        if dependencies.is_dir() and str(dependencies) not in sys.path:
            sys.path.insert(0, str(dependencies))
        for name, digest in WEIGHT_HASHES.items():
            with (self.cache / name).open("rb") as stream:
                if hashlib.file_digest(stream, "sha256").hexdigest() != digest:
                    raise ValueError(f"DVMNet weight checksum differs: {name}")
        model = _official_network(self.cache)(transport="cosine", mask="both")
        checkpoint = torch.load(self.cache / "models/checkpoint_co3d.ckpt", map_location="cpu", weights_only=True, mmap=True)
        model.load_state_dict({key.removeprefix("model."): value for key, value in checkpoint["state_dict"].items()}, strict=True)
        self.model = model.to(self.device).eval().requires_grad_(False)
        self.preprocess = transforms.Compose([transforms.ToTensor(), transforms.Resize((224, 224)),
                                             transforms.Normalize([.485, .456, .406], [.229, .224, .225])])
        # Warm up before first playback; otherwise first facing adds a large kernel delay.
        if next(self.model.parameters()).device.type == "cuda":
            sample = torch.zeros(1, 3, 224, 224, device=self.device)
            with torch.inference_mode():
                self.model(sample, sample)
            torch.cuda.synchronize(self.device)
        self.error = None

    def rotation(self, reference, current):
        import torch
        from PIL import Image

        if self.model is None:
            raise ValueError(self.error or "DVMNet facing weights are unavailable; run python -m tools.setup_facing")
        first = self.preprocess(Image.fromarray(reference))[None].to(self.device)
        second = self.preprocess(Image.fromarray(current))[None].to(self.device)
        with torch.inference_mode():
            return self.model(first, second)[4][0].float().cpu().numpy()

    def estimate(self, prediction, raw_frame, metadata, context, references, excluded=(), targets=None):
        results = {}
        masks = dict(zip(prediction["object_ids"], prediction["masks"]))
        for obj, reference in references.items():
            if targets is not None and obj not in targets:
                continue
            row = {"status": "unknown", "unit_id": reference["unit_id"], "reference_id": reference["reference_id"],
                   "frame_index": metadata["frame_index"], "calibration_version": metadata.get("calibration_version"),
                   "reference_frame_index": reference["frame_index"], "reference_calibration_version": reference["calibration_version"]}
            try:
                if reference.get("error"):
                    raise ValueError(reference["error"])
                if obj in excluded or obj not in masks or obj not in prediction.get("trays", {}):
                    raise ValueError("Facing requires accepted tracking and current tray geometry")
                if list(raw_frame.shape[1::-1]) != reference["source_size"]:
                    raise ValueError("Facing reference uses a different source canvas")
                crop = masked_source_crop(raw_frame, masks[obj], metadata)
                rotation = self.rotation(reference["crop_rgb"], crop)
                tray = prediction["trays"][obj]
                mapping = np.asarray(context["image_to_plane"]) @ np.asarray(metadata["homography"]["matrix"])
                corners = transform_points(tray["corners_plane"], np.linalg.inv(mapping))
                row.update(select_front_edge(rotation, reference["source_ray"], corners, tray["corners_plane"],
                                             reference["front_width_mm"], margin_deg=self.margin_deg))
            except Exception as error:
                row.update(status="unknown", reason=str(error))
            results[obj] = row
        return results
