# backend/core/config.py
import os
from urllib.parse import urlsplit
from dotenv import load_dotenv

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.dirname(CURRENT_DIR)
PROJECT_ROOT = os.path.dirname(BACKEND_DIR)

DATA_DIR = os.path.join(BACKEND_DIR, "data")
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR, exist_ok=True)

ENV_PATH = os.path.join(PROJECT_ROOT, ".env")
load_dotenv(dotenv_path=ENV_PATH)


class Settings:
    # ======== 默认模型配置（所有 Agent 的兜底配置）=======
    _def_api_key = (os.getenv("DEFAULT_API_KEY", "") or ""
                    or os.getenv("LLM_API_KEY", ""))
    DEFAULT_API_KEY = _def_api_key

    _def_base_url = (os.getenv("DEFAULT_BASE_URL", "").strip()
                     or os.getenv("LLM_BASE_URL", "").strip()
                     or "https://api.deepseek.com/v1")
    DEFAULT_BASE_URL = _def_base_url

    _def_model = (os.getenv("DEFAULT_MODEL", "")
                  or os.getenv("LLM_MODEL", "")
                  or "deepseek-chat")
    DEFAULT_MODEL = _def_model

    # ======== 配置2: 风险分析管线（回退: ANALYST/REVIEWER → DEFAULT）========
    _analyst_api_key = os.getenv("ANALYST_API_KEY", "").strip() or _def_api_key
    ANALYST_API_KEY = _analyst_api_key
    _analyst_base_url = os.getenv("ANALYST_BASE_URL", "").strip() or _def_base_url
    ANALYST_BASE_URL = _analyst_base_url
    _analyst_model = os.getenv("ANALYST_MODEL", "").strip() or _def_model
    ANALYST_MODEL = _analyst_model

    _reviewer_api_key = os.getenv("REVIEWER_API_KEY", "").strip() or _def_api_key
    REVIEWER_API_KEY = _reviewer_api_key
    _reviewer_base_url = os.getenv("REVIEWER_BASE_URL", "").strip() or _def_base_url
    REVIEWER_BASE_URL = _reviewer_base_url
    _reviewer_model = os.getenv("REVIEWER_MODEL", "").strip() or _def_model
    REVIEWER_MODEL = _reviewer_model

    # ======== AI 助手模型（回退: ASSISTANT → DEFAULT）========
    # 环境变量兼容 ASSISTANT_*（优先）和 AGENT_*（向后兼容）
    _assistant_api_key = os.getenv("ASSISTANT_API_KEY", "").strip() or os.getenv("AGENT_API_KEY", "").strip() or _def_api_key
    ASSISTANT_API_KEY = _assistant_api_key
    _assistant_base_url = os.getenv("ASSISTANT_BASE_URL", "").strip() or os.getenv("AGENT_BASE_URL", "").strip() or _def_base_url
    ASSISTANT_BASE_URL = _assistant_base_url
    _assistant_model = os.getenv("ASSISTANT_MODEL", "").strip() or os.getenv("AGENT_MODEL", "").strip() or _def_model
    ASSISTANT_MODEL = _assistant_model

    # ======== 配置3: 向量引擎（回退: EMBEDDING → DEFAULT）========
    _emb_api_key = os.getenv("EMBEDDING_API_KEY", "") or _def_api_key
    EMBEDDING_API_KEY = _emb_api_key
    _emb_base_url = os.getenv("EMBEDDING_BASE_URL", "").strip() or _def_base_url
    EMBEDDING_BASE_URL = _emb_base_url
    _emb_model = os.getenv("EMBEDDING_MODEL", "").strip() or _def_model
    EMBEDDING_MODEL = _emb_model

    # ======== 配置4: 视觉引擎（回退: VISION → DEFAULT）========
    _vis_api_key = os.getenv("VISION_API_KEY", "") or _def_api_key
    VISION_API_KEY = _vis_api_key
    _vis_base_url = os.getenv("VISION_BASE_URL", "").strip() or _def_base_url
    VISION_BASE_URL = _vis_base_url
    _vis_model = os.getenv("VISION_MODEL", "").strip() or _def_model
    VISION_MODEL = _vis_model

    # ======== 配置5: 多 Pipeline 模型配置 ========
    _guide_model = os.getenv("GUIDE_MODEL", "").strip() or _def_model
    GUIDE_MODEL = _guide_model
    _celebrity_model = os.getenv("CELEBRITY_MODEL", "").strip() or _def_model
    CELEBRITY_MODEL = _celebrity_model
    _briefing_model = os.getenv("BRIEFING_MODEL", "").strip() or _def_model
    BRIEFING_MODEL = _briefing_model

    # ======== 配置6: Qdrant 向量数据库（RAG 知识库） ========
    QDRANT_HOST = os.getenv("QDRANT_HOST", "127.0.0.1")
    QDRANT_PORT = int(os.getenv("QDRANT_PORT", "6333"))
    QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "yq_history")

    # ======== 配置6: Qdrant 话题演化追踪集合 ========
    TOPIC_COLLECTION = os.getenv("TOPIC_COLLECTION", "topic_evolution")

    # ======== Agent 配置 ========
    AGENT_MCP_ENABLED = os.getenv("AGENT_MCP_ENABLED", "false").lower() == "true"
    AGENT_MCP_TRANSPORT = os.getenv("AGENT_MCP_TRANSPORT", "http").strip()
    AGENT_MAX_ITERATIONS = int(os.getenv("AGENT_MAX_ITERATIONS", "6"))
    AGENT_MEMORY_TTL_DAYS = int(os.getenv("AGENT_MEMORY_TTL_DAYS", "90"))
    AGENT_TOKEN_BUDGET = int(os.getenv("AGENT_TOKEN_BUDGET", "1500"))
    AGENT_REFLECTION_ENABLED = os.getenv("AGENT_REFLECTION_ENABLED", "true").lower() == "true"
    AGENT_SELF_HEALING_ENABLED = os.getenv("AGENT_SELF_HEALING_ENABLED", "true").lower() == "true"

    # v2.2 P1: Agent 循环安全网
    AGENT_TOOL_TIMEOUT = int(os.getenv("AGENT_TOOL_TIMEOUT", "120"))
    AGENT_MAX_TOOL_RESULT_CHARS = int(os.getenv("AGENT_MAX_TOOL_RESULT_CHARS", "3000"))

    # ======== 系统路径配置 ========
    STATE_DB_PATH = os.getenv("STATE_DB_PATH", os.path.join(DATA_DIR, "radar_state.db"))
    CRAWLER_DB_PATH = os.getenv("CRAWLER_DB_PATH", os.path.join(BACKEND_DIR, "data", "sqlite_tables.db"))
    LOG_DIR = os.getenv("LOG_DIR", os.path.join(PROJECT_ROOT, "logs"))

    # ======== 环境标识（用于 CORS 等配置按环境区分）=======
    ENV = os.getenv("ENV", "dev").lower()  # dev | prod
    ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "").strip()  # 逗号分隔
    METRICS_TOKEN = os.getenv("METRICS_TOKEN", "").strip()  # prod 下 /metrics 的鉴权令牌

    # ======== API 认证配置 ========
    API_KEYS = os.getenv("API_KEYS", "")

    # ======== JWT 认证配置 ========
    _raw_jwt_secret = os.getenv("JWT_SECRET", "")
    JWT_SECRET = _raw_jwt_secret.strip() if _raw_jwt_secret else ""
    JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256").strip()
    JWT_EXPIRE_HOURS = int(os.getenv("JWT_EXPIRE_HOURS", "24"))
    JWT_REFRESH_EXPIRE_HOURS = int(os.getenv("JWT_REFRESH_EXPIRE_HOURS", "168"))

    # ======== 游客访问配置 ========
    GUEST_TOKEN_EXPIRE_HOURS = int(os.getenv("GUEST_TOKEN_EXPIRE_HOURS", "2"))
    GUEST_RATE_LIMIT = int(os.getenv("GUEST_RATE_LIMIT", "20"))

    # ======== OAuth 配置 ========
    GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "").strip()
    GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "").strip()
    WECHAT_APP_ID = os.getenv("WECHAT_APP_ID", "").strip()
    WECHAT_APP_SECRET = os.getenv("WECHAT_APP_SECRET", "").strip()
    OAUTH_REDIRECT_BASE = os.getenv("OAUTH_REDIRECT_BASE", "https://omnis.jaydennn.xyz").strip()
    OAUTH_HTTPS_PROXY = os.getenv("OAUTH_HTTPS_PROXY", "").strip()

    # ======== 爬虫 Cookie 配置 ========
    WEIBO_COOKIE = os.getenv("WEIBO_COOKIE", "").strip()

    # ======== 日志配置 ========
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
    LOG_FORMAT = os.getenv("LOG_FORMAT", "text").lower()  # text | json
    LOG_TO_FILE = os.getenv("LOG_TO_FILE", "true").lower() == "true"
    LOG_TO_CONSOLE = os.getenv("LOG_TO_CONSOLE", "true").lower() == "true"
    LOG_MAX_BYTES = int(os.getenv("LOG_MAX_BYTES", str(10 * 1024 * 1024)))
    LOG_BACKUP_COUNT = int(os.getenv("LOG_BACKUP_COUNT", "5"))
    LOG_USE_UTC = os.getenv("LOG_USE_UTC", "false").lower() == "true"


