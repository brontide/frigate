# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

This project is a patchset on top of Frigate; a local NVR (Network Video Recorder) with real-time AI object detection for IP cameras. The backend is Python 3.11+ (FastAPI, multiprocessing-heavy), the frontend is React 18 + TypeScript + Vite, and the system runs as a Docker container.

## Style and Editing

This is a passion project, personal in nature and I would love to get this pulled upstream but so far have been unsuccessful so I've been keeping it out of the main repo. My goal is to improve function as much as possible without making this a nightmare to rebase regularly.

* DO: Minimize edits to upstream files to make rebasing easier
* DO: When creating whole new functions, make a side-car file such as video_mw.py and import that into the main file.
* DO: When creating configuration items, make them opt-in with the default of what the code currently has
* DO NOT: Remove functions from upstream files
* DO: Maintain comments where appropriate — pythonic code may not require any, but more complex logic should have a brief comment
* DO: Group and commit changes by function, minimizing interactions between unrelated changes
* DO: Run `ruff check --fix` and `ruff format` on Python code before committing (see commands below)
* DO: When adding or changing configuration items, update `MEADOWVIEW_CONFIGURATION.md` and `README.md` to reflect the changes in a follow-up commit after the code commit

### Branches

meadow-watch: Tracks upstream/master 

meadow-watch-dev: Tracks upstream/dev

## Commands

### Backend

```bash
# Build local Docker image
make local

# Run tests (builds first, then runs in container)
make run_tests

# Run a single Python test module (inside devcontainer or after building)
python3 -m unittest frigate.test.test_<module_name> -v

# Type checking (runs as part of make run_tests)
python3 -m mypy --config-file frigate/mypy.ini frigate

# Lint and auto-fix Python code (run before committing)
ruff check --fix frigate migrations docker *.py

# Format Python code (run before committing)
ruff format frigate migrations docker *.py
```

### Frontend (from `web/`)

```bash
# Dev server (requires a running Frigate backend)
PROXY_HOST=localhost:5000 npm run dev

# Lint
npm run lint
npm run lint:fix

# Format
npm run prettier:write

# Tests
npm run test

# Coverage
npm run coverage
```

## Architecture

### Backend (Python)

The core is a multiprocessing architecture where each camera runs in its own process(es):

- `frigate/app.py` — Main application entrypoint; starts and coordinates all processes
- `frigate/api/` — FastAPI REST endpoints and WebSocket handlers
- `frigate/config/` — YAML config loading and Pydantic validation
- `frigate/camera/` — Per-camera process management and RTSP stream ingestion
- `frigate/detectors/` — AI object detection backends (Coral, OpenVINO, ONNX, TensorRT, etc.)
- `frigate/motion/` — Low-res motion detection that gates the more expensive object detection
- `frigate/track/` — Object tracking using Kalman filters
- `frigate/events/` — Event lifecycle management (start, update, end, cleanup)
- `frigate/record/` — 24/7 recording and clip generation
- `frigate/review/` — Review segment processing
- `frigate/comms/` — Inter-process communication (MQTT, WebSocket, ZMQ)
- `frigate/embeddings/` — ML embeddings for semantic search
- `frigate/db/` — SQLite models (peewee ORM) and migrations
- `frigate/ptz/` — Pan-Tilt-Zoom camera control

Inter-process communication uses Python `multiprocessing.Queue` and `SharedMemory` for passing frames efficiently between processes.

### Frontend (React)

- `web/src/pages/` — Top-level route pages
- `web/src/components/` — Feature-organized components
- `web/src/hooks/` — Custom React hooks (API calls, WebSocket, state)
- `web/src/api/` — API client utilities
- `web/public/locales/` — i18n translation files (organized by language code, then namespace)

State management uses Recoil for global state and SWR for server data fetching. Real-time updates come via WebSocket (`react-use-websocket`).

### i18n Rule

**Never hardcode UI strings.** All frontend text must use the i18next translation system. Add new strings to the appropriate file in `web/public/locales/en/` and reference them via `useTranslation()`. The locale files are organized by namespace: `common.json`, `views/<page>.json`, `components/<component>.json`, `objects.json`, etc.

### Ports (Development)

| Port | Service |
|------|---------|
| 5000 | NGINX reverse proxy (main entry) |
| 5001 | FastAPI backend |
| 5173 | Vite dev server |
| 8554 | go2rtc RTSP |
| 8555 | go2rtc WebRTC |
