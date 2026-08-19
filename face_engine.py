"""
Core Face Recognition Engine - DeepFace version (Windows-friendly)
No dlib compilation needed.
"""

import cv2
import numpy as np
import pickle
from dataclasses import dataclass, field
from collections import deque
from typing import Optional
import time
import logging

logger = logging.getLogger(__name__)

RECOGNITION_THRESHOLD   = 0.60
CONFIRM_FRAMES_REQUIRED = 5
CONFIRM_WINDOW_SECONDS  = 8
LBP_VARIANCE_THRESHOLD  = 80.0

try:
    from deepface import DeepFace
    DEEPFACE_OK = True
    logger.info("[FaceEngine] DeepFace loaded OK")
except Exception as e:
    DEEPFACE_OK = False
    logger.error(f"[FaceEngine] DeepFace not available: {e}")


@dataclass
class RecognitionState:
    student_id: str
    name: str
    frame_hits: deque = field(default_factory=lambda: deque(maxlen=50))
    confirmed: bool = False
    last_confidence: float = 0.0


class FaceEngine:
    def __init__(self):
        self._known_ids: list[str] = []
        self._known_names: list[str] = []
        self._known_embeddings: list[np.ndarray] = []
        self._recognition_states: dict[str, RecognitionState] = {}

    def load_embeddings(self, records: list[dict]):
        self._known_ids.clear()
        self._known_names.clear()
        self._known_embeddings.clear()
        for r in records:
            try:
                emb = pickle.loads(r["embedding"])
                self._known_ids.append(r["student_id"])
                self._known_names.append(r["name"])
                self._known_embeddings.append(emb)
            except Exception as e:
                logger.error(f"[FaceEngine] Bad embedding for {r['student_id']}: {e}")
        logger.info(f"[FaceEngine] Loaded {len(self._known_embeddings)} embeddings.")

    def add_embedding(self, student_id: str, name: str, embedding: np.ndarray):
        self._known_ids.append(student_id)
        self._known_names.append(name)
        self._known_embeddings.append(embedding)

    def extract_embedding(self, image: np.ndarray) -> Optional[np.ndarray]:
        """Extract face embedding from an image using DeepFace."""
        if not DEEPFACE_OK:
            return None
        try:
            result = DeepFace.represent(
                img_path=image,
                model_name="Facenet",
                enforce_detection=True,
                detector_backend="opencv"
            )
            if result:
                return np.array(result[0]["embedding"])
        except Exception as e:
            logger.warning(f"[FaceEngine] extract_embedding failed: {e}")
        return None

    def process_frame(self, frame: np.ndarray, session_id: str) -> dict:
        """Process a single frame - detect faces, recognize, apply threshold."""
        results = []
        newly_confirmed = []
        now = time.time()

        if not DEEPFACE_OK:
            return {"faces": [], "newly_confirmed": []}

        try:
            # Detect all faces in frame
            detected = DeepFace.extract_faces(
                img_path=frame,
                detector_backend="opencv",
                enforce_detection=False,
                align=True
            )
        except Exception as e:
            logger.debug(f"[FaceEngine] extract_faces error: {e}")
            return {"faces": [], "newly_confirmed": []}

        for face_obj in detected:
            region = face_obj.get("facial_area", {})
            x = region.get("x", 0)
            y = region.get("y", 0)
            w = region.get("w", 0)
            h = region.get("h", 0)

            if w < 40 or h < 40:
                continue

            box = (y, x + w, y + h, x)  # top, right, bottom, left
            face_crop = frame[y:y+h, x:x+w]

            # Anti-spoofing texture check
            lbp_ok = self._check_texture(face_crop)

            # Get embedding for this face
            student_id, name, confidence = None, None, 0.0
            try:
                emb_result = DeepFace.represent(
                    img_path=face_crop,
                    model_name="Facenet",
                    enforce_detection=False,
                    detector_backend="skip"
                )
                if emb_result:
                    embedding = np.array(emb_result[0]["embedding"])
                    student_id, name, confidence = self._identify(embedding)
            except Exception as e:
                logger.debug(f"[FaceEngine] represent error: {e}")

            is_live = lbp_ok

            confirmed = False
            if student_id and is_live:
                state = self._recognition_states.setdefault(
                    f"{session_id}_{student_id}",
                    RecognitionState(student_id=student_id, name=name)
                )
                state.last_confidence = confidence
                state.frame_hits.append(now)

                window_hits = sum(
                    1 for t in state.frame_hits
                    if now - t <= CONFIRM_WINDOW_SECONDS
                )
                if window_hits >= CONFIRM_FRAMES_REQUIRED and not state.confirmed:
                    state.confirmed = True
                    newly_confirmed.append(student_id)
                confirmed = state.confirmed

            results.append({
                "box": box,
                "student_id": student_id,
                "name": name or "Unknown",
                "confidence": round(confidence, 3),
                "liveness": is_live,
                "texture_ok": lbp_ok,
                "confirmed": confirmed,
            })

        return {"faces": results, "newly_confirmed": newly_confirmed}

    def _identify(self, embedding: np.ndarray) -> tuple[Optional[str], Optional[str], float]:
        if not self._known_embeddings:
            return None, None, 0.0

        known = np.array(self._known_embeddings)

        # Cosine similarity
        emb_norm = embedding / (np.linalg.norm(embedding) + 1e-6)
        known_norms = known / (np.linalg.norm(known, axis=1, keepdims=True) + 1e-6)
        similarities = known_norms @ emb_norm
        best_idx = int(np.argmax(similarities))
        best_sim = float(similarities[best_idx])

        if best_sim >= RECOGNITION_THRESHOLD:
            return (
                self._known_ids[best_idx],
                self._known_names[best_idx],
                best_sim,
            )
        return None, None, best_sim

    def _check_texture(self, face_crop: np.ndarray) -> bool:
        if face_crop.size == 0:
            return False
        try:
            gray = cv2.cvtColor(face_crop, cv2.COLOR_BGR2GRAY)
            gray = cv2.resize(gray, (64, 64))
            variance = float(np.var(gray))
            return variance >= LBP_VARIANCE_THRESHOLD
        except Exception:
            return True

    def reset_session(self, session_id: str):
        keys = [k for k in self._recognition_states if k.startswith(f"{session_id}_")]
        for k in keys:
            del self._recognition_states[k]


face_engine = FaceEngine()