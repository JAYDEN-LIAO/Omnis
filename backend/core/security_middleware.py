"""
WS3: 安全加固中间件

集中管理 FastAPI 应用的安全增强：
  - SecurityHeadersMiddleware: 注入安全响应头（CSP, HSTS, XFO 等）
  - MaxBodySizeMiddleware: 限制请求体大小
"""
import json
from typing import Callable, Awaitable
from fastapi import FastAPI, Request, Response
from backend.core.logger import get_logger

logger = get_logger("core.security")


# ============================================================
# WS3.2: 安全响应头中间件
# ============================================================

SECURITY_HEADERS = {
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'",
    "X-Frame-Options": "DENY",
    "X-Content-Type-Options": "nosniff",
    "X-XSS-Protection": "0",
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains; preload",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
    "Cross-Origin-Embedder-Policy": "require-corp",
    "Server": "",
}


def add_security_headers_middleware(app: FastAPI):
    """
    挂载安全响应头中间件并用默认值覆盖不安全响应头。
    /docs /redoc /openapi.json 跳过 CSP（静态资源需要加载外部 JS/CSS）。
    """
    _skip_csp_prefixes = ("/docs", "/redoc", "/openapi.json")

    @app.middleware("http")
    async def security_headers_middleware(request: Request, call_next: Callable[[Request], Awaitable[Response]]):
        response: Response = await call_next(request)

        # Swagger / OpenAPI 页面需要加载外部 CDN 资源，跳过严格 CSP
        path = request.url.path
        if any(path == p or path.startswith(p + "/") or path.startswith(p) for p in _skip_csp_prefixes):
            for header_to_remove in ("server", "x-powered-by"):
                if header_to_remove in response.headers:
                    del response.headers[header_to_remove]
            return response

        for header_name, header_value in SECURITY_HEADERS.items():
            if header_name not in response.headers:
                response.headers[header_name] = header_value

        for header_to_remove in ("server", "x-powered-by"):
            if header_to_remove in response.headers:
                del response.headers[header_to_remove]

        return response

    logger.info("[SecurityMiddleware] 安全响应头中间件已挂载")


# ============================================================
# WS3.3: 请求体大小限制
# ============================================================

_MAX_BODY_SIZE = 1024 * 1024  # 1 MB

def add_max_body_size_middleware(app: FastAPI, max_size: int = _MAX_BODY_SIZE):
    @app.middleware("http")
    async def max_body_size_middleware(request: Request, call_next: Callable[[Request], Awaitable[Response]]):
        if request.method in ("POST", "PUT", "PATCH"):
            content_length = request.headers.get("content-length", "0")
            try:
                if int(content_length) > max_size:
                    return Response(
                        status_code=413,
                        content=json.dumps({"code": 413, "msg": "请求体过大，上限 1MB", "data": None}),
                        media_type="application/json",
                    )
            except (ValueError, TypeError):
                pass
        return await call_next(request)

    logger.info(f"[SecurityMiddleware] 请求体大小限制中间件已挂载 (max={max_size} bytes)")
