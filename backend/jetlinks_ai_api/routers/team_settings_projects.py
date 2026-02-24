from __future__ import annotations

import secrets
import sqlite3
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from ..db import fetchall, fetchone, row_to_dict, rows_to_dicts, utc_now_iso
from ..deps import CurrentUser, get_current_user, get_db, get_settings, require_team_admin
from ..project_utils import resolve_project_path, resolve_user_workspace_root, slugify


router = APIRouter(tags=["team"])

class TeamSettings(BaseModel):
    workspace_path: str | None = None
    workspace_root: str | None = None


class UpdateTeamSettingsRequest(BaseModel):
    workspace_path: str | None = Field(default=None, max_length=600)


@router.get("/team/settings", response_model=TeamSettings)
async def get_team_settings(
    user: CurrentUser = Depends(get_current_user),
    settings=Depends(get_settings),  # noqa: ANN001
    db=Depends(get_db),  # noqa: ANN001
) -> TeamSettings:
    row = await fetchone(db, "SELECT workspace_path FROM team_settings WHERE team_id = ?", (user.team_id,))
    data = row_to_dict(row) or {}
    ws = str(data.get("workspace_path") or "").strip()

    workspace_root = settings.workspace_root
    if ws:
        try:
            workspace_root = resolve_project_path(settings, ws)
        except ValueError:
            workspace_root = settings.workspace_root
    try:
        workspace_root = resolve_user_workspace_root(
            settings,
            Path(workspace_root),
            user.team_id,
            user.id,
            user.team_name,
            user.name,
        )
    except Exception:
        workspace_root = Path(workspace_root).expanduser().resolve()

    return TeamSettings(workspace_path=ws or None, workspace_root=str(workspace_root))


@router.put("/team/settings", response_model=TeamSettings)
async def update_team_settings(
    req: UpdateTeamSettingsRequest,
    user: CurrentUser = Depends(get_current_user),
    settings=Depends(get_settings),  # noqa: ANN001
    db=Depends(get_db),  # noqa: ANN001
) -> TeamSettings:
    require_team_admin(user)

    raw = (req.workspace_path or "").strip()
    ws: str | None
    if raw:
        try:
            resolved = resolve_project_path(settings, raw)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        ws = str(resolved)
    else:
        ws = None

    now = utc_now_iso()
    await db.execute(
        """
        INSERT INTO team_settings(team_id, workspace_path, created_at, updated_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(team_id) DO UPDATE SET
          workspace_path = excluded.workspace_path,
          updated_at = excluded.updated_at
        """,
        (user.team_id, ws, now, now),
    )
    await db.commit()

    workspace_root = settings.workspace_root
    if ws:
        try:
            workspace_root = resolve_project_path(settings, ws)
        except ValueError:
            workspace_root = settings.workspace_root
    try:
        workspace_root = resolve_user_workspace_root(
            settings,
            Path(workspace_root),
            user.team_id,
            user.id,
            user.team_name,
            user.name,
        )
    except Exception:
        workspace_root = Path(workspace_root).expanduser().resolve()

    return TeamSettings(workspace_path=ws, workspace_root=str(workspace_root))

class TeamProject(BaseModel):
    id: int
    team_id: int
    name: str
    slug: str
    path: str
    enabled: bool
    created_at: str
    updated_at: str


class TeamProjectCandidate(BaseModel):
    name: str
    path: str
    slug: str
    root: str
    detected_by: str
    already_added: bool


class CreateTeamProjectRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    slug: str | None = Field(default=None, max_length=80)
    path: str = Field(min_length=1, max_length=600)
    enabled: bool = True


class UpdateTeamProjectRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    slug: str | None = Field(default=None, min_length=1, max_length=80)
    path: str | None = Field(default=None, min_length=1, max_length=600)
    enabled: bool | None = None


class ImportTeamProjectsRequest(BaseModel):
    paths: list[str] = Field(min_length=1, max_length=120)
    enabled: bool = True


class TeamProjectImportSkipped(BaseModel):
    path: str
    reason: str


class TeamProjectImportResult(BaseModel):
    created: list[TeamProject] = Field(default_factory=list)
    skipped: list[TeamProjectImportSkipped] = Field(default_factory=list)


class TeamProjectTreeNode(BaseModel):
    name: str
    rel_path: str
    node_type: Literal["dir", "file"]
    has_children: bool = False
    children: list["TeamProjectTreeNode"] = Field(default_factory=list)


