"""Meadow-view sidecar for video.py — parallel region detection."""

import numpy as np

from frigate.config.camera.detect import DetectConfig
from frigate.detectors.detector_config import ModelConfig
from frigate.util.object import create_tensor_input, is_object_filtered


def detect_regions(
    detect_config: DetectConfig,
    object_detector,
    frame: np.ndarray,
    model_config: ModelConfig,
    regions: list,
    objects_to_track: list,
    object_filters: dict,
) -> list:
    """Submit all regions in parallel via slotted detector, return detections.

    Parallel equivalent of the serial `for region in regions: detect(...)` loop
    in video.py. Prepares all tensors up front, submits them through the slotted
    detector, then post-processes each region's results with the same coordinate
    remapping as the original detect() function.
    """
    tensors = [create_tensor_input(frame, model_config, r) for r in regions]
    all_region_detections = object_detector.detect_parallel(tensors)

    detections = []
    for region, region_detections in zip(regions, all_region_detections):
        for d in region_detections:
            box = d[2]
            size = region[2] - region[0]
            x_min = int(max(0, (box[1] * size) + region[0]))
            y_min = int(max(0, (box[0] * size) + region[1]))
            x_max = int(min(detect_config.width - 1, (box[3] * size) + region[0]))
            y_max = int(min(detect_config.height - 1, (box[2] * size) + region[1]))

            # ignore objects that were detected outside the frame
            if (x_min >= detect_config.width - 1) or (
                y_min >= detect_config.height - 1
            ):
                continue

            width = x_max - x_min
            height = y_max - y_min
            area = width * height
            ratio = width / max(1, height)
            det = (d[0], d[1], (x_min, y_min, x_max, y_max), area, ratio, region)
            if is_object_filtered(det, objects_to_track, object_filters):
                continue
            detections.append(det)
    return detections
