"""Bound incoming bodies before JSON/form parsing, including chunked uploads."""
from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse


class RequestSizeLimit:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        limit = (25 if scope.get('path') == '/api/upload' else 4) * 1024 * 1024
        headers = dict(scope.get('headers', []))
        try:
            size = int(headers.get(b'content-length', b'0'))
        except ValueError:
            size = limit + 1
        if size > limit:
            return await JSONResponse({'detail': 'Request exceeds the allowed size.'}, status_code=413)(scope, receive, send)
        received = 0

        async def limited_receive():
            nonlocal received
            message = await receive()
            if message['type'] == 'http.request':
                received += len(message.get('body', b''))
                if received > limit:
                    raise HTTPException(413, 'Request exceeds the allowed size.')
            return message

        await self.app(scope, limited_receive, send)
