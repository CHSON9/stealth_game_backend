#/Users/sea/my_projects/stealth_game/app/multi_camera_manager.py
import time
import cv2
class MultiCameraManager:

    def __init__(self):

        self.cam_states = {

            "cam1": {
                "tracks": [],
                "collision": False,
                "target_id": None,
                "timestamp": 0
            },

            "cam2": {
                "tracks": [],
                "collision": False,
                "target_id": None,
                "timestamp": 0
            }
        }

        self.sync_window = 0.5

    def compute_similarity(
        self,
        track1,
        track2
    ):

        hist1 = track1["feature"]
        hist2 = track2["feature"]

        similarity = cv2.compareHist(
            hist1.astype("float32"),
            hist2.astype("float32"),
            cv2.HISTCMP_CORREL
        )

        return similarity
    
    def update_camera(
        self,
        camera_id,
        tracks,
        collision=False,
        target_id=None
    ):

        self.cam_states[camera_id] = {

            "tracks": tracks,

            "collision": collision,

            "target_id": target_id,

            "timestamp": time.time()
        }

    def is_valid_tag(self):

        cam1 = self.cam_states["cam1"]
        cam2 = self.cam_states["cam2"]

        if not cam1["collision"]:
            return False, None

        if not cam2["collision"]:
            return False, None

        time_diff = abs(
            cam1["timestamp"] - cam2["timestamp"]
        )

        if time_diff > self.sync_window:
            return False, None

        target1 = cam1["target_id"]
        target2 = cam2["target_id"]

        if target1 is None:
            return False, None

        if target2 is None:
            return False, None

        track1 = next(
            (
                t for t in cam1["tracks"]
                if t["id"] == target1
            ),
            None
        )

        track2 = next(
            (
                t for t in cam2["tracks"]
                if t["id"] == target2
            ),
            None
        )

        if track1 is None or track2 is None:
            return False, None

        similarity = self.compute_similarity(
            track1,
            track2
        )

        print(
            f"[INFO] Appearance Similarity: {similarity:.3f}"
        )

        if similarity < 0.7:
            return False, None

        return True, target1

    def export_state(self):

        return {

            "cam1": {

                "track_count":
                    len(self.cam_states["cam1"]["tracks"]),

                "collision":
                    self.cam_states["cam1"]["collision"]
            },

            "cam2": {

                "track_count":
                    len(self.cam_states["cam2"]["tracks"]),

                "collision":
                    self.cam_states["cam2"]["collision"]
            }
        }