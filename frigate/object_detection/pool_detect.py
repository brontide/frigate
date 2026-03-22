"""Shared-pool remote object detector for parallel region submission.

Uses a global pool of SHM slots so multiple regions (from any camera) can be
in-flight simultaneously across detectors.  Each pool slot is an independent
connection_id — detector backends are completely unchanged except for unpacking
a (pool_slot, camera_name) tuple from the queue instead of a bare string.
"""

import logging
import time
from multiprocessing import Queue as MpQueue

import numpy as np
import zmq

from frigate.comms.object_detector_signaler import ObjectDetectorSubscriber
from frigate.detectors.detector_config import ModelConfig
from frigate.util.builtin import EventsPerSecond
from frigate.util.image import UntrackedSharedMemory

logger = logging.getLogger(__name__)


class PoolRemoteObjectDetector:
    """Drop-in alternative to RemoteObjectDetector using a shared slot pool.

    Cameras acquire free slots from the pool, write tensors, enqueue work items
    as (pool_slot, camera_name) tuples, and wait for results via ZMQ prefix
    matching on their camera topic.
    """

    def __init__(
        self,
        name: str,
        labels: dict[int, str],
        detection_queue,
        model_config: ModelConfig,
        stop_event,
        free_slots: MpQueue,
        num_slots: int,
    ):
        self.name = name
        self.labels = labels
        self.detection_queue = detection_queue
        self.stop_event = stop_event
        self.free_slots = free_slots
        self.num_slots = num_slots
        self.fps = EventsPerSecond()

        # Pre-open all pool slot SHMs so we don't open/close per-request
        self.pool_np_in: dict[int, np.ndarray] = {}
        self.pool_shm_in: dict[int, UntrackedSharedMemory] = {}
        self.pool_np_out: dict[int, np.ndarray] = {}
        self.pool_shm_out: dict[int, UntrackedSharedMemory] = {}

        for i in range(num_slots):
            slot_name = f"pool_slot{i}"
            shm_in = UntrackedSharedMemory(name=slot_name, create=False)
            self.pool_shm_in[i] = shm_in
            self.pool_np_in[i] = np.ndarray(
                (1, model_config.height, model_config.width, 3),
                dtype=np.uint8,
                buffer=shm_in.buf,
            )
            shm_out = UntrackedSharedMemory(name=f"out-{slot_name}", create=False)
            self.pool_shm_out[i] = shm_out
            self.pool_np_out[i] = np.ndarray(
                (20, 6), dtype=np.float32, buffer=shm_out.buf
            )

        # ZMQ subscriber for this camera — prefix matches all pool slot responses
        self.subscriber = ObjectDetectorSubscriber(self.name)

        logger.info(f"{name}: using shared detection pool ({num_slots} global slots)")

    def detect_parallel(
        self, tensors: list[np.ndarray], threshold: float = 0.4
    ) -> list[list]:
        """Submit multiple tensors in parallel, return per-tensor detection lists."""
        if self.stop_event.is_set():
            return [[] for _ in tensors]

        all_results: list[list] = []

        # Drain stale ZMQ messages
        while True:
            try:
                self.subscriber.socket.recv_string(flags=zmq.NOBLOCK)
            except zmq.Again:
                break

        # Acquire slots and submit all tensors
        acquired_slots: list[int] = []
        for tensor in tensors:
            try:
                slot_idx = self.free_slots.get(timeout=10)
            except Exception:
                logger.warning(f"{self.name}: timed out waiting for free pool slot")
                break
            acquired_slots.append(slot_idx)
            self.pool_np_in[slot_idx][:] = tensor[:]
            self.detection_queue.put((f"pool_slot{slot_idx}", self.name))

        # Wait for all responses
        pending = set(range(len(acquired_slots)))
        results_by_idx: dict[int, list] = {}
        deadline = time.monotonic() + 10.0

        while pending and time.monotonic() < deadline:
            remaining_ms = (deadline - time.monotonic()) * 1000
            if remaining_ms <= 0:
                break
            try:
                has_update, _, _ = zmq.select(
                    [self.subscriber.socket], [], [], remaining_ms / 1000
                )
            except zmq.ZMQError:
                break
            if not has_update:
                continue

            try:
                msg = self.subscriber.socket.recv_string(flags=zmq.NOBLOCK)
            except zmq.Again:
                continue

            # Parse pool slot index from message
            # Format: "object_detector/{camera_name}/pool_slot{idx}/"
            for i, slot_idx in enumerate(acquired_slots):
                if i in pending and f"pool_slot{slot_idx}" in msg:
                    # Read results from pool output SHM
                    detections = []
                    for d in self.pool_np_out[slot_idx]:
                        if d[1] < threshold:
                            break
                        detections.append(
                            (
                                self.labels[int(d[0])],
                                float(d[1]),
                                (d[2], d[3], d[4], d[5]),
                            )
                        )
                    results_by_idx[i] = detections
                    pending.discard(i)
                    # Return slot to pool
                    self.free_slots.put(slot_idx)
                    self.fps.update()
                    break

        if pending:
            # Release timed-out slots back to the pool. The detector may
            # still be processing them, which means another camera could
            # overwrite the input before the detector reads it — but the
            # result is just a wasted inference (published to our ZMQ topic,
            # drained as stale on the next call). This avoids slot starvation.
            for i in pending:
                self.free_slots.put(acquired_slots[i])
            logger.warning(
                f"{self.name}: {len(pending)} pool slots timed out, released"
            )

        # Assemble results in submission order
        for i in range(len(acquired_slots)):
            all_results.append(results_by_idx.get(i, []))

        return all_results

    def detect(self, tensor_input: np.ndarray, threshold: float = 0.4):
        """Single-tensor detect. Backward compatible."""
        return self.detect_parallel([tensor_input], threshold)[0]

    def cleanup(self):
        self.subscriber.stop()
