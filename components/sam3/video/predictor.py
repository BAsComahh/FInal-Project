"""Official Transformers SAM3 video model, using its streaming memory session."""

import cv2
import numpy as np
from PIL import Image
from time import perf_counter


class VideoPredictor:
    def __init__(self, model_id="facebook/sam3", device=None, *, profile=False):
        self.model_id, self.device = model_id, device
        self.profile = profile
        self.model = self.processor = self.session = None
        self.load_progress = None
        self.index = 0
        self.source_frame = None

    def load(self):
        if self.model is not None:
            return
        self.load_progress = ("Preparing model", None, None)
        try:
            import torch
            from transformers import Sam3TrackerVideoModel, Sam3TrackerVideoProcessor
            from .loading import weight_loading_progress

            if self.device is None:
                self.device = (f"cuda:{max(range(torch.cuda.device_count()), key=lambda i: torch.cuda.get_device_properties(i).total_memory)}"
                               if torch.cuda.is_available() else "cpu")
            self.load_progress = ("Loading processor", None, None)
            self.processor = Sam3TrackerVideoProcessor.from_pretrained(self.model_id, local_files_only=True)

            def report(progress):
                self.load_progress = progress

            self.load_progress = ("Loading weights", None, None)
            with weight_loading_progress(report):
                model, info = Sam3TrackerVideoModel.from_pretrained(self.model_id, local_files_only=True, output_loading_info=True)
            if info.get("missing_keys") or info.get("mismatched_keys"):
                raise ValueError("The checkpoint is missing SAM3 video weights")
            self.load_progress = (f"Moving weights to {self.device}", None, None)
            self.model = model.to(device=self.device, dtype=torch.float32).eval()
        finally:
            self.load_progress = None

    def reset(self):
        self.session = None
        self.index = 0
        self.source_frame = None

    def _select_frame(self, source_frame, *, advance=False):
        if source_frame is None:
            if advance:
                self.index += 1
            return
        if self.source_frame is not None:
            if source_frame < self.source_frame:
                raise ValueError("Reset the video session before going backwards")
            if source_frame > self.source_frame:
                self.index += 1
        self.source_frame = source_frame

    def _session(self):
        import torch

        self.load()
        if self.session is None:
            self.session = self.processor.init_video_session(
                inference_device=self.device, inference_state_device="cpu",
                video_storage_device="cpu", processing_device="cpu", dtype=torch.float32,
            )

    def prepare_initial_frame(self, frame, *, source_frame=None):
        """Precompute the real first frame using the installed backend's cache API."""
        import torch

        self._session()
        if self.index != 0 or self.session.obj_ids:
            raise ValueError("Prepare the initial frame before adding objects")
        self.load_progress = ("Preparing first-frame features", None, None)
        try:
            self._select_frame(source_frame)
            pixels = self._frame_inputs(frame).pixel_values[0]
            self.session.add_new_frame(pixels, frame_idx=self.index)
            with torch.inference_mode():
                features = self.model.get_image_features(self.session.get_frame(self.index).unsqueeze(0), return_dict=True)
                # These keys match Transformers 5.18.0 _prepare_vision_features.
                self.session.cache.cache_vision_features(self.index, {
                    "vision_feats": features.fpn_hidden_states,
                    "vision_pos_embeds": features.fpn_position_encoding,
                })
            if torch.device(self.device).type == "cuda":
                torch.cuda.synchronize(self.device)
        finally:
            self.load_progress = None

    def _frame_inputs(self, frame):
        rgb = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        return self.processor(images=rgb, return_tensors="pt")

    def _infer(self, frame):
        import torch

        def sync():
            if self.profile and torch.device(self.device).type == "cuda":
                torch.cuda.synchronize(self.device)

        sync()
        started = perf_counter()
        inputs = self._frame_inputs(frame)
        prepared = perf_counter()
        with torch.inference_mode():
            outputs = self.model(inference_session=self.session, frame_idx=self.index, frame=inputs.pixel_values[0])
            sync()
            inferred = perf_counter()
            masks = self.processor.post_process_masks([outputs.pred_masks], original_sizes=inputs.original_sizes)[0]
        height, width = frame.shape[:2]
        masks = masks.detach().cpu().numpy().astype(bool).reshape(-1, height, width)
        logits = outputs.object_score_logits
        scores = None if logits is None else logits.detach().float().cpu().reshape(-1).tolist()
        finished = perf_counter()
        return {"object_ids": list(outputs.object_ids), "masks": masks, "frame_idx": self.index,
                "object_score_logits": scores,
                "inference_call_count": 1,
                "timings_seconds": {"preprocess": prepared - started, "model_call": inferred - prepared,
                                    "mask_postprocess_transfer": finished - inferred},
                "timing_gpu_synchronized": self.profile and torch.device(self.device).type == "cuda"}

    def click(self, frame, point, *, object_id=1, positive=True, source_frame=None):
        self._session()
        height, width = frame.shape[:2]
        x, y = map(float, point)
        if not np.isfinite([x, y]).all() or not (0 <= x < width and 0 <= y < height):
            raise ValueError("Click must be inside the image")
        if not positive and object_id not in self.session.obj_ids:
            raise ValueError("Start a new object with a positive click")
        self._select_frame(source_frame)
        self.processor.add_inputs_to_inference_session(
            inference_session=self.session, frame_idx=self.index, obj_ids=object_id,
            input_points=[[[[x, y]]]], input_labels=[[[int(positive)]]],
            original_size=(height, width), clear_old_inputs=False,
        )
        return self._infer(frame)

    def propagate(self, frame, *, source_frame=None):
        if self.session is None or not self.session.obj_ids:
            raise ValueError("Click an object before propagating")
        self._select_frame(source_frame, advance=True)
        return self._infer(frame)

    def initialize(self, frame, object_ids, masks, *, source_frame=None):
        """Start a new coordinate-space session from masks using the official API."""
        object_ids = list(object_ids)
        masks = np.asarray(masks)
        if (not object_ids or len(set(object_ids)) != len(object_ids)
                or masks.dtype != np.bool_ or masks.shape != (len(object_ids), *frame.shape[:2])):
            raise ValueError("Initial masks must be bool arrays matching the distinct object IDs and frame.")
        self.reset()
        self._session()
        self._select_frame(source_frame)
        self.processor.add_inputs_to_inference_session(
            inference_session=self.session, frame_idx=0, obj_ids=list(object_ids),
            input_masks=list(masks), original_size=frame.shape[:2],
        )
        return self._infer(frame)

    def replace_initial_points(self, frame, clicks, *, source_frame=None, changed_ids=None):
        """Replace registration prompts before propagation using official APIs.

        Unchanged objects reuse their cached conditioning masks. Removing an
        object uses reset_tracking_data(), which retains the image cache, then
        submits the surviving objects on the same initial frame, grouped by
        point count so padding cannot change the model's multimask selection.
        """
        if self.index != 0 or (self.session is not None
                              and any(self.session.frames_tracked_per_obj.values())):
            raise ValueError("Point editing is only supported before video propagation")
        if self.source_frame is not None and source_frame != self.source_frame:
            raise ValueError("Point editing must stay on the initial registration frame")
        if any(click["video_frame"] != source_frame for click in clicks):
            raise ValueError("Registration prompts must belong to the same initial video frame")
        self._select_frame(source_frame)
        groups = {}
        for click in clicks:
            groups.setdefault(click["object_id"], []).append(click)
        if self.session is None and not groups:
            return None
        self._session()
        if set(groups) != set(self.session.obj_ids):
            self.session.reset_tracking_data()
            changed_ids = list(groups)
        elif changed_ids is None:
            changed_ids = list(groups)
        if not groups:
            return None
        batches = {}
        for obj in changed_ids:
            batches.setdefault(len(groups[obj]), []).append(obj)
        prediction = None
        timings, inference_calls = {}, 0
        for objects in batches.values():
            self.processor.add_inputs_to_inference_session(
                inference_session=self.session, frame_idx=self.index, obj_ids=objects,
                input_points=[[[click["point"] for click in groups[obj]] for obj in objects]],
                input_labels=[[[int(click["positive"]) for click in groups[obj]] for obj in objects]],
                original_size=frame.shape[:2], clear_old_inputs=True,
            )
            prediction = self._infer(frame)
            for name, value in prediction["timings_seconds"].items():
                timings[name] = timings.get(name, 0) + value
            inference_calls += prediction["inference_call_count"]
        if prediction is not None:
            prediction.update(timings_seconds=timings, inference_call_count=inference_calls)
        return prediction if prediction is not None else self._infer(frame)
