> **This is an unofficial fork of Frigate NVR. It is not affiliated with, endorsed by, or associated with Frigate, Inc. in any way. "Frigate" and the Frigate logo are trademarks of Frigate, Inc.**

# Meadow-View — Motion & Region Enhancements for Frigate

This fork adds pluggable motion detection and configurable region handling on top of upstream Frigate. All new options are opt-in; the defaults match upstream behaviour.

## MOG2 Motion Detection

An alternative motion detector based on OpenCV's MOG2 background subtractor. MOG2 is especially good at suppressing hard shadows and wind-blown leaves, which means `threshold` can usually come down compared to the default `improved` method.

Recommended starting point:

```yaml
motion:
  method: mog2
  frame_height: 300
  use_motion_region_grid: false
```

Other settings (`threshold`, `contour_area`, `improve_contrast`, `frame_alpha`) should be tuned to taste after reviewing both daytime and nighttime footage.

## Minimum Region Size

Set `minimum_region: native` under `detect:` to always use the full model input size as the smallest detection region. This is recommended for models with strong small-object detection such as YOLO26 with STAL, where the upstream `auto` logic (which halves the region for models > 320px) would discard useful context.

## Region Merging

Motion regions are now scored by motion area and sorted so the most significant regions are processed first. Overlapping motion and tracked-object regions are aggressively merged, and a deduplication pass removes any region already covered by a larger one. This reduces redundant detector invocations without sacrificing coverage.

## Configuration Reference

See [MEADOWVIEW_CONFIGURATION.md](MEADOWVIEW_CONFIGURATION.md) for the complete configuration reference with all available options, defaults, and usage guidance.

---

<p align="center">
  <img align="center" alt="logo" src="docs/static/img/branding/frigate.png">
</p>

# Frigate NVR™ - Realtime Object Detection for IP Cameras

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

<a href="https://hosted.weblate.org/engage/frigate-nvr/">
<img src="https://hosted.weblate.org/widget/frigate-nvr/language-badge.svg" alt="Translation status" />
</a>

\[English\] | [简体中文](https://github.com/blakeblackshear/frigate/blob/dev/README_CN.md)

A complete and local NVR designed for [Home Assistant](https://www.home-assistant.io) with AI object detection. Uses OpenCV and Tensorflow to perform realtime object detection locally for IP cameras.

Use of a GPU or AI accelerator is highly recommended. AI accelerators will outperform even the best CPUs with very little overhead. See Frigate's supported [object detectors](https://docs.frigate.video/configuration/object_detectors/).

- Tight integration with Home Assistant via a [custom component](https://github.com/blakeblackshear/frigate-hass-integration)
- Designed to minimize resource use and maximize performance by only looking for objects when and where it is necessary
- Leverages multiprocessing heavily with an emphasis on realtime over processing every frame
- Uses a very low overhead motion detection to determine where to run object detection
- Object detection with TensorFlow runs in separate processes for maximum FPS
- Communicates over MQTT for easy integration into other systems
- Records video with retention settings based on detected objects
- 24/7 recording
- Re-streaming via RTSP to reduce the number of connections to your camera
- WebRTC & MSE support for low-latency live view

## Documentation

View the documentation at https://docs.frigate.video

## Donations

If you would like to make a donation to support development, please use [Github Sponsors](https://github.com/sponsors/blakeblackshear).

## License

This project is licensed under the **MIT License**.

- **Code:** The source code, configuration files, and documentation in this repository are available under the [MIT License](LICENSE). You are free to use, modify, and distribute the code as long as you include the original copyright notice.
- **Trademarks:** The "Frigate" name, the "Frigate NVR" brand, and the Frigate logo are **trademarks of Frigate, Inc.** and are **not** covered by the MIT License.

Please see our [Trademark Policy](TRADEMARK.md) for details on acceptable use of our brand assets.

## Screenshots

### Live dashboard

<div>
<img width="800" alt="Live dashboard" src="https://github.com/blakeblackshear/frigate/assets/569905/5e713cb9-9db5-41dc-947a-6937c3bc376e">
</div>

### Streamlined review workflow

<div>
<img width="800" alt="Streamlined review workflow" src="https://github.com/blakeblackshear/frigate/assets/569905/6fed96e8-3b18-40e5-9ddc-31e6f3c9f2ff">
</div>

### Multi-camera scrubbing

<div>
<img width="800" alt="Multi-camera scrubbing" src="https://github.com/blakeblackshear/frigate/assets/569905/d6788a15-0eeb-4427-a8d4-80b93cae3d74">
</div>

### Built-in mask and zone editor

<div>
<img width="800" alt="Built-in mask and zone editor" src="https://github.com/blakeblackshear/frigate/assets/569905/d7885fc3-bfe6-452f-b7d0-d957cb3e31f5">
</div>

## Translations

We use [Weblate](https://hosted.weblate.org/projects/frigate-nvr/) to support language translations. Contributions are always welcome.

<a href="https://hosted.weblate.org/engage/frigate-nvr/">
<img src="https://hosted.weblate.org/widget/frigate-nvr/multi-auto.svg" alt="Translation status" />
</a>

---

**Copyright © 2026 Frigate, Inc.**
