"""Native analysis tools may use the model gateway, never platform HTTP APIs."""
import asyncio
from urllib.parse import urlsplit

from starlette.responses import JSONResponse

from .config import settings


class RunnerBoundary:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        host = urlsplit(settings.dsh_runner_url).hostname
        if scope["type"] == "http" and host and scope.get("client"):
            try:
                addresses = await asyncio.get_running_loop().getaddrinfo(host, None)
            except OSError:
                addresses = []  # A runner absent from Docker DNS cannot connect.
            if scope["client"][0] in {row[4][0] for row in addresses}:
                response = JSONResponse(status_code=403, content={"code": 403, "msg": "Analysis cannot access platform APIs", "data": None})
                return await response(scope, receive, send)
        await self.app(scope, receive, send)