settings = Settings()


# ── 生产启动强校验（ref #3）──
# 校验在模块导入时执行，uvicorn 以「导入 app」方式启动同样会触发，
# 不再依赖仅在 __main__ 分支打印的软警告。
WEAK_JWT_SECRETS = frozenset({
    "dev-secret-change-me-in-prod-please-32bytes", "your-secret-key",
    "changeme", "secret", "jwt-secret", "test", "default", "123456",
})
ALLOWED_JWT_ALGORITHMS = frozenset({"HS256", "HS384", "HS512"})


def _validate_jwt_secret(s=settings) -> None:
    """校验 JWT 密钥与算法；prod 一律 raise，dev 仅告警。"""
    import secrets
    import warnings

    secret = s.JWT_SECRET
    env = s.ENV
    if not secret:
        if env == "prod":
            raise RuntimeError(
                "[CONFIG] JWT_SECRET 未配置或为空。生产环境必须设置 JWT_SECRET。"
                "生成方式：python -c 'import secrets; print(secrets.token_urlsafe(48))'"
            )
        dev_secret = "dev-" + secrets.token_urlsafe(32)
        s.JWT_SECRET = dev_secret
        # 回写环境变量，使 reload 子进程与 crypto_utils 复用同一密钥
        os.environ["JWT_SECRET"] = dev_secret
        warnings.warn(
            "[CONFIG] JWT_SECRET 未配置，自动生成临时 dev 密钥；进程重启后 token 失效。",
            RuntimeWarning,
            stacklevel=2,
        )
        return

    if secret.strip().lower() in WEAK_JWT_SECRETS:
        if env == "prod":
            raise RuntimeError("[CONFIG] JWT_SECRET 为已知示例/弱值，生产环境禁止启动")
        warnings.warn("[CONFIG] JWT_SECRET 为示例值，仅 dev 模式放行", RuntimeWarning, stacklevel=2)

    min_len = 32 if env == "prod" else 16
    if len(secret) < min_len:
        if env == "prod":
            raise RuntimeError(f"[CONFIG] JWT_SECRET 太短（{len(secret)} 字符 < {min_len}）")
        warnings.warn(
            f"[CONFIG] JWT_SECRET 太短（{len(secret)} 字符）。dev 模式放行。",
            RuntimeWarning,
            stacklevel=2,
        )

    if s.JWT_ALGORITHM not in ALLOWED_JWT_ALGORITHMS:
        raise RuntimeError(
            f"[CONFIG] 不支持的 JWT_ALGORITHM：{s.JWT_ALGORITHM}；"
            f"允许 {sorted(ALLOWED_JWT_ALGORITHMS)}"
        )


