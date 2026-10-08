from sqlalchemy import insert, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.auth.services import AuthContext
from backend.app.categories.db_models import CategoryModel, ResponseNormModel
from backend.shared.schemas import (
    CategoryDTO,
    CreateCategory,
    NormDTO,
    Page,
    PatchCategory,
    SetNorm,
)
from backend.shared.utils import AppError, Paginator


class CategoryUseCase:
    def __init__(self, session: AsyncSession, paginator: Paginator) -> None:
        self.session = session
        self.paginator = paginator


class ListCategoriesUseCase(CategoryUseCase):
    async def execute(
        self,
        ctx: AuthContext,
        limit: int,
        cursor: str | None,
        all_categories: bool = False,
        include_inactive: bool = False,
    ) -> Page[CategoryDTO]:
        if all_categories:
            ctx.require("admin")
        statement = select(CategoryModel)
        if not (all_categories or include_inactive):
            statement = statement.where(CategoryModel.is_active.is_(True))
        return await self.paginator.page(
            self.session,
            statement,
            CategoryModel.id,
            "id",
            CategoryDTO,
            limit,
            cursor,
            {"resource": "categories", "user": ctx.login, "all": all_categories, "inactive": include_inactive},
        )


class CreateCategoryUseCase(CategoryUseCase):
    async def execute(self, ctx: AuthContext, data: CreateCategory) -> CategoryDTO:
        ctx.require("admin")
        category = (
            await self.session.execute(
                insert(CategoryModel)
                .values(
                    name=data.name,
                    description=data.description,
                    is_active=True,
                )
                .returning(CategoryModel)
            )
        ).scalar_one()
        await self.session.execute(
            insert(ResponseNormModel).values(category_id=category.id, response_seconds=data.response_seconds)
        )
        await self.session.commit()
        return CategoryDTO.model_validate(category)


class PatchCategoryUseCase(CategoryUseCase):
    async def execute(self, ctx: AuthContext, category_id: int, data: PatchCategory) -> CategoryDTO:
        ctx.require("admin")
        values = data.model_dump(exclude_unset=True)
        if not values or any(value is None for value in values.values()):
            raise AppError("Нужно передать непустые поля изменения", status_code=400)
        category = (
            await self.session.execute(
                update(CategoryModel).where(CategoryModel.id == category_id).values(**values).returning(CategoryModel)
            )
        ).scalar_one_or_none()
        if category is None:
            raise AppError("Категория не найдена", status_code=404)
        await self.session.commit()
        return CategoryDTO.model_validate(category)


class ListNormsUseCase(CategoryUseCase):
    async def execute(self, ctx: AuthContext, limit: int, cursor: str | None) -> Page[NormDTO]:
        ctx.require("admin")
        return await self.paginator.page(
            self.session,
            select(ResponseNormModel),
            ResponseNormModel.category_id,
            "category_id",
            NormDTO,
            limit,
            cursor,
            {"resource": "norms", "user": ctx.login},
        )


class SetNormUseCase(CategoryUseCase):
    async def execute(self, ctx: AuthContext, category_id: int, data: SetNorm) -> NormDTO:
        ctx.require("admin")
        category = await self.session.scalar(
            select(CategoryModel).where(CategoryModel.id == category_id).with_for_update()
        )
        if category is None:
            raise AppError("Категория не найдена", status_code=404)
        norm = (
            await self.session.execute(
                pg_insert(ResponseNormModel)
                .values(
                    category_id=category_id,
                    response_seconds=data.response_seconds,
                )
                .on_conflict_do_update(
                    index_elements=[ResponseNormModel.category_id], set_={"response_seconds": data.response_seconds}
                )
                .returning(ResponseNormModel)
            )
        ).scalar_one()
        await self.session.commit()
        return NormDTO.model_validate(norm)
