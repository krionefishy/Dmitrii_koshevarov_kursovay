from litestar import Router

from backend.app.api.health import HealthController
from backend.app.auth.routes import AuthController
from backend.app.categories.routes import CategoriesController
from backend.app.tickets.routes import TicketsController
from backend.app.users.routes import UsersController

api_router = Router(
    path="/api/v1",
    route_handlers=[HealthController, AuthController, CategoriesController, TicketsController, UsersController],
)
