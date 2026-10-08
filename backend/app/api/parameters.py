from typing import Annotated

from litestar.params import Parameter, PathParameter

from backend.shared.schemas import MAX_ID

Limit = Annotated[int, Parameter(ge=1, le=100)]
Cursor = Annotated[str | None, Parameter(max_length=2048)]
PathID = Annotated[int, PathParameter(ge=1, le=MAX_ID)]
