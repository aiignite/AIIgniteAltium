from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.files.uploaded_project import UploadedProject


async def get_owned_project(db: AsyncSession, project_id: UUID, user_id: UUID) -> UploadedProject:
    project = await db.get(UploadedProject, project_id)
    if project is None or project.is_deleted or str(project.user_id) != str(user_id):
        raise HTTPException(404, "工程不存在")
    return project
