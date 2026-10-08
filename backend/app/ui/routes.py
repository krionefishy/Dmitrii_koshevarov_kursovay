from pathlib import Path

from litestar import Controller, Router, get

ROOT = Path(__file__).parent


class UIController(Controller):
    path = ""

    @get(
        "/",
        media_type="text/html",
        sync_to_thread=True,
        include_in_schema=False,
        response_headers={
            "Content-Security-Policy": (
                "default-src 'self'; script-src 'self'; style-src 'self'; "
                "object-src 'none'; base-uri 'none'; frame-ancestors 'none'"
            )
        },
    )
    def index(self) -> str:
        return (ROOT / "index.html").read_text()

    @get("/assets/app.js", media_type="text/javascript", sync_to_thread=True, include_in_schema=False)
    def javascript(self) -> str:
        return (ROOT / "app.js").read_text()

    @get("/assets/styles.css", media_type="text/css", sync_to_thread=True, include_in_schema=False)
    def styles(self) -> str:
        return (ROOT / "styles.css").read_text()


ui_router = Router(path="", route_handlers=[UIController])