def parse_allowed_origins(s=settings) -> list[str]:
    """prod 下解析并强校验 CORS 源；缺失或非法一律 raise（fail-fast）。"""
    raw = (s.ALLOWED_ORIGINS or "").strip()
    if not raw:
        if s.ENV == "prod":
            raise RuntimeError("[CONFIG] ENV=prod 必须配置 ALLOWED_ORIGINS（逗号分隔的 https 源）")
        return []
    items = [item.strip().rstrip("/") for item in raw.split(",") if item.strip()]
    if s.ENV != "prod":
        return items
    for origin in items:
        parts = urlsplit(origin)
        if (
            "*" in origin
            or parts.scheme != "https"
            or not parts.hostname
            or parts.username or parts.password
            or parts.path not in ("", "/")
            or parts.query or parts.fragment
        ):
            raise RuntimeError(
                "[CONFIG] ALLOWED_ORIGINS 只能是 https 源，且不得含通配、路径、查询或内嵌凭据"
            )
    return items


def validate_production_settings(s=settings) -> None:
    """prod 启动前汇总校验；dev 直接放行。"""
    if s.ENV != "prod":
        return
    _validate_jwt_secret(s)
    parse_allowed_origins(s)
    if not (os.getenv("DB_ENCRYPTION_KEY", "").strip() or s.JWT_SECRET):
        raise RuntimeError("[CONFIG] ENV=prod 缺少可用的加密密钥（DB_ENCRYPTION_KEY / JWT_SECRET）")
    if not s.METRICS_TOKEN:
        raise RuntimeError("[CONFIG] ENV=prod 必须配置 METRICS_TOKEN，否则 /metrics 将无鉴权暴露")


