#/Users/sea/my_projects/stealth_game/app/cv/yolo_inpaint_stealth.py
import cv2
import numpy as np
from ultralytics import YOLO


class YoloInpaintStealth:
    def __init__(self):
        self.model = YOLO("yolov8n-seg.pt")
        self.model.to("cpu")

        self.last_results = None

        # -----------------------------
        # tracking
        # -----------------------------
        self.prev_centers = {}
        self.speed_threshold = 8.0

        # -----------------------------
        # background
        # -----------------------------
        self.background = None

        # 어떤 픽셀이 이미 clean하게 채워졌는지
        self.background_filled = None

        self.background_locked = False

        # -----------------------------
        # previous frame
        # -----------------------------
        self.prev_gray = None
        self.prev_frame = None

        # -----------------------------
        # camera motion
        # -----------------------------
        self.max_frame_diff_reset = 40.0

        # -----------------------------
        # detection
        # -----------------------------
        self.person_conf_threshold = 0.6

        # -----------------------------
        # stealth mask refinement
        # -----------------------------
        self.person_kernel_size = 11

        # -----------------------------
        # accumulation safe mask
        # -----------------------------
        self.safe_kernel_size = 81

    # =========================================================
    # 1. detection
    # =========================================================
    def detect(self, frame):

        self.last_results = self.model(
            frame,
            verbose=False
        )[0]

        detections = []

        if self.last_results.boxes is None:
            return detections

        h, w = frame.shape[:2]

        for box in self.last_results.boxes:

            cls = int(box.cls[0])
            conf = float(box.conf[0])

            if cls != 0:
                continue

            if conf < self.person_conf_threshold:
                continue

            x1, y1, x2, y2 = map(
                int,
                box.xyxy[0]
            )

            x1 = max(0, x1)
            y1 = max(0, y1)

            x2 = min(w, x2)
            y2 = min(h, y2)

            detections.append({
                "bbox": [x1, y1, x2, y2]
            })

        return detections

    # =========================================================
    # 2. stealth mask refinement
    # =========================================================
    def refine_person_mask(self, mask):

        mask = (mask > 0.3).astype(np.uint8)

        kernel = np.ones(
            (
                self.person_kernel_size,
                self.person_kernel_size
            ),
            np.uint8
        )

        mask = cv2.dilate(
            mask,
            kernel,
            iterations=1
        )

        mask = cv2.morphologyEx(
            mask,
            cv2.MORPH_CLOSE,
            kernel
        )

        return mask.astype(np.float32)

    # =========================================================
    # 3. huge safe mask for accumulation
    # =========================================================
    def build_background_safe_mask(
        self,
        full_person_binary
    ):

        kernel = np.ones(
            (
                self.safe_kernel_size,
                self.safe_kernel_size
            ),
            np.uint8
        )

        safe_mask = cv2.dilate(
            full_person_binary.astype(np.uint8),
            kernel,
            iterations=2
        )

        return safe_mask.astype(bool)

    # =========================================================
    # 4. full person mask
    # =========================================================
    def build_full_person_mask(
        self,
        boxes,
        masks,
        h,
        w
    ):

        full_person_mask = np.zeros(
            (h, w),
            dtype=np.float32
        )

        for i, box in enumerate(boxes):

            cls = int(box.cls[0])
            conf = float(box.conf[0])

            if cls != 0:
                continue

            if conf < self.person_conf_threshold:
                continue

            mask = cv2.resize(
                masks[i],
                (w, h)
            )

            mask = self.refine_person_mask(mask)

            full_person_mask = np.maximum(
                full_person_mask,
                mask
            )

        return full_person_mask

    # =========================================================
    # 5. stealth mask
    # =========================================================
    def build_stealth_mask(
        self,
        boxes,
        masks,
        tracks,
        h,
        w
    ):

        mask_total = np.zeros(
            (h, w),
            dtype=np.float32
        )

        for track in tracks:

            tx1, ty1, tx2, ty2 = map(
                int,
                track["bbox"]
            )

            track_id = track["id"]

            cx = (tx1 + tx2) // 2
            cy = (ty1 + ty2) // 2

            prev = self.prev_centers.get(
                track_id,
                (cx, cy)
            )

            speed = np.linalg.norm(
                np.array([cx, cy]) - np.array(prev)
            )

            self.prev_centers[track_id] = (
                cx,
                cy
            )

            # 움직이면 stealth 안됨
            if speed > self.speed_threshold:
                continue

            best_iou = 0.0
            best_mask = None

            for i, box in enumerate(boxes):

                cls = int(box.cls[0])
                conf = float(box.conf[0])

                if cls != 0:
                    continue

                if conf < self.person_conf_threshold:
                    continue

                x1, y1, x2, y2 = map(
                    int,
                    box.xyxy[0]
                )

                iou = self._compute_iou(
                    [tx1, ty1, tx2, ty2],
                    [x1, y1, x2, y2]
                )

                if iou > best_iou:
                    best_iou = iou
                    best_mask = masks[i]

            if best_iou < 0.25:
                continue

            if best_mask is None:
                continue

            mask = cv2.resize(
                best_mask,
                (w, h)
            )

            mask = self.refine_person_mask(mask)

            mask_total = np.maximum(
                mask_total,
                mask
            )

        return mask_total

    # =========================================================
    # 6. clean plate accumulation
    # =========================================================
    def accumulate_background(
        self,
        frame,
        full_person_binary
    ):

        if self.background_locked:
            return

        # 최초 생성
        if self.background is None:

            self.background = np.zeros_like(
                frame,
                dtype=np.float32
            )

            self.background_filled = np.zeros(
                frame.shape[:2],
                dtype=bool
            )

        # 사람 주변까지 크게 보호
        safe_mask = self.build_background_safe_mask(
            full_person_binary
        )

        # 저장 가능한 영역
        non_person = ~safe_mask

        # 아직 안 채워진 픽셀만 저장
        new_pixels = (
            non_person
            &
            (~self.background_filled)
        )

        self.background[new_pixels] = frame[
            new_pixels
        ]

        self.background_filled[
            new_pixels
        ] = True

        # 얼마나 채워졌는지
        fill_ratio = np.mean(
            self.background_filled
        )

        print(
            f"[INFO] Background Fill: {fill_ratio:.3f}"
        )

        # 거의 다 채워졌으면 lock
        if fill_ratio > 0.95:

            self.background_locked = True

            print(
                "[INFO] Background Locked"
            )

    # =========================================================
    # 7. camera motion
    # =========================================================
    def handle_camera_motion(
        self,
        frame,
        gray
    ):

        if self.prev_gray is None:
            return

        frame_diff = np.mean(
            cv2.absdiff(
                gray,
                self.prev_gray
            )
        )

        if frame_diff > self.max_frame_diff_reset:

            print(
                "[INFO] Camera Motion -> Reset Background"
            )

            self.background = None
            self.background_filled = None
            self.background_locked = False

    # =========================================================
    # 8. process
    # =========================================================
    def process(
        self,
        frame,
        tracks
    ):

        h, w = frame.shape[:2]

        results = self.last_results

        if (
            results is None
            or results.boxes is None
            or results.masks is None
        ):
            return frame, np.zeros(
                (h, w),
                dtype=np.uint8
            )

        boxes = results.boxes

        masks = results.masks.data.cpu().numpy()

        gray = cv2.cvtColor(
            frame,
            cv2.COLOR_BGR2GRAY
        )

        # 전체 사람 mask
        full_person_mask = self.build_full_person_mask(
            boxes,
            masks,
            h,
            w
        )

        full_person_binary = (
            full_person_mask > 0.5
        )

        # 초기 프레임
        if (
            self.prev_gray is None
            or self.prev_frame is None
        ):

            self.prev_gray = gray
            self.prev_frame = frame.copy()

            self.accumulate_background(
                frame,
                full_person_binary
            )

            return frame, np.zeros(
                (h, w),
                dtype=np.uint8
            )

        # 카메라 움직임 체크
        self.handle_camera_motion(
            frame,
            gray
        )

        # clean plate 누적
        self.accumulate_background(
            frame,
            full_person_binary
        )

        # prev 업데이트
        self.prev_gray = gray
        self.prev_frame = frame.copy()

        # stealth mask 생성
        stealth_mask = self.build_stealth_mask(
            boxes,
            masks,
            tracks,
            h,
            w
        )

        # background 아직 부족
        if self.background is None:
            return frame, np.zeros(
                (h, w),
                dtype=np.uint8
            )

        # 최종 background
        bg = np.clip(
            self.background,
            0,
            255
        ).astype(np.uint8)

        result = frame.copy()

        hard_mask = stealth_mask > 0.5

        # hard replace
        result[hard_mask] = bg[
            hard_mask
        ]

        return result, hard_mask.astype(
            np.uint8
        )

    # =========================================================
    # 9. IoU
    # =========================================================
    def _compute_iou(
        self,
        boxA,
        boxB
    ):

        xA = max(boxA[0], boxB[0])
        yA = max(boxA[1], boxB[1])

        xB = min(boxA[2], boxB[2])
        yB = min(boxA[3], boxB[3])

        inter = max(
            0,
            xB - xA
        ) * max(
            0,
            yB - yA
        )

        areaA = max(
            0,
            boxA[2] - boxA[0]
        ) * max(
            0,
            boxA[3] - boxA[1]
        )

        areaB = max(
            0,
            boxB[2] - boxB[0]
        ) * max(
            0,
            boxB[3] - boxB[1]
        )

        return inter / float(
            areaA + areaB - inter + 1e-6
        )