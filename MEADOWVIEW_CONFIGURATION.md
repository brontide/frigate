# Meadow-View Configuration Reference

All meadow-view options are **opt-in**. When omitted, defaults match upstream Frigate behaviour. Options under `motion:` and `detect:` can be set at the top level (global) or per-camera.

---

## Motion Detection

### `method`

| | |
|---|---|
| **YAML path** | `motion.method` |
| **Type** | string enum — `improved` \| `mog2` |
| **Default** | `improved` |
| **Scope** | global or per-camera |

Selects the motion detection algorithm.

- **`improved`** — The stock Frigate frame-differencing detector. Well-tested and lightweight.
- **`mog2`** — An alternative based on OpenCV's MOG2 (Mixture of Gaussians) background subtractor. MOG2 builds a statistical model of the background over time, which makes it better at suppressing hard shadows and repetitive motion like wind-blown foliage. Because MOG2 already handles these cases, you can often lower `threshold` compared to the default method.

Changing `method` requires a camera process restart.

```yaml
motion:
  method: mog2
```

### `region_multiplier`

| | |
|---|---|
| **YAML path** | `motion.region_multiplier` |
| **Type** | float |
| **Range** | 1.0 – 4.0 |
| **Default** | `1.35` |
| **Scope** | global or per-camera |

Expansion factor applied to motion bounding boxes before they are sent to the object detector. A value of `1.0` sends exactly the motion region with no padding; higher values add proportionally more context around the detected motion.

Increasing this can help the detector identify objects that are partially outside the raw motion area, at the cost of larger (and therefore fewer) regions per frame.

```yaml
motion:
  region_multiplier: 1.5
```

### `use_motion_region_grid`

| | |
|---|---|
| **YAML path** | `motion.use_motion_region_grid` |
| **Type** | boolean |
| **Default** | `true` |
| **Scope** | global or per-camera |

When `true`, motion regions are sized using a historical region grid that learns typical object sizes from past detections across an 8×8 grid of frame cells. This helps the detector receive appropriately-sized regions based on where in the frame the motion occurred (e.g., objects far from the camera produce smaller regions).

Set to `false` to disable the grid entirely. In that case, regions are sized purely from the motion bounding box and `region_multiplier`. This is useful when switching to MOG2, which already produces tighter, more reliable motion boxes that don't benefit as much from historical sizing.

```yaml
motion:
  use_motion_region_grid: false
```

---

## Object Detection

### `minimum_region`

| | |
|---|---|
| **YAML path** | `detect.minimum_region` |
| **Type** | string or integer |
| **Accepted values** | `"auto"`, `"native"`, or a positive integer (pixels) |
| **Default** | `"auto"` |
| **Scope** | global or per-camera |

Controls the smallest detection region (in pixels) that will be sent to the object detector.

- **`"auto"`** — Upstream default behaviour. For models with input size > 320 px, the minimum region is half the model input size. For models ≤ 320 px, the full model input size is used. This is a good general-purpose setting.
- **`"native"`** — Always uses the full model input size as the minimum region. Recommended for modern models with strong small-object detection (e.g., YOLO with STAL), where halving the region discards useful context and hurts accuracy on distant or small objects.
- **Integer** — A fixed pixel value. The value is automatically aligned to a multiple of 4. Use this for fine-grained control when you know the exact region size that works best for your model and camera layout.

```yaml
detect:
  minimum_region: native
```

---

## Region Deduplication

Region deduplication is **always active** and has no configuration toggle. After all motion and tracked-object regions are assembled for a frame, a deduplication pass runs to remove redundant regions:

1. Regions are sorted by area (largest first).
2. Tracked-object regions are prioritised over motion regions.
3. Any region with an IoU (Intersection over Union) ≥ 0.85 against a larger region is dropped.

This reduces redundant detector invocations without sacrificing detection coverage.

---

## UI / Metrics

### `inference_threshold`

| | |
|---|---|
| **YAML path** | `ui.inference_threshold.warning` / `ui.inference_threshold.error` |
| **Type** | integer (milliseconds) |
| **Defaults** | `warning: 50`, `error: 100` |
| **Scope** | global only |

Controls the colour-coded thresholds for detector inference speed displayed on the System metrics page.

- **`warning`** — Inference times above this value (in ms) are highlighted as a warning in the UI.
- **`error`** — Inference times above this value (in ms) are highlighted as an error in the UI.

Adjust these if your detector hardware has different performance characteristics. For example, a CPU-only setup might raise both thresholds, while a fast Coral TPU setup might lower them.

```yaml
ui:
  inference_threshold:
    warning: 75
    error: 150
```

---

## Full Example

A complete example showing every meadow-view option with non-default values:

```yaml
motion:
  method: mog2
  region_multiplier: 1.5
  use_motion_region_grid: false

detect:
  minimum_region: native

ui:
  inference_threshold:
    warning: 75
    error: 150
```