TeamProjectTreeNode.model_rebuild()


class TeamProjectReadme(BaseModel):
    exists: bool
    filename: str | None = None
    rel_path: str | None = None
    content: str | None = None
    truncated: bool = False

_PROJECT_DISCOVERY_MARKERS: list[tuple[str, str]] = [
    (".git", "git"),
    ("pyproject.toml", "python"),
    ("requirements.txt", "python"),
    ("package.json", "node"),
    ("go.mod", "go"),
    ("Cargo.toml", "rust"),
    ("pom.xml", "java"),
    ("build.gradle", "gradle"),
    ("build.gradle.kts", "gradle"),
]


def _is_dir(path: Path) -> bool:
    try:
        return path.is_dir()
    except Exception:
        return False


def _visible_entries(dir_path: Path, *, show_hidden: bool, max_entries: int) -> list[Path]:
    try:
        entries = list(dir_path.iterdir())
    except Exception:
        return []

    if not show_hidden:
        entries = [entry for entry in entries if not entry.name.startswith(".")]

    entries.sort(key=lambda p: (0 if _is_dir(p) else 1, p.name.lower()))
    return entries[:max_entries]


def _normalized_path(raw: object) -> str:
    text = str(raw or "").strip()
    if not text:
        return ""
    try:
        return str(Path(text).expanduser().resolve())
    except Exception:
        return text


def _detect_project_marker(path: Path) -> str | None:
    for marker, marker_type in _PROJECT_DISCOVERY_MARKERS:
        try:
            if (path / marker).exists():
                return marker_type
        except Exception:
            continue
    return None


def _has_visible_children(dir_path: Path, *, show_hidden: bool) -> bool:
    try:
        for child in dir_path.iterdir():
            if not show_hidden and child.name.startswith("."):
                continue
            return True
    except Exception:
        return False
    return False


def _build_project_tree_nodes(
    dir_path: Path,
    project_root: Path,
    *,
    depth_remaining: int,
    show_hidden: bool,
    max_entries: int,
) -> list[TeamProjectTreeNode]:
    nodes: list[TeamProjectTreeNode] = []
    for entry in _visible_entries(dir_path, show_hidden=show_hidden, max_entries=max_entries):
        try:
            rel_path = entry.relative_to(project_root).as_posix()
        except Exception:
            continue

        if _is_dir(entry):
            has_children = _has_visible_children(entry, show_hidden=show_hidden)
            children: list[TeamProjectTreeNode] = []
            if has_children and depth_remaining > 1:
                children = _build_project_tree_nodes(
                    entry,
                    project_root,
                    depth_remaining=depth_remaining - 1,
                    show_hidden=show_hidden,
                    max_entries=max_entries,
                )
            nodes.append(
                TeamProjectTreeNode(
                    name=entry.name,
                    rel_path=rel_path,
                    node_type="dir",
                    has_children=has_children,
                    children=children,
                )
            )
            continue

        nodes.append(
            TeamProjectTreeNode(
                name=entry.name,
                rel_path=rel_path,
                node_type="file",
                has_children=False,
                children=[],
            )
        )
    return nodes


_README_CANDIDATES = (
    "README.md",
    "readme.md",
    "README.MD",
    "readme.MD",
    "README.markdown",
    "readme.markdown",
    "README.txt",
    "readme.txt",
    "README",
    "readme",
)

_MAX_README_BYTES = 120 * 1024


def _find_readme(dir_path: Path) -> Path | None:
    for name in _README_CANDIDATES:
        candidate = dir_path / name
        if candidate.exists() and candidate.is_file():
            return candidate

    try:
        scanned = 0
        for entry in dir_path.iterdir():
            scanned += 1
            if scanned > 240:
                break
            if not entry.is_file():
                continue
            lowered = entry.name.lower()
            if not lowered.startswith("readme"):
                continue
            return entry
    except Exception:
        return None
    return None


