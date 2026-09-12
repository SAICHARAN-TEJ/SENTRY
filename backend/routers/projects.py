"""Project endpoints: create + list projects, auto-add creator as owner."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from backend import db
from backend.auth import get_current_user
from backend.errors import ApiError, AUTH_FORBIDDEN
from backend.schemas import ProjectCreate, ProjectOut

router = APIRouter(prefix="/v1/projects", tags=["projects"])


@router.post("", status_code=201, response_model=ProjectOut)
async def create_project(body: ProjectCreate, user: dict = Depends(get_current_user)) -> ProjectOut:
    """Atomically create project metadata, ownership and provenance."""
    with db.transaction() as tx:
        org_id = body.organization_id
        if org_id is None:
            row = tx.query(
                """
                insert into organizations (name, created_by)
                values (%s, %s) returning id
                """,
                (f"{user['id'][:8]} org", user["id"]), one=True)
            org_id = row["id"]
        else:
            access = tx.query(
                """
                select o.id, (
                    o.created_by = %s or exists (
                        select 1 from projects p
                        join project_members pm on pm.project_id = p.id
                        where p.organization_id = o.id and pm.user_id = %s
                          and pm.role = 'owner'
                    )
                ) as is_owner
                from organizations o where o.id = %s
                """,
                (user["id"], user["id"], org_id), one=True)
            if access is None:
                raise ApiError(AUTH_FORBIDDEN, "organization not found", 404)
            if not access.get("is_owner"):
                raise ApiError(AUTH_FORBIDDEN, "organization ownership required")
        proj = tx.query(
            """
            insert into projects (organization_id, name, default_crs)
            values (%s, %s, %s)
            returning id, name, organization_id, default_crs, created_at
            """,
            (org_id, body.name, body.default_crs), one=True)
        tx.execute(
            """
            insert into project_members (project_id, user_id, role)
            values (%s, %s, 'owner') on conflict do nothing
            """,
            (proj["id"], user["id"]))
        tx.execute(
            """
            insert into provenance_events
                (project_id, entity_type, entity_id, event_type, actor, payload)
            values (%s, 'project', %s, 'project_created', %s, %s)
            """,
            (proj["id"], proj["id"], user["id"], {"name": body.name}))
    return ProjectOut(**proj)  # type: ignore[arg-type]


@router.get("", response_model=list[ProjectOut])
async def list_projects(user: dict = Depends(get_current_user)) -> list[ProjectOut]:
    """List projects the calling user belongs to."""
    rows = db.query(
        """
        select p.id, p.name, p.organization_id, p.default_crs, p.created_at
        from projects p
        join project_members pm on pm.project_id = p.id
        where pm.user_id = %s
        order by p.created_at desc
        """,
        (user["id"],),
    )
    return [ProjectOut(**r) for r in rows]  # type: ignore[misc]
