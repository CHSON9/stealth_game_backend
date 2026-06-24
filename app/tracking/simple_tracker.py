#/Users/sea/my_projects/stealth_game/app/tracking/simple_tracker.py
import numpy as np
import cv2
class SimpleTracker:
    def __init__(self, max_distance=120):
        self.next_id = 0
        self.tracks = {}
        self.max_distance = max_distance

    def _extract_feature(self, frame, bbox):

        x1, y1, x2, y2 = map(int, bbox)

        h, w = frame.shape[:2]

        x1 = max(0, x1)
        y1 = max(0, y1)

        x2 = min(w, x2)
        y2 = min(h, y2)

        crop = frame[y1:y2, x1:x2]

        if crop.size == 0:

            return np.zeros(256)

        hsv = cv2.cvtColor(
            crop,
            cv2.COLOR_BGR2HSV
        )

        hist = cv2.calcHist(
            [hsv],
            [0, 1],
            None,
            [16, 16],
            [0, 180, 0, 256]
        )

        hist = cv2.normalize(
            hist,
            hist
        ).flatten()

        return hist

    def _center(self, bbox):
        x1, y1, x2, y2 = bbox
        return np.array([(x1 + x2) / 2, (y1 + y2) / 2])

    def update(self, detections, frame):
        updated_tracks = []
        used_ids = set()

        for det_idx, det in enumerate(detections):
            bbox = det["bbox"]
            center = self._center(bbox)
            feature = self._extract_feature(
                frame,
                bbox
            )

            best_id = None
            best_dist = float("inf")

            for track_id, old_center in self.tracks.items():
                if track_id in used_ids:
                    continue

                dist = np.linalg.norm(center - old_center)

                if dist < best_dist and dist < self.max_distance:
                    best_dist = dist
                    best_id = track_id

            if best_id is None:
                best_id = self.next_id
                self.next_id += 1

            self.tracks[best_id] = center
            used_ids.add(best_id)

            updated_tracks.append({
                "id": best_id,
                "bbox": bbox,
                "det_idx": det_idx,
                "center": center,
                "feature": feature,
            })

        self.tracks = {
            track["id"]: track["center"]
            for track in updated_tracks
        }

        return updated_tracks