def _load_readme_payload(base_dir: Path, project_root: Path) -> TeamProjectReadme:
    readme_path = _find_readme(base_dir)
    if not readme_path:
        return TeamProjectReadme(exists=False)

    try:
        rel_path = readme_path.relative_to(project_root).as_posix()
    except Exception:
        rel_path = readme_path.name

    try:
        data = readme_path.read_bytes()
    except Exception:
        return TeamProjectReadme(exists=False)

    truncated = False
    if len(data) > _MAX_README_BYTES:
        data = data[:_MAX_README_BYTES]
        truncated = True

    content = data.decode("utf-8", errors="ignore").strip()
    return TeamProjectReadme(
        exists=True,
        filename=readme_path.name,
        rel_path=rel_path,
        content=content,
        truncated=truncated,
    )


@router.get("/team/projects", response_model=list[TeamProject])
async def list_team_projects(
    user: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),  # noqa: ANN001
) -> list[TeamProject]:
    rows = await fetchall(
        db,
        """
        SELECT id, team_id, name, slug, path, enabled, created_at, updated_at
        FROM team_projects
        WHERE team_id = ?
        ORDER BY id DESC
        """,
        (user.team_id,),
    )
    items = rows_to_dicts(list(rows))
    for it in items:
        it["enabled"] = bool(it.get("enabled"))
    return [TeamProject(**it) for it in items]


@router.get("/team/projects/discover", response_model=list[TeamProjectCandidate])
async def discover_team_projects(
    max_entries: int = Query(default=80, ge=1, le=300),
    include_hidden: bool = Query(default=False),
    include_added: bool = Query(default=False),
    user: CurrentUser = Depends(get_current_user),
    settings=Depends(get_settings),  # noqa: ANN001
    db=Depends(get_db),  # noqa: ANN001
) -> list[TeamProjectCandidate]:
    require_team_admin(user)

    existing_rows = await fetchall(db, "SELECT path FROM team_projects WHERE team_id = ?", (int(user.team_id),))
    existing_paths = {_normalized_path((row_to_dict(row) or {}).get("path")) for row in existing_rows}
    existing_paths.discard("")

    roots = list(getattr(settings, "projects_roots", []) or [])
    if not roots:
        roots = [settings.workspace_root]

    candidates: list[TeamProjectCandidate] = []
    seen_paths: set[str] = set()
    probe_limit = max(max_entries * 5, 200)
    for raw_root in roots:
        try:
            root = Path(raw_root).expanduser().resolve()
        except Exception:
            continue
        if not root.exists() or not root.is_dir():
            continue

        entries = _visible_entries(root, show_hidden=include_hidden, max_entries=probe_limit)
        for entry in entries:
            if not _is_dir(entry):
                continue
            if {".aistaff", ".jetlinks-ai"}.intersection({part.lower() for part in entry.parts}):
                continue

            marker = _detect_project_marker(entry)
            if not marker:
                continue

            path_str = _normalized_path(entry)
            if not path_str or path_str in seen_paths:
                continue
            seen_paths.add(path_str)

            already_added = path_str in existing_paths
            if already_added and not include_added:
                continue

            name = entry.name.strip() or "project"
            candidates.append(
                TeamProjectCandidate(
                    name=name,
                    path=path_str,
                    slug=slugify(name, "project")[:60],
                    root=str(root),
                    detected_by=marker,
                    already_added=already_added,
                )
            )

    candidates.sort(key=lambda it: (it.already_added, it.name.lower(), it.path))
    return candidates[:max_entries]


@router.get("/team/projects/{project_id}/tree", response_model=list[TeamProjectTreeNode])
async def get_team_project_tree(
    project_id: int,
    sub_path: str | None = Query(default=None, max_length=600),
    max_depth: int = Query(default=2, ge=1, le=6),
    max_entries: int = Query(default=120, ge=20, le=500),
    show_hidden: bool = Query(default=False),
    user: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),  # noqa: ANN001
) -> list[TeamProjectTreeNode]:
    row = await fetchone(
        db,
        "SELECT id, team_id, path FROM team_projects WHERE id = ?",
        (int(project_id),),
    )
    project = row_to_dict(row)
    if not project or int(project.get("team_id") or 0) != user.team_id:
        raise HTTPException(status_code=404, detail="项目不存在")

    path_raw = str(project.get("path") or "").strip()
    if not path_raw:
        raise HTTPException(status_code=400, detail="项目路径为空")

    try:
        project_root = Path(path_raw).expanduser().resolve()
    except Exception:
        raise HTTPException(status_code=400, detail="项目路径无效") from None

    if not project_root.exists() or not project_root.is_dir():
        raise HTTPException(status_code=400, detail="项目路径不存在或不可访问")

    target_dir = project_root
    clean_sub_path = str(sub_path or "").strip().replace("\\", "/").strip("/")
    if clean_sub_path:
        try:
            target_dir = (project_root / clean_sub_path).resolve()
        except Exception:
            raise HTTPException(status_code=400, detail="目录路径非法") from None
        try:
            _ = target_dir.relative_to(project_root)
        except Exception:
            raise HTTPException(status_code=400, detail="目录路径非法") from None
        if not target_dir.exists() or not target_dir.is_dir():
            raise HTTPException(status_code=404, detail="目录不存在")

    return _build_project_tree_nodes(
        target_dir,
        project_root,
        depth_remaining=max_depth,
        show_hidden=show_hidden,
        max_entries=max_entries,
    )


