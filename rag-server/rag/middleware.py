from starlette.responses import JSONResponse
from .observability import request_id_context


class RequestTooLarge(Exception):
    pass


class BodyLimitMiddleware:
    def __init__(self, app, limit):
        self.app = app
        self.limit = limit

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = dict(scope.get("headers", []))
        length = headers.get(b"content-length")
        if length:
            try:
                if int(length) > self.limit:
                    response = JSONResponse(
                        {
                            "error": {
                                "code": "BODY_TOO_LARGE",
                                "message": "Request exceeds the upload limit",
                            },
                            "request_id": request_id_context.get(),
                        },
                        status_code=413,
                    )
                    await response(scope, receive, send)
                    return
            except ValueError:
                response = JSONResponse(
                    {
                        "error": {"code": "INVALID_LENGTH", "message": "Invalid Content-Length"},
                        "request_id": request_id_context.get(),
                    },
                    status_code=400,
                )
                await response(scope, receive, send)
                return
        total = 0
        exceeded = False
        replaced = False

        async def bounded_receive():
            nonlocal total, exceeded
            message = await receive()
            total += len(message.get("body", b""))
            if total > self.limit:
                exceeded = True
                raise RequestTooLarge()
            return message

        async def respond_oversized():
            nonlocal replaced
            if not replaced:
                replaced = True
                response = JSONResponse(
                    {
                        "error": {"code": "BODY_TOO_LARGE", "message": "Request exceeds the upload limit"},
                        "request_id": request_id_context.get(),
                    },
                    status_code=413,
                )
                await response(scope, receive, send)

        async def guarded_send(message):
            # Framework parsers may translate receive exceptions into 400. Preserve 413.
            if exceeded:
                await respond_oversized()
            else:
                await send(message)

        try:
            await self.app(scope, bounded_receive, guarded_send)
        except RequestTooLarge:
            await respond_oversized()