_validate_jwt_secret()
validate_production_settings()


# ── 多 Pipeline 模型解析 ──

NODE_OVERRIDES = {
    "risk/analyst": "DEFAULT_MODEL",
    "risk/reviewer": "DEFAULT_MODEL",
    "risk/director": "DEFAULT_MODEL",
}


def resolve_model(pipeline_id: str, node: str = "") -> str:
    """优先级：节点覆盖 > Pipeline 默认 > 全局 DEFAULT"""
    node_key = f"{pipeline_id}/{node}"
    node_env = NODE_OVERRIDES.get(node_key)
    if node_env:
        val = getattr(settings, node_env, "")
        if val:
            return val
    pipeline_model = getattr(settings, f"{pipeline_id.upper()}_MODEL", "")
    return pipeline_model or settings.DEFAULT_MODEL


def update_llm_config(agent: str, config: dict) -> bool:
    _BAD_VALUES = {"test", "sk-test", "", "gpt-4"}
    prefix_map = {
        "default":   "DEFAULT",
        "assistant": "ASSISTANT",
        "embedding": "EMBEDDING",
        "vision":    "VISION",
    }
    if agent not in prefix_map:
        return False
    prefix = prefix_map[agent]
    for field, value in config.items():
        if not isinstance(value, str) or value.strip().lower() in _BAD_VALUES:
            continue
        attr = f"{prefix}_{field.upper()}"
        if hasattr(settings, attr):
            setattr(settings, attr, value.strip())
    return True


def get_effective_llm_config(agent: str) -> dict:
    prefix_map = {
        "assistant": "ASSISTANT",
        "embedding": "EMBEDDING",
        "vision":    "VISION",
    }
    prefix = prefix_map.get(agent)
    if not prefix:
        return {}

    def field(name):
        specific = getattr(settings, f"{prefix}_{name.upper()}", "") or ""
        return specific if specific else getattr(settings, f"DEFAULT_{name.upper()}", "") or ""

    return {
        "api_key": field("api_key"),
        "base_url": field("base_url"),
        "model": field("model"),
    }


def get_agent_config() -> tuple[str, str, str]:
    def field(name: str) -> str:
        v = getattr(settings, f"ASSISTANT_{name.upper()}", "") or ""
        if v: return v
        return getattr(settings, f"DEFAULT_{name.upper()}", "") or ""
    return field("api_key"), field("base_url"), field("model")


def get_agent_config_for_user(owner_id: str) -> tuple[str, str, str]:
    try:
        from backend.shared.db.model_config_db import get_effective_config
        cfg = get_effective_config(owner_id, "AGENT")
        return (cfg.get("api_key", ""), cfg.get("base_url", ""), cfg.get("model", ""))
    except Exception:
        return get_agent_config()