@router.get("/team/workspace/tree", response_model=list[TeamProjectTreeNode])
async def get_team_workspace_tree(
    sub_path: str | None = Query(default=None, max_length=600),
    max_depth: int = Query(default=2, ge=1, le=6),
    max_entries: int = Query(default=120, ge=20, le=500),
    show_hidden: bool = Query(default=False),
    user: CurrentUser = Depends(get_current_user),
    settings=Depends(get_settings),  # noqa: ANN001
    db=Depends(get_db),  # noqa: ANN001
) -> list[TeamProjectTreeNode]:
    row = await fetchone(db, "SELECT workspace_path FROM team_settings WHERE team_id = ?", (user.team_id,))
    data = row_to_dict(row) or {}
    workspace_raw = str(data.get("workspace_path") or "").strip()

    if workspace_raw:
        try:
            workspace_root = resolve_project_path(settings, workspace_raw)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
    else:
        workspace_root = settings.workspace_root

    try:
        workspace_root = Path(workspace_root).expanduser().resolve()
    except Exception:
        raise HTTPException(status_code=400, detail="工作区路径无效") from None

    try:
        workspace_root = resolve_user_workspace_root(
            settings,
            workspace_root,
            user.team_id,
            user.id,
            user.team_name,
            user.name,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"用户工作区路径无效：{e}") from e

    if not workspace_root.exists() or not workspace_root.is_dir():
        raise HTTPException(status_code=400, detail="工作区路径不存在或不可访问")

    target_dir = workspace_root
    clean_sub_path = str(sub_path or "").strip().replace("\\", "/").strip("/")
    if clean_sub_path:
        try:
            target_dir = (workspace_root / clean_sub_path).resolve()
        except Exception:
            raise HTTPException(status_code=400, detail="目录路径非法") from None
        try:
            _ = target_dir.relative_to(workspace_root)
        except Exception:
            raise HTTPException(status_code=400, detail="目录路径非法") from None
        if not target_dir.exists() or not target_dir.is_dir():
            raise HTTPException(status_code=404, detail="目录不存在")

    return _build_project_tree_nodes(
        target_dir,
        workspace_root,
        depth_remaining=max_depth,
        show_hidden=show_hidden,
        max_entries=max_entries,
    )


@router.get("/team/projects/{project_id}/readme", response_model=TeamProjectReadme)
async def get_team_project_readme(
    project_id: int,
    user: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),  # noqa: ANN001
) -> TeamProjectReadme:
    row = await fetchone(
        db,
        "SELECT id, team_id, path FROM team_projects WHERE id = ?",
        (int(project_id),),
    )
    project = row_to_dict(row)
    if not project or int(project.get("team_id") or 0) != user.team_id:
        raise HTTPException(status_code=404, detail="项目不存在")

    path_raw = str(project.get("path") or "").strip()
    if not path_raw:
        raise HTTPException(status_code=400, detail="项目路径为空")

    try:
        project_root = Path(path_raw).expanduser().resolve()
    except Exception:
        raise HTTPException(status_code=400, detail="项目路径无效") from None

    if not project_root.exists() or not project_root.is_dir():
        raise HTTPException(status_code=400, detail="项目路径不存在或不可访问")

    return _load_readme_payload(project_root, project_root)


