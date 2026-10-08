from typing import Annotated

from dishka.integrations.litestar import FromDishka, inject
from litestar import Controller, get, patch, post, put
from litestar.params import QueryParameter

from backend.app.api.parameters import Cursor, Limit, PathID
from backend.app.auth.services import AuthContext
from backend.app.categories.usecases import (
    CreateCategoryUseCase,
    ListCategoriesUseCase,
    ListNormsUseCase,
    PatchCategoryUseCase,
    SetNormUseCase,
)
from backend.shared.schemas import (
    CategoryDTO,
    CreateCategory,
    NormDTO,
    Page,
    PatchCategory,
    SetNorm,
)


class CategoriesController(Controller):
    path = ""

    @get("/categories")
    @inject
    async def categories(
        self,
        ctx: FromDishka[AuthContext],
        usecase: FromDishka[ListCategoriesUseCase],
        limit: Limit = 20,
        cursor: Cursor = None,
        include_inactive: Annotated[bool, QueryParameter()] = False,
    ) -> Page[CategoryDTO]:
        return await usecase.execute(ctx, limit, cursor, include_inactive=include_inactive)

    @get("/admin/categories")
    @inject
    async def admin_categories(
        self,
        ctx: FromDishka[AuthContext],
        usecase: FromDishka[ListCategoriesUseCase],
        limit: Limit = 20,
        cursor: Cursor = None,
    ) -> Page[CategoryDTO]:
        return await usecase.execute(ctx, limit, cursor, all_categories=True)

    @post("/admin/categories")
    @inject
    async def create_category(
        self, data: CreateCategory, ctx: FromDishka[AuthContext], usecase: FromDishka[CreateCategoryUseCase]
    ) -> CategoryDTO:
        return await usecase.execute(ctx, data)

    @patch("/admin/categories/{category_id:int}")
    @inject
    async def patch_category(
        self,
        category_id: PathID,
        data: PatchCategory,
        ctx: FromDishka[AuthContext],
        usecase: FromDishka[PatchCategoryUseCase],
    ) -> CategoryDTO:
        return await usecase.execute(ctx, category_id, data)

    @get("/admin/norms")
    @inject
    async def list_norms(
        self,
        ctx: FromDishka[AuthContext],
        usecase: FromDishka[ListNormsUseCase],
        limit: Limit = 20,
        cursor: Cursor = None,
    ) -> Page[NormDTO]:
        return await usecase.execute(ctx, limit, cursor)

    @put("/admin/norms/{category_id:int}")
    @inject
    async def set_norm(
        self, category_id: PathID, data: SetNorm, ctx: FromDishka[AuthContext], usecase: FromDishka[SetNormUseCase]
    ) -> NormDTO:
        return await usecase.execute(ctx, category_id, data)
