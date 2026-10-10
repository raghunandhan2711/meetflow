"""Local session access, atomic sliding-window limits and secret redaction."""
from collections import deque
import hashlib
import ipaddress
import logging
import math
import re
import secrets
import threading
import time
from starlette.requests import Request
from starlette.responses import JSONResponse
from .config import settings

COOKIE = 'meetflow_session'
SESSION_TTL = 12 * 60 * 60
KEY_PATTERN = re.compile(r'gsk_[A-Za-z0-9]{16,}')


def redact(value):
    if isinstance(value, str):
        for secret in [settings.groq_api_key, settings.hf_token, settings.jira_api_token]:
            if secret:
                value = value.replace(secret, '[REDACTED]')
        return KEY_PATTERN.sub('[REDACTED]', value)
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, dict):
        return {key: redact(item) for key, item in value.items()}
    return value


class SecretLogFilter(logging.Filter):
    def filter(self, record):
        record.msg, record.args = redact(record.getMessage()), ()
        if record.exc_info:
            record.exc_text = redact(logging.Formatter().formatException(record.exc_info))
            record.exc_info = None
        return True


def protect_logs():
    # Request URLs can contain user-entered search text. Do not log them.
    logging.getLogger('uvicorn.access').disabled = True
    for name in ['', 'uvicorn', 'uvicorn.error', 'httpx', 'httpcore']:
        logger = logging.getLogger(name)
        logger.addFilter(SecretLogFilter())
        for handler in logger.handlers:
            handler.addFilter(SecretLogFilter())


class SlidingLimiter:
    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.lock = threading.Lock()
        self.windows = {}

    def admit(self, rules):
        """Atomically admit all rules or reject without charging other windows."""
        now = self.clock()
        with self.lock:
            retry = 0
            for name, limit, seconds in rules:
                queue = self.windows.setdefault(name, deque())
                while queue and queue[0] <= now - seconds:
                    queue.popleft()
                if len(queue) >= limit:
                    retry = max(retry, math.ceil(queue[0] + seconds - now))
            if retry:
                return max(1, retry)
            for name, _, _ in rules:
                self.windows[name].append(now)
        return 0

    def clear(self):
        with self.lock:
            self.windows.clear()


class LocalSessions:
    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.lock = threading.Lock()
        self.tokens = {}

    def issue(self):
        now = self.clock()
        token = secrets.token_urlsafe(32)
        with self.lock:
            self.tokens = {key: expiry for key, expiry in self.tokens.items() if expiry > now}
            if len(self.tokens) >= 128:
                self.tokens.pop(next(iter(self.tokens)))
            self.tokens[hashlib.sha256(token.encode()).hexdigest()] = now + SESSION_TTL
        return token

    def valid(self, token):
        if not token or len(token) > 128:
            return False
        with self.lock:
            return self.tokens.get(hashlib.sha256(token.encode()).hexdigest(), 0) > self.clock()


sessions = LocalSessions()
api_limiter = SlidingLimiter()
groq_limiter = SlidingLimiter()
provider_lock = threading.Lock()
provider_retry_at = 0


def reserve_groq():
    with provider_lock:
        retry = max(0, math.ceil(provider_retry_at - time.monotonic()))
        if not retry:
            retry = groq_limiter.admit([
                ('groq-minute', settings.groq_requests_per_minute, 60),
                ('groq-hour', settings.groq_requests_per_hour, 3600)])
    if retry:
        raise ValueError(f'AI request limit reached. Retry in {retry} seconds. Your transcript is saved.')


def provider_cooldown(value):
    global provider_retry_at
    try:
        seconds = max(1, min(3600, math.ceil(float(value or 60))))
    except (ValueError, TypeError, OverflowError):
        seconds = 60
    with provider_lock:
        provider_retry_at = max(provider_retry_at, time.monotonic() + seconds)
    return seconds


def local_request(request):
    try:
        client_local = ipaddress.ip_address(request.client.host).is_loopback
    except (ValueError, AttributeError):
        return False
    return client_local and request.url.hostname in ('127.0.0.1', 'localhost', '::1')


async def guard(request: Request, call_next):
    response = None
    if not local_request(request):
        response = JSONResponse({'detail': 'This workspace is private to this computer.'}, status_code=403)
    elif request.url.path.startswith('/api/'):
        origin = request.headers.get('origin')
        if request.headers.get('sec-fetch-site') == 'cross-site' or (origin and origin != str(request.base_url).rstrip('/')):
            response = JSONResponse({'detail': 'Cross-origin requests are not allowed.'}, status_code=403)
        elif request.url.path != '/api/health' and not sessions.valid(request.cookies.get(COOKIE)):
            response = JSONResponse({'detail': 'Open or refresh the website to start a private session.'}, status_code=401)
        else:
            client = request.client.host
            rules = [(f'api:{client}', settings.rate_limit_api_per_minute, 60)]
            if request.method not in ('GET', 'HEAD', 'OPTIONS'):
                rules.append((f'writes:{client}', settings.rate_limit_writes_per_minute, 60))
                if request.url.path in ('/api/meetings', '/api/upload') or request.url.path.endswith('/retry'):
                    rules.extend([(f'jobs-minute:{client}', settings.rate_limit_analyses_per_minute, 60),
                                  (f'jobs-hour:{client}', settings.rate_limit_analyses_per_hour, 3600)])
            retry = api_limiter.admit(rules)
            if retry:
                response = JSONResponse({'detail': f'Request limit reached. Retry in {retry} seconds.'},
                                        status_code=429, headers={'Retry-After': str(retry)})
    if response is None:
        response = await call_next(request)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'same-origin'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Content-Security-Policy'] = "default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self' data:; media-src 'self' blob:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    if request.url.path in ('/', '/app') or request.url.path.startswith('/api/'):
        response.headers['Cache-Control'] = 'no-store'
    if request.method == 'GET' and request.url.path in ('/', '/app') and response.status_code == 200:
        if not sessions.valid(request.cookies.get(COOKIE)):
            response.set_cookie(COOKIE, sessions.issue(), max_age=SESSION_TTL, httponly=True,
                                samesite='strict', secure=request.url.scheme == 'https')
    return response
