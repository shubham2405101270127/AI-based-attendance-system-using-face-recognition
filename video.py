"""
Video streaming API - MJPEG stream with face recognition overlay.
Uses a global camera manager and shared session state.
"""

import asyncio
import cv2
import numpy as np
import base64
import logging
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel

from app.core.face_engine import face_engine
from app.services.recognition_service import mark_present

logger = logging.getLogger(__name__)
router = APIRouter()

# ─── Shared camera / session state ──────────────────────────────────────────
_camera: cv2.VideoCapture | None = None
_active_session_id: str | None = None
_marked_this_session: set[str] = set()


class SessionStart(BaseModel):
    session_id: str


@router.post("/start-session")
async def start_camera_session(body: SessionStart):
    global _camera, _active_session_id, _marked_this_session
    _active_session_id = body.session_id
    _marked_this_session = set()
    if _camera is None or not _camera.isOpened():
        _camera = cv2.VideoCapture(0)
        _camera.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        _camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    return {"ok": True, "session_id": _active_session_id}


@router.post("/stop-session")
async def stop_camera_session():
    global _camera, _active_session_id, _marked_this_session
    if _camera:
        _camera.release()
        _camera = None
    _active_session_id = None
    _marked_this_session.clear()
    return {"ok": True}


@router.get("/stream")
async def video_stream():
    """MJPEG stream with face recognition overlay."""
    if _camera is None or not _camera.isOpened():
        raise HTTPException(400, "Camera not started. Call /start-session first.")

    async def frame_generator():
        while _camera and _camera.isOpened():
            ret, frame = _camera.read()
            if not ret:
                await asyncio.sleep(0.05)
                continue

            if _active_session_id:
                result = face_engine.process_frame(frame, _active_session_id)
                frame = _draw_overlay(frame, result["faces"])

                # Fire-and-forget attendance marking for confirmed faces
                for sid in result["newly_confirmed"]:
                    if sid not in _marked_this_session:
                        _marked_this_session.add(sid)
                        face = next((f for f in result["faces"] if f["student_id"] == sid), None)
                        conf = face["confidence"] if face else 0.0
                        asyncio.create_task(mark_present(_active_session_id, sid, conf))

            _, jpeg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n" +
                jpeg.tobytes() +
                b"\r\n"
            )
            await asyncio.sleep(0.033)  # ~30 fps target

    return StreamingResponse(
        frame_generator(),
        media_type="multipart/x-mixed-replace; boundary=frame"
    )


@router.post("/process-photo")
async def process_uploaded_photo(payload: dict):
    """
    Process a base64-encoded classroom photo for batch attendance.
    Body: {session_id: str, image_b64: str}
    """
    try:
        session_id = payload["session_id"]
        img_data = base64.b64decode(payload["image_b64"])
        nparr = np.frombuffer(img_data, np.uint8)
        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        result = face_engine.process_frame(frame, session_id)

        # For photo upload: auto-confirm after single good detection (no time threshold)
        for face in result["faces"]:
            sid = face.get("student_id")
            if sid and face["liveness"] and face["confidence"] > 0.6:
                await mark_present(session_id, sid, face["confidence"])

        return {
            "faces_detected": len(result["faces"]),
            "faces": result["faces"],
        }
    except Exception as e:
        raise HTTPException(400, str(e))


def _draw_overlay(frame: np.ndarray, faces: list) -> np.ndarray:
    """Draw bounding boxes and labels on the frame."""
    for f in faces:
        top, right, bottom, left = f["box"]
        name      = f["name"]
        conf      = f["confidence"]
        is_live   = f["liveness"]
        confirmed = f["confirmed"]

        # Box color: green=confirmed, yellow=recognized, red=unknown/spoof
        if not is_live:
            color = (0, 0, 200)      # red: spoof
        elif confirmed:
            color = (0, 200, 0)      # green: confirmed present
        elif f["student_id"]:
            color = (0, 200, 200)    # yellow: recognizing…
        else:
            color = (100, 100, 100)  # grey: unknown

        cv2.rectangle(frame, (left, top), (right, bottom), color, 2)

        label = f"{name} ({conf:.0%})"
        if not is_live:
            label += " ⚠ SPOOF"
        elif confirmed:
            label += " ✓"

        cv2.rectangle(frame, (left, top - 22), (right, top), color, -1)
        cv2.putText(frame, label, (left + 4, top - 5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1)

    # Frame counter / status
    ts = cv2.getTickCount()
    cv2.putText(frame, f"Faces: {len(faces)}", (10, 25),
                cv2.FONT_HERSHEY_SIMPLEX, 0.65, (200, 255, 200), 2)
    return frame
