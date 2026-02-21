from __future__ import annotations

from fastapi import APIRouter

from .team_invites import router as team_invites_router
from .team_members import router as team_members_router
from .team_requirements import router as team_requirements_router
from .team_exports import router as team_exports_router
from .team_settings_projects import router as team_settings_projects_router
from .team_skills import router as team_skills_router
from .team_teams import router as team_teams_router


router = APIRouter(tags=["team"])
router.include_router(team_skills_router)
router.include_router(team_settings_projects_router)
router.include_router(team_teams_router)
router.include_router(team_requirements_router)
router.include_router(team_exports_router)
router.include_router(team_members_router)
router.include_router(team_invites_router)