@router.get("/team/workspace/readme", response_model=TeamProjectReadme)
async def get_team_workspace_readme(
    user: CurrentUser = Depends(get_current_user),
    settings=Depends(get_settings),  # noqa: ANN001
    db=Depends(get_db),  # noqa: ANN001
) -> TeamProjectReadme:
    row = await fetchone(db, "SELECT workspace_path FROM team_settings WHERE team_id = ?", (user.team_id,))
    data = row_to_dict(row) or {}
    workspace_raw = str(data.get("workspace_path") or "").strip()

    if workspace_raw:
        try:
            workspace_root = resolve_project_path(settings, workspace_raw)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
    else:
        workspace_root = settings.workspace_root

    try:
        workspace_root = Path(workspace_root).expanduser().resolve()
    except Exception:
        raise HTTPException(status_code=400, detail="工作区路径无效") from None

    try:
        workspace_root = resolve_user_workspace_root(
            settings,
            workspace_root,
            user.team_id,
            user.id,
            user.team_name,
            user.name,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"用户工作区路径无效：{e}") from e

    if not workspace_root.exists() or not workspace_root.is_dir():
        raise HTTPException(status_code=400, detail="工作区路径不存在或不可访问")

    return _load_readme_payload(workspace_root, workspace_root)


@router.post("/team/projects", response_model=TeamProject)
async def create_team_project(
    req: CreateTeamProjectRequest,
    user: CurrentUser = Depends(get_current_user),
    settings=Depends(get_settings),  # noqa: ANN001
    db=Depends(get_db),  # noqa: ANN001
) -> TeamProject:
    require_team_admin(user)

    now = utc_now_iso()
    try:
        resolved = resolve_project_path(settings, req.path)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    base = req.slug.strip() if req.slug else req.name.strip()
    base_slug = slugify(base, "project")[:60]
    if not base_slug:
        base_slug = f"project-{secrets.token_hex(3)}"

    project_id: int | None = None
    for i in range(0, 50):
        slug = base_slug if i == 0 else f"{base_slug}-{i + 1}"
        try:
            cur = await db.execute(
                """
                INSERT INTO team_projects(team_id, name, slug, path, enabled, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (user.team_id, req.name.strip(), slug, str(resolved), 1 if req.enabled else 0, now, now),
            )
            project_id = int(cur.lastrowid)
            await db.commit()
            break
        except sqlite3.IntegrityError:
            continue

    if not project_id:
        raise HTTPException(status_code=400, detail="slug 已存在，请换一个")

    row = await fetchone(
        db,
        """
        SELECT id, team_id, name, slug, path, enabled, created_at, updated_at
        FROM team_projects
        WHERE id = ?
        """,
        (project_id,),
    )
    data = row_to_dict(row)
    if not data:
        raise HTTPException(status_code=500, detail="创建失败")
    data["enabled"] = bool(data.get("enabled"))
    return TeamProject(**data)


@router.post("/team/projects/import", response_model=TeamProjectImportResult)
async def import_team_projects(
    req: ImportTeamProjectsRequest,
    user: CurrentUser = Depends(get_current_user),
    settings=Depends(get_settings),  # noqa: ANN001
    db=Depends(get_db),  # noqa: ANN001
) -> TeamProjectImportResult:
    require_team_admin(user)

    existing_rows = await fetchall(db, "SELECT path FROM team_projects WHERE team_id = ?", (int(user.team_id),))
    existing_paths = {_normalized_path((row_to_dict(row) or {}).get("path")) for row in existing_rows}
    existing_paths.discard("")

    now = utc_now_iso()
    seen_input_paths: set[str] = set()
    created: list[TeamProject] = []
    skipped: list[TeamProjectImportSkipped] = []

    for raw_path in req.paths:
        source_path = str(raw_path or "").strip()
        if not source_path:
            skipped.append(TeamProjectImportSkipped(path="", reason="路径为空"))
            continue

        try:
            resolved = resolve_project_path(settings, source_path)
        except ValueError as e:
            skipped.append(TeamProjectImportSkipped(path=source_path, reason=str(e)))
            continue

        normalized_path = _normalized_path(resolved)
        if normalized_path in seen_input_paths:
            skipped.append(TeamProjectImportSkipped(path=normalized_path, reason="请求里重复路径"))
            continue
        seen_input_paths.add(normalized_path)

        if normalized_path in existing_paths:
            skipped.append(TeamProjectImportSkipped(path=normalized_path, reason="项目已存在"))
            continue

        project_name = resolved.name.strip() or "project"
        base_slug = slugify(project_name, "project")[:60]
        if not base_slug:
            base_slug = f"project-{secrets.token_hex(3)}"

        project_id: int | None = None
        for i in range(0, 50):
            slug = base_slug if i == 0 else f"{base_slug}-{i + 1}"
            try:
                cur = await db.execute(
                    """
                    INSERT INTO team_projects(team_id, name, slug, path, enabled, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (int(user.team_id), project_name, slug, normalized_path, 1 if req.enabled else 0, now, now),
                )
                project_id = int(cur.lastrowid)
                break
            except sqlite3.IntegrityError:
                continue

        if not project_id:
            skipped.append(TeamProjectImportSkipped(path=normalized_path, reason="slug 冲突，导入失败"))
            continue

        existing_paths.add(normalized_path)
        row = await fetchone(
            db,
            """
            SELECT id, team_id, name, slug, path, enabled, created_at, updated_at
            FROM team_projects
            WHERE id = ?
            """,
            (project_id,),
        )
        project_data = row_to_dict(row)
        if not project_data:
            skipped.append(TeamProjectImportSkipped(path=normalized_path, reason="写入后读取失败"))
            continue
        project_data["enabled"] = bool(project_data.get("enabled"))
        created.append(TeamProject(**project_data))

    await db.commit()
    return TeamProjectImportResult(created=created, skipped=skipped)


@router.put("/team/projects/{project_id}", response_model=TeamProject)
async def update_team_project(
    project_id: int,
    req: UpdateTeamProjectRequest,
    user: CurrentUser = Depends(get_current_user),
    settings=Depends(get_settings),  # noqa: ANN001
    db=Depends(get_db),  # noqa: ANN001
) -> TeamProject:
    require_team_admin(user)

    existing_row = await fetchone(
        db,
        "SELECT id, team_id, slug FROM team_projects WHERE id = ?",
        (int(project_id),),
    )
    existing = row_to_dict(existing_row)
    if not existing or int(existing["team_id"]) != user.team_id:
        raise HTTPException(status_code=404, detail="项目不存在")

    fields: list[str] = []
    values: list = []
    if req.name is not None:
        fields.append("name = ?")
        values.append(req.name.strip())
    if req.slug is not None:
        fields.append("slug = ?")
        values.append(slugify(req.slug, str(existing.get("slug") or "project"))[:60])
    if req.path is not None:
        try:
            resolved = resolve_project_path(settings, req.path)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        fields.append("path = ?")
        values.append(str(resolved))
    if req.enabled is not None:
        fields.append("enabled = ?")
        values.append(1 if req.enabled else 0)

    if not fields:
        row = await fetchone(
            db,
            """
            SELECT id, team_id, name, slug, path, enabled, created_at, updated_at
            FROM team_projects
            WHERE id = ?
            """,
            (int(project_id),),
        )
        data = row_to_dict(row)
        if not data:
            raise HTTPException(status_code=404, detail="项目不存在")
        data["enabled"] = bool(data.get("enabled"))
        return TeamProject(**data)

    fields.append("updated_at = ?")
    values.append(utc_now_iso())
    values.append(int(project_id))

    try:
        await db.execute(f"UPDATE team_projects SET {', '.join(fields)} WHERE id = ?", tuple(values))
        await db.commit()
    except sqlite3.IntegrityError as e:
        raise HTTPException(status_code=400, detail=f"更新失败：{e}") from e

    row = await fetchone(
        db,
        """
        SELECT id, team_id, name, slug, path, enabled, created_at, updated_at
        FROM team_projects
        WHERE id = ?
        """,
        (int(project_id),),
    )
    data = row_to_dict(row)
    if not data:
        raise HTTPException(status_code=404, detail="项目不存在")
    data["enabled"] = bool(data.get("enabled"))
    return TeamProject(**data)


@router.delete("/team/projects/{project_id}")
async def delete_team_project(
    project_id: int,
    user: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),  # noqa: ANN001
) -> dict:
    require_team_admin(user)

    existing_row = await fetchone(
        db,
        "SELECT id, team_id FROM team_projects WHERE id = ?",
        (int(project_id),),
    )
    existing = row_to_dict(existing_row)
    if not existing or int(existing["team_id"]) != user.team_id:
        raise HTTPException(status_code=404, detail="项目不存在")

    await db.execute("DELETE FROM team_projects WHERE id = ?", (int(project_id),))
    await db.commit()
    return {"ok": True}
