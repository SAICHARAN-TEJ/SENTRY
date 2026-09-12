"""Shared test fixtures: synthetic scene, fake in-memory DB."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import numpy as np
import pytest

# API tests intentionally opt into the development identity header.  The
# application default remains fail-closed (DEV_AUTH=false); set this before
# any test module imports backend.main / first constructs Settings().
os.environ.setdefault("DEV_AUTH", "true")

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

BANDS = ["B02", "B03", "B04", "B08"]
JOB_STATUSES = {"QUEUED", "CLAIMED", "PREPROCESSING", "RECONSTRUCTING", "UNCERTAINTY",
               "VALIDATING", "REPORTING", "COMPLETED", "FAILED", "CANCELLED"}


@pytest.fixture(scope="session")
def scene() -> dict:
    """Deterministic synthetic 512x512 4-band scene (uint16 DN)."""
    from fixtures.make_fixtures import build_scene

    return build_scene(seed=42)


@pytest.fixture(scope="session")
def ref_arrays(scene) -> dict:
    """Float32 [0,1] reflectance views: (4, H, W) and (H, W, 4)."""
    dn = np.stack([scene["bands"][b] for b in BANDS]).astype(np.float32)
    refl = np.clip(dn * 1e-4, 0, 1)
    return {"bchw": refl, "bhwc": np.moveaxis(refl, 0, -1)}


class FakeDB:
    """Tiny in-memory backend.db replacement: pattern-matched SQL on dict stores."""

    def __init__(self) -> None:
        self.projects: dict[str, dict] = {}
        self.members: dict[tuple, dict] = {}      # (project_id, user_id) -> row
        self.orgs: dict[str, dict] = {}
        self.jobs: dict[str, dict] = {}
        self.steps: dict[tuple, dict] = {}        # (job_id, step_name) -> row
        self.artifacts: dict[str, dict] = {}
        self.validations: dict[str, dict] = {}
        self.metrics: list[dict] = []
        self.models: dict[str, dict] = {}
        self.provenance: list[dict] = []
        self.aois: dict[str, dict] = {}
        self.configs: dict[str, dict] = {}
        self.scenes: dict[str, dict] = {}
        self.references: dict[str, dict] = {}
        self.job_inputs: list[dict] = []
        self._seq = 0

    def _next_id(self) -> str:
        self._seq += 1
        return f"00000000-0000-4000-8000-{self._seq:012d}"

    def query(self, sql: str, params=None, *, one: bool = False):
        """Match a small SQL dialect sufficient for the routers under test."""
        s = " ".join(sql.lower().split())
        p = list(params) if params else []

        # Validation evidence check must consult stored artifacts, not always pass.
        if "from raster_artifacts where job_id" in s and "artifact_type" in s:
            if "select 1" in s:
                hit = next((a for a in self.artifacts.values()
                            if a["job_id"] == p[0] and a.get("artifact_type") == p[1]), None)
                return ({"ok": 1} if hit else None) if one else ([{"ok": 1}] if hit else [])
        if "update validation_runs set queue_job_id" in s:
            row = self.validations.get(p[2]) if len(p) >= 3 else None
            if row is not None:
                row["queue_job_id"] = p[0]
                row["request_fingerprint"] = p[1]
            return None if one else []

        if s.startswith("select 1") or s == "select 1 as ok":
            return {"ok": 1} if one else [{"ok": 1}]

        # --- membership ----------------------------------------------------
        if "from project_members where project_id" in s and "insert" not in s:
            row = self.members.get((p[0], p[1]))
            return row if one else ([row] if row else [])
        if "insert into project_members" in s:
            # values (project_id, user_id, 'owner') on conflict do nothing
            self.members[(p[0], p[1])] = {
                "project_id": p[0], "user_id": p[1],
                "role": p[2] if len(p) > 2 else "owner"}
            return None

        # --- organizations / projects ---------------------------------------
        if "insert into organizations" in s:
            row = {"id": self._next_id(), "name": p[0],
                   "created_by": p[1] if len(p) > 1 else None,
                   "created_at": None}
            self.orgs[row["id"]] = row
            return row if one else [row]

        if "insert into projects" in s:
            row = {"id": self._next_id(), "organization_id": p[0], "name": p[1],
                   "default_crs": p[2], "created_at": None}
            self.projects[row["id"]] = row
            return row if one else [row]

        if "from projects p join project_members" in s:
            rows = [dict(pr) for pr in self.projects.values()
                    if (pr["id"], p[0]) in self.members]
            return rows if not one else (rows[0] if rows else None)

        if "pg_advisory_xact_lock" in s:
            return {"pg_advisory_xact_lock": True} if one else [{"pg_advisory_xact_lock": True}]

        if "select o.id" in s and "from organizations o" in s:
            org_id, user_id = p[-1], p[0]
            exists = org_id in self.orgs
            owner = any(
                pr["organization_id"] == org_id
                and (pr["id"], user_id) in self.members
                and self.members[(pr["id"], user_id)]["role"] == "owner"
                for pr in self.projects.values()
            )
            row = {"id": org_id, "is_owner": owner} if exists else None
            return row if one else ([row] if row else [])

        # --- model registry --------------------------------------------------
        if "from model_versions" in s and "where name" in s:
            row = next((m for m in self.models.values() if m["name"] == p[0]), None)
            return row if one else ([row] if row else [])
        if "from model_versions" in s and s.startswith("select"):
            rows = list(self.models.values())
            return rows if not one else (rows[0] if rows else None)

        # --- processing configs ----------------------------------------------
        if "select config_hash from processing_configs" in s:
            row = self.configs.get(p[0])
            return ({"config_hash": row["config_hash"]} if one else [row]) if row \
                else (None if one else [])

        # --- AOIs ------------------------------------------------------------
        if "insert into aois" in s:
            row = {"id": self._next_id(), "project_id": p[0], "name": p[1],
                   "bbox": json.loads(p[3]), "area_m2": p[4], "created_at": None}
            self.aois[row["id"]] = row
            return row if one else [row]
        if "from aois where id = %s and project_id = %s" in s:
            row = next((a for a in self.aois.values()
                        if a["id"] == p[0] and a["project_id"] == p[1]), None)
            return row if one else ([row] if row else [])
        if "from aois where project_id = %s" in s:
            rows = [a for a in self.aois.values() if a["project_id"] == p[0]]
            return rows if not one else (rows[0] if rows else None)

        # --- scenes / references ---------------------------------------------
        if "from scenes where id = %s" in s:
            row = self.scenes.get(p[0])
            return row if one else ([row] if row else [])
        if "from reference_assets where id = %s" in s:
            row = self.references.get(p[0])
            return row if one else ([row] if row else [])

        # --- jobs -------------------------------------------------------------
        if "from jobs" in s and "idempotency_key" in s and "where project_id" in s:
            rows = [j for j in self.jobs.values()
                    if j.get("project_id") == p[0]
                    and j.get("idempotency_key") == p[1]]
            if "status not in" in s:
                rows = [j for j in rows if j.get("status") not in {"FAILED", "CANCELLED"}]
            # SQL orders newest first in production; insertion sequence is
            # deterministic in this test double, so the last row is newest.
            row = rows[-1] if rows else None
            return row if one else ([row] if row else [])

        if "insert into jobs" in s:
            # Validation-queue insert uses literals for job_type/mode/status:
            # (project_id, requested_by, idem, fingerprint, config_hash, model_id).
            if "'validate', 'validate', 'queued'" in s:
                row = {"id": self._next_id(), "project_id": p[0], "job_type": "validate",
                       "mode": "validate", "status": "QUEUED", "progress": 0.0,
                       "requested_by": p[1], "idempotency_key": p[2],
                       "input_fingerprint": p[3], "config_hash": p[4],
                       "model_version_id": p[5] if len(p) > 5 else None,
                       "error_code": None, "error_message": None, "created_at": None,
                       "started_at": None, "completed_at": None, "priority": 100}
                self.jobs[row["id"]] = row
                return row if one else [row]
            # Current production SQL includes mode between job_type and status.
            # Keep compatibility with the older 7-parameter test SQL too.
            has_mode = "(project_id, job_type, mode," in s
            if has_mode:
                row = {"id": self._next_id(), "project_id": p[0], "job_type": p[1],
                       "mode": p[2], "status": "QUEUED", "progress": 0.0,
                       "requested_by": p[3], "idempotency_key": p[4],
                       "input_fingerprint": p[5], "config_hash": p[6],
                       "model_version_id": p[7],
                       "error_code": None, "error_message": None, "created_at": None,
                       "started_at": None, "completed_at": None, "priority": 100}
            else:
                row = {"id": self._next_id(), "project_id": p[0], "job_type": p[1],
                   "mode": "reconstruct_validate", "status": "QUEUED", "progress": 0.0,
                   "requested_by": p[2], "idempotency_key": p[3], "input_fingerprint": p[4],
                   "config_hash": p[5], "model_version_id": p[6],
                   "error_code": None, "error_message": None, "created_at": None,
                   "started_at": None, "completed_at": None, "priority": 100}
            self.jobs[row["id"]] = row
            return row if one else [row]

        if "select pg_advisory_xact_lock" in s:
            return {"pg_advisory_xact_lock": True} if one else [{"pg_advisory_xact_lock": True}]

        if "from jobs where id = %s" in s and s.startswith("select"):
            row = self.jobs.get(p[0])
            return (dict(row) if row else None) if one else ([dict(row)] if row else [])

        if "update jobs set idempotency_key" in s:
            # Terminal attempts are archived by changing only their key; all
            # child rows remain intact for FR-12 provenance/auditability.
            row = self.jobs.get(p[-1]) if p else None
            if row is None:
                return 0
            row["idempotency_key"] = f"{row['idempotency_key']}::archived::{row['id']}"
            return 1

        if "update jobs set status" in s:
            # The cancel statement has a literal status and only the job id in
            # params; queue transitions use a parameterized status. Respect
            # the conditional terminal guard and return the real row count.
            if "'cancelled'" in s:
                job_id = p[0] if p else None
                row = self.jobs.get(job_id)
                if row is None or row.get("status") in JOB_STATUSES & {
                    "COMPLETED", "FAILED", "CANCELLED"
                }:
                    return 0
                row["status"] = "CANCELLED"
                row["completed_at"] = "now"
                return 1

            job_id = p[-1] if p else None
            row = self.jobs.get(job_id)
            if row is None:
                return 0
            status = p[0] if p and p[0] in JOB_STATUSES else None
            if status is not None:
                row["status"] = status
            if "completed_at = now()" in s:
                row["completed_at"] = "now"
            return 1

        if "delete from jobs" in s:
            self.jobs.pop(p[0], None)
            for k in [k for k in self.steps if k[0] == p[0]]:
                del self.steps[k]
            return 1

        # --- job steps / inputs ------------------------------------------------
        if "insert into job_steps" in s:
            self.steps[(p[0], p[1])] = {"status": "QUEUED", "progress": 0.0,
                                        "attempt": 0}
            return None
        if "from job_steps where job_id = %s" in s and s.startswith("select"):
            rows = [{"name": k[1], "status": v["status"], "progress": v["progress"],
                     "attempt": v["attempt"], "metrics": None}
                    for k, v in self.steps.items() if k[0] == p[0]]
            return rows if not one else (rows[0] if rows else None)
        if "insert into job_inputs" in s or "insert into provenance_events" in s:
            if "insert into job_inputs" in s:
                self.job_inputs.append({"sql": s, "params": p})
            else:
                self.provenance.append({"sql": s, "params": p})
            return None

        # --- artifacts -----------------------------------------------------
        if "from raster_artifacts where job_id = %s" in s and s.startswith("select"):
            rows = [{"id": a["id"], "artifact_type": a["artifact_type"],
                     "storage_bucket": a["storage_bucket"], "object_key": a["object_key"],
                     "checksum": None, "bytes": 1, "media_type": "image/tiff"}
                    for a in self.artifacts.values() if a["job_id"] == p[0]]
            return rows if not one else (rows[0] if rows else None)

        # --- validation runs -------------------------------------------------
        if "from validation_runs where queue_job_id" in s:
            hit = next((dict(v) for v in self.validations.values()
                        if v.get("queue_job_id") == p[0]), None)
            return hit if one else ([hit] if hit else [])
        if "update validation_runs set status = 'failed'" in s:
            row = self.validations.get(p[0]) if p else None
            if row is not None:
                row["status"] = "FAILED"
            return None if one else []
        if "from validation_runs where job_id" in s and "request_fingerprint" in s:
            hit = next((dict(v) for v in self.validations.values()
                        if v["job_id"] == p[0] and v.get("request_fingerprint") == p[1]), None)
            return hit if one else ([hit] if hit else [])
        if "from validation_runs where id =" in s:
            row = self.validations.get(p[0])
            return (dict(row) if row else None) if one else ([dict(row)] if row else [])
        if "insert into validation_runs" in s:
            fp = p[4] if len(p) > 4 else None
            if fp is not None:
                dup = next((v for v in self.validations.values()
                            if v["job_id"] == p[0] and v.get("request_fingerprint") == fp), None)
                if dup is not None:
                    return None if one else []
            row = {"id": self._next_id(), "job_id": p[0],
                   "protocol_version": p[1], "evaluation_grid_m": p[2],
                   "reference_id": p[3] if len(p) > 3 else None,
                   "queue_job_id": None, "request_fingerprint": fp,
                   "status": "RUNNING", "overall_status": None, "score": None}
            self.validations[row["id"]] = row
            return row if one else [row]
        if "from validation_runs where job_id" in s and s.startswith("select"):
            rows = [dict(v) for v in self.validations.values() if v["job_id"] == p[0]]
            rows = rows[-1:]
            return (rows[0] if rows else None) if one else rows
        if "from validation_runs vr where vr.id = %s" in s:
            row = self.validations.get(p[0])
            if row is not None:
                out = dict(row)
                out.setdefault("overall_status", None)
                out.setdefault("score", None)
                out.setdefault("status", "RUNNING")
                out.setdefault("evaluation_grid_m", 2.5)
                out.setdefault("protocol_version", "sih26142_v1")
                return out if one else [out]
            return None if one else []
        if "from validation_metrics where validation_run_id" in s:
            return [] if not one else None
        if "from uncertainty_summaries" in s:
            return None if one else []

        # Default: no rows.
        return None if one else []

    def execute(self, sql: str, params=None) -> int:
        """Route mutations through query() and report 1 affected row."""
        result = self.query(sql, params, one=False)
        return result if isinstance(result, int) else 1

    # --- helpers -----------------------------------------------------------

    def add_member(self, project_id: str, user_id: str, role: str = "owner") -> None:
        """Seed a project membership."""
        self.members[(project_id, user_id)] = {
            "project_id": project_id, "user_id": user_id, "role": role}

    def add_model(self, name: str, version: str = "1.0.0") -> str:
        """Seed a model registry row."""
        mid = self._next_id()
        self.models[mid] = {"id": mid, "name": name, "version": version,
                            "framework": "test", "model_card": {}}
        return mid


@pytest.fixture
def fake_db(monkeypatch):
    """Patch backend.db with an in-memory fake and expose its handle."""
    import backend.db as db_mod

    fake = FakeDB()
    fake.add_model("bicubic_4x")
    fake.add_model("custom_mf_sr", "0.1.0")
    fake.add_model("opensr_ldsrs2", "esa-opensr")
    monkeypatch.setattr(db_mod, "query", fake.query)
    monkeypatch.setattr(db_mod, "execute", fake.execute)
    yield fake
