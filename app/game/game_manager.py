#/Users/sea/my_projects/stealth_game/app/game/game_manager.py
import random
import time
import numpy as np


class GameManager:

    def __init__(self):

        # -----------------------------
        # 게임 상태
        # -----------------------------
        self.started = False
        self.finished = False
        self.paused = False

        # waiting / selecting / playing / paused / game_over
        self.phase = "waiting"

        # -----------------------------
        # 시간
        # -----------------------------
        self.start_time = None
        self.time_limit = 180

        # -----------------------------
        # 술래
        # -----------------------------
        self.tagger_id = None

        # -----------------------------
        # 점수
        # -----------------------------
        self.score = 0

        self.tagger_touch_count = 0

        self.player_hit_count = {}

        # -----------------------------
        # tracking
        # -----------------------------
        self.prev_centers = {}

        self.current_tracks = []

        # -----------------------------
        # invisibility
        # -----------------------------
        self.stopped_ids = set()

        self.speed_threshold = 8.0

        # -----------------------------
        # collision cooldown
        # -----------------------------
        self.hit_cooldown = 1.0

        self.last_hit_time = {}

    # -----------------------------
    # 게임 시작
    # -----------------------------
    def start_game(self):

        if self.tagger_id is None:
            self.select_tagger_from_current_tracks()

        self.started = True
        self.finished = False
        self.paused = False

        self.phase = "playing"

        self.start_time = time.time()

    # -----------------------------
    # 게임 종료
    # -----------------------------
    def end_game(self):

        self.finished = True
        self.started = False

        self.phase = "game_over"

    # -----------------------------
    # 게임 재시작
    # -----------------------------
    def restart(self):

        self.__init__()

    # -----------------------------
    # pause
    # -----------------------------
    def pause_game(self):

        if self.started and not self.finished:

            self.paused = True

            self.phase = "paused"

    # -----------------------------
    # resume
    # -----------------------------
    def resume_game(self):

        if self.started and not self.finished:

            self.paused = False

            self.phase = "playing"

    # -----------------------------
    # 남은 시간
    # -----------------------------
    def get_time_left(self):

        if not self.started:
            return self.time_limit

        elapsed = time.time() - self.start_time

        remain = self.time_limit - elapsed

        if remain <= 0:

            remain = 0

            self.finished = True

            self.phase = "game_over"

        return remain

    # -----------------------------
    # 술래 선택
    # -----------------------------
    def select_tagger(self, tracks):

        ids = [t["id"] for t in tracks]

        if ids:
            self.tagger_id = random.choice(ids)

    # -----------------------------
    # 현재 tracks 기준 술래 선택
    # -----------------------------
    def select_tagger_from_current_tracks(self):

        self.select_tagger(self.current_tracks)

        if self.tagger_id is not None:
            self.phase = "selecting"

    # -----------------------------
    # 움직임 분석
    # -----------------------------
    def update_motion(self, tracks):

        self.stopped_ids.clear()

        for t in tracks:

            track_id = t["id"]

            center = t["center"]

            prev = self.prev_centers.get(
                track_id,
                center
            )

            speed = np.linalg.norm(center - prev)

            self.prev_centers[track_id] = center

            if speed < self.speed_threshold:

                self.stopped_ids.add(track_id)

    # -----------------------------
    # IoU
    # -----------------------------
    def iou(self, box1, box2):

        x1 = max(box1[0], box2[0])
        y1 = max(box1[1], box2[1])

        x2 = min(box1[2], box2[2])
        y2 = min(box1[3], box2[3])

        inter = max(0, x2 - x1) * max(0, y2 - y1)

        area1 = (box1[2] - box1[0]) * (
            box1[3] - box1[1]
        )

        area2 = (box2[2] - box2[0]) * (
            box2[3] - box2[1]
        )

        union = area1 + area2 - inter

        return inter / union if union > 0 else 0

    # -----------------------------
    # collision detect
    # -----------------------------
    def detect_collision(self, tracks):

        if self.tagger_id is None:
            return False, None

        tagger = next(
            (
                t for t in tracks
                if t["id"] == self.tagger_id
            ),
            None
        )

        if tagger is None:
            return False, None

        for t in tracks:

            if t["id"] == self.tagger_id:
                continue

            collision = self.iou(
                tagger["bbox"],
                t["bbox"]
            )

            if collision > 0.15:
                return True, t["id"]

        return False, None

    # -----------------------------
    # 최종 tag 적용
    # -----------------------------
    def apply_valid_tag(self, target_id):

        now = time.time()

        last = self.last_hit_time.get(
            target_id,
            0
        )

        if now - last <= self.hit_cooldown:
            return

        self.score += 1

        self.tagger_touch_count += 1

        self.player_hit_count[target_id] = \
            self.player_hit_count.get(
                target_id,
                0
            ) + 1

        self.last_hit_time[target_id] = now

    # -----------------------------
    # 메인 업데이트
    # -----------------------------
    def update(self, tracks):

        self.current_tracks = tracks

        # 시작 전에도 motion 업데이트
        if not self.started:

            self.update_motion(tracks)

            return

        if self.finished:
            return

        if self.paused:
            return

        self.update_motion(tracks)

        self.get_time_left()

    # -----------------------------
    # 상태 export
    # -----------------------------
    def export_state(self):

        players = []

        for track_id in self.prev_centers.keys():

            players.append({

                "id": track_id,

                "is_tagger":
                    track_id == self.tagger_id,

                "is_invisible":
                    track_id in self.stopped_ids,

                "hit_count":
                    self.player_hit_count.get(
                        track_id,
                        0
                    )
            })

        return {

            "started": self.started,

            "finished": self.finished,

            "paused": self.paused,

            "phase": self.phase,

            "score": self.score,

            "tagger_id": self.tagger_id,

            "time_left":
                int(self.get_time_left()),

            "tagger_touch_count":
                self.tagger_touch_count,

            "player_count":
                len(players),

            "players": players
        }