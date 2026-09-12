"""Error model: stable machine-readable codes mapped to HTTP statuses (PRD 13.1)."""

from __future__ import annotations

INVALID_AOI = "INVALID_AOI"
SCENE_NOT_FOUND = "SCENE_NOT_FOUND"
DATA_CORRUPT = "DATA_CORRUPT"
MODEL_UNAVAILABLE = "MODEL_UNAVAILABLE"
GPU_OOM = "GPU_OOM"
VALIDATION_INCOMPLETE = "VALIDATION_INCOMPLETE"
ARTIFACT_WRITE_FAILED = "ARTIFACT_WRITE_FAILED"
AUTH_FORBIDDEN = "AUTH_FORBIDDEN"
JOB_CONFLICT = "JOB_CONFLICT"
NOT_FOUND = "NOT_FOUND"
QUALITY_FAIL = "QUALITY_FAIL"
LEASE_LOST = "LEASE_LOST"

ERROR_STATUS: dict[str, int] = {
    INVALID_AOI: 400,
    SCENE_NOT_FOUND: 404,
    DATA_CORRUPT: 422,
    MODEL_UNAVAILABLE: 404,
    GPU_OOM: 500,
    VALIDATION_INCOMPLETE: 422,
    ARTIFACT_WRITE_FAILED: 500,
    AUTH_FORBIDDEN: 403,
    JOB_CONFLICT: 409,
    NOT_FOUND: 404,
    QUALITY_FAIL: 422,
    LEASE_LOST: 409,
}


class ApiError(Exception):
    """Domain error carrying a stable code, human message and HTTP status."""

    def __init__(self, code: str, message: str, http_status: int | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status if http_status is not None else ERROR_STATUS.get(code, 400)
