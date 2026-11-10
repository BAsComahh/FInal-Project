"""Local shape compatibility for the pinned Transformers EdgeTAM video port."""


def video_model_class():
    from transformers import EdgeTamVideoModel

    class EdgeTamVideoModelWithMaskScores(EdgeTamVideoModel):
        def _use_mask_as_output(self, *args, **kwargs):
            output = super()._use_mask_as_output(*args, **kwargs)
            scores = output.object_score_logits
            # HF 5.18 mask prompts omit the object axis used by decoder scores.
            if scores.ndim == 2 and scores.shape[-1] == 1:
                output.object_score_logits = scores.unsqueeze(-1)
            elif scores.ndim != 3 or scores.shape[-2:] != (1, 1):
                raise RuntimeError(f"Unsupported EdgeTAM mask score shape: {tuple(scores.shape)}")
            return output

    return EdgeTamVideoModelWithMaskScores
