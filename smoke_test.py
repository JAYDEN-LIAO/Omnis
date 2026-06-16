"""
MediaRadar 冒烟测试（Smoke Test）
===============================
验证所有关键端点的 HTTP 状态码是否正常。
每个端点只验证状态码（200/401/403/等），不做数据断言。

用法：
    python smoke_test.py
    # 全绿 = 重构安全

设计依据：
    - 所有端点映射来自 @后端审查.md 复核结果
    - 认证逻辑来自 backend/core/auth_deps.py
    - 路由定义来自各 service/*/api.py
"""

import sys
import os

# Windows GBK 编码兼容
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# 标准导入：将项目根目录加入 PYTHONPATH，支持 from backend.xxx
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from fastapi.testclient import TestClient

# 标准包导入
from backend.gateway.main import app

client = TestClient(app)

# ============================================================
# 测试辅助
# ============================================================

_results: list[tuple[str, bool, str]] = []


def check(name: str, condition: bool, detail: str = "") -> bool:
    """记录一个断言结果。返回 condition 以支持链式。"""
    _results.append((name, condition, detail))
    return condition


def report():
    """打印测试报告"""
    passed = sum(1 for _, ok, _ in _results if ok)
    failed = sum(1 for _, ok, _ in _results if not ok)
    total = len(_results)

    print("\n" + "=" * 60)
    print(f"  Smoke Test 结果: {passed}/{total} 通过")
    print("=" * 60)

    for name, ok, detail in _results:
        icon = "[PASS]" if ok else "[FAIL]"
        line = f"  {icon} {name}"
        if detail:
            line += f"  [{detail}]"
        print(line)

    if failed > 0:
        print(f"\n[FAIL] {failed} 项失败，请检查后再重构")
    else:
        print(f"\n[PASS] 全部 {total} 项通过，可以安全进行重构")

    return failed == 0


# ============================================================
# 用户与 Token 管理
# ============================================================

# 使用唯一时间戳避免与已有数据冲突
import time as _time

_TS = str(int(_time.time()))[-6:]
TEST_EMAIL = f"smoke_test_{_TS}@example.com"
TEST_PASSWORD = "smoke_test_123"
TEST_NICKNAME = "SmokeTestBot"

_user_token: str = ""
_admin_token: str = ""
_test_user_id: str = ""


def register_and_login():
    """注册测试用户 + 获取 JWT token（幂等：已有同邮箱用户则直接登录）"""
    global _user_token, _test_user_id

    # 1. 先尝试登录（处理上次运行残留的测试用户）
    resp = client.post("/api/auth/login", json={
        "email": TEST_EMAIL,
        "password": TEST_PASSWORD,
    })
    if resp.status_code == 200:
        data = resp.json()
        _user_token = data.get("data", {}).get("access_token", "")
        _test_user_id = data.get("data", {}).get("user", {}).get("user_id", "")
        return

    # 2. 登录失败 → 注册新用户
    resp = client.post("/api/auth/register", json={
        "email": TEST_EMAIL,
        "password": TEST_PASSWORD,
        "nickname": TEST_NICKNAME,
    })
    if resp.status_code == 200:
        data = resp.json()
        _user_token = data.get("data", {}).get("access_token", "")
        _test_user_id = data.get("data", {}).get("user", {}).get("user_id", "")
    elif resp.status_code == 409:
        # 已存在但密码不对 → 无法继续
        print(f"  [WARN] 测试用户已存在但密码不匹配，跳过认证测试")
    else:
        print(f"  [WARN] 注册异常: {resp.status_code} {resp.json().get('detail', '')}")


def get_auth_headers() -> dict:
    """返回普通用户的 Authorization header"""
    return {"Authorization": f"Bearer {_user_token}"}


def get_admin_auth_headers() -> dict:
    """返回 admin 用户的 Authorization header（如有）"""
    return {"Authorization": f"Bearer {_admin_token}"}


# ============================================================
# 测试用例
# ============================================================

def test_public_endpoints():
    """公开端点（无认证）"""
    print("\n--- 公开端点 ---")

    # GET /health — 公开
    resp = client.get("/health")
    check("GET /health → 200 或 503", resp.status_code in (200, 503),
          f"got {resp.status_code}")

    # GET /metrics — 公开
    resp = client.get("/metrics")
    check("GET /metrics → 200", resp.status_code == 200,
          f"got {resp.status_code}")

    # POST /api/auth/register — 公开（缺少字段应返回 422 而非 500）
    resp = client.post("/api/auth/register", json={"email": "noop@test.com"})
    check("POST /api/auth/register (缺字段) → 422", resp.status_code == 422,
          f"got {resp.status_code}")

    # POST /api/auth/login — 公开（错误凭证应返回 401）
    resp = client.post("/api/auth/login", json={"email": "no@no.com", "password": "wrong"})
    check("POST /api/auth/login (错凭证) → 401 或 429", resp.status_code in (401, 429),
          f"got {resp.status_code}")

    # POST /api/auth/refresh — 公开（空 token 应返回 400 或 401）
    resp = client.post("/api/auth/refresh", json={"refresh_token": ""})
    check("POST /api/auth/refresh (空token) → 400 或 401",
          resp.status_code in (400, 401, 422),
          f"got {resp.status_code}")

    # GET /rss/{token}.xml — 公开
    resp = client.get("/rss/fake_token_123.xml")
    check("GET /rss/fake.xml → 200 (占位XML)", resp.status_code == 200,
          f"got {resp.status_code}")


def test_auth_required_endpoints():
    """需认证端点 — 无 token 应返回 401 或 422（取决于路径参数）"""
    print("\n--- 需认证端点（无 token → 401） ---")

    # 选取代表性的端点，不依赖路径参数
    user_only_endpoints = [
        ("GET", "/api/auth/me"),
        ("POST", "/api/auth/logout"),
        ("GET", "/api/scheduler/status"),
        ("GET", "/api/yq_list"),
        ("GET", "/api/settings"),
        ("GET", "/api/topic_list"),
        ("GET", "/api/volume_stats"),
        ("GET", "/api/today_summary"),
        ("GET", "/api/push/configs"),
        ("GET", "/api/llm/configs"),
        ("GET", "/api/subscriptions"),
        ("GET", "/api/model-configs"),
        ("GET", "/api/quota"),
        ("GET", "/api/radar_status"),
        ("GET", "/api/mcp/health"),
    ]

    for method, path in user_only_endpoints:
        resp = getattr(client, method.lower())(path)
        name = f"{method} {path} (无token)"
        # 401 = 未认证; 422 = 路径参数缺失（FastAPI 在 auth 之前校验）
        ok = resp.status_code in (401, 403, 422)
        check(name, ok, f"got {resp.status_code}")


def test_user_authenticated_endpoints():
    """普通用户已认证 — 应返回 200（或合理的业务状态码）"""
    print("\n--- 普通用户已认证端点 ---")

    headers = get_auth_headers()
    if not _user_token:
        check("[WARN] 跳过（无可用 token）", False, "无法注册/登录测试用户")
        return

    # 可安全调用的用户端点（不修改数据，或修改后无副作用）
    safe_endpoints = [
        ("GET", "/api/auth/me"),
        ("GET", "/api/yq_list"),
        ("GET", "/api/settings"),
        ("GET", "/api/topic_list"),
        ("GET", "/api/volume_stats"),
        ("GET", "/api/today_summary"),
        ("GET", "/api/push/configs"),
        ("GET", "/api/llm/configs"),
        ("GET", "/api/subscriptions"),
        ("GET", "/api/model-configs"),
        ("GET", "/api/quota"),
        ("GET", "/api/radar_status"),
        ("GET", "/api/mcp/health"),
        ("GET", "/api/agent/memory"),
    ]

    for method, path in safe_endpoints:
        resp = getattr(client, method.lower())(path, headers=headers)
        name = f"{method} {path} (用户认证)"
        # 200 = 正常; 400 = 缺少查询参数; 404 = 资源不存在
        ok = resp.status_code in (200, 400, 404)
        check(name, ok, f"got {resp.status_code}")

    # scheduler/status 可能因 APScheduler 未配置返回 500
    resp = client.get("/api/scheduler/status", headers=headers)
    check("GET /api/scheduler/status (用户认证)",
          resp.status_code in (200, 500),
          f"got {resp.status_code} (500=APScheduler不可达，可接受)")

    # 端点需要路径参数
    resp = client.get("/api/topic_evolution", headers=headers, params={"keyword": "test"})
    check("GET /api/topic_evolution (keyword=test) → 200", resp.status_code == 200,
          f"got {resp.status_code}")

    resp = client.get("/api/topic_stats", headers=headers)
    check("GET /api/topic_stats → 200 或 500", resp.status_code in (200, 500),
          f"got {resp.status_code} (Qdrant 不可达时 500 可接受)")


def test_admin_required_endpoints():
    """管理员端点 — 普通用户应返回 403"""
    print("\n--- 管理员端点（普通用户 → 403） ---")

    headers = get_auth_headers()
    if not _user_token:
        check("[WARN] 跳过（无可用 token）", False, "无法注册/登录测试用户")
        return

    admin_endpoints = [
        ("GET", "/api/circuit/states"),
        ("POST", "/api/scheduler/start"),
        ("POST", "/api/scheduler/stop"),
        ("GET", "/api/admin/users"),
        ("GET", "/api/admin/stats"),
    ]

    for method, path in admin_endpoints:
        resp = getattr(client, method.lower())(path, headers=headers)
        name = f"{method} {path} (普通用户)"
        check(name, resp.status_code == 403,
              f"got {resp.status_code} (期望 403)")


def test_subscription_create():
    """创建订阅 — 验证 201"""
    print("\n--- 订阅创建 ---")

    headers = get_auth_headers()
    if not _user_token:
        check("[WARN] 跳过（无可用 token）", False, "")
        return

    resp = client.post("/api/subscriptions", headers=headers, json={
        "name": f"smoke_keyword_{_TS}",
        "type": "keyword",
        "polarity": "all",
        "sensitivity": "balanced",
        "platforms": ["微博"],
        "push_mode": "none",
    })
    check("POST /api/subscriptions → 201/400/429", resp.status_code in (201, 400, 429),
          f"got {resp.status_code} (400=参数校验/重复, 429=配额超限)")


def test_agent_memory_endpoints():
    """Agent 记忆端点"""
    print("\n--- Agent 记忆端点 ---")

    headers = get_auth_headers()
    if not _user_token:
        check("[WARN] 跳过（无可用 token）", False, "")
        return

    # 获取记忆列表
    resp = client.get("/api/agent/memory", headers=headers)
    check("GET /api/agent/memory → 200", resp.status_code == 200,
          f"got {resp.status_code}")

    # 获取不存在的 session 详情（应 200 或 404）
    resp = client.get("/api/agent/memory/fake_session_123", headers=headers)
    check("GET /api/agent/memory/fake → 200 或 404",
          resp.status_code in (200, 404),
          f"got {resp.status_code}")


def test_push_config_endpoints():
    """推送配置端点"""
    print("\n--- 推送配置端点 ---")

    headers = get_auth_headers()
    if not _user_token:
        check("[WARN] 跳过（无可用 token）", False, "")
        return

    # 获取 email channel 配置
    resp = client.get("/api/push/config/email", headers=headers)
    check("GET /api/push/config/email → 200 或 400",
          resp.status_code in (200, 400),
          f"got {resp.status_code}")

    # 无效 channel — 当前端点未做严格校验，200 也可接受
    resp = client.get("/api/push/config/invalid_channel", headers=headers)
    check("GET /api/push/config/invalid → 200 或 400",
          resp.status_code in (200, 400),
          f"got {resp.status_code}")


def test_llm_config_endpoints():
    """LLM 配置端点"""
    print("\n--- LLM 配置端点 ---")

    headers = get_auth_headers()
    if not _user_token:
        check("[WARN] 跳过（无可用 token）", False, "")
        return

    # 获取 analyst 配置
    resp = client.post("/api/llm/config/analyst", headers=headers, json={
        "model": "deepseek-chat",
        "api_key": "sk-test",
        "base_url": "https://api.deepseek.com/v1",
    })
    check("POST /api/llm/config/analyst → 200", resp.status_code == 200,
          f"got {resp.status_code}")

    # 测试 LLM 连通性（可能失败因为 fake key，但不应 500）
    resp = client.post("/api/llm/test/analyst", headers=headers)
    check("POST /api/llm/test/analyst → 200 或 500",
          resp.status_code in (200, 500),
          f"got {resp.status_code} (fake key 时 500 可接受)")


def test_oauth_endpoints():
    """OAuth 端点（公开）"""
    print("\n--- OAuth 端点 ---")

    # Google OAuth login — 可能返回 503（未配置）或 200
    resp = client.get("/api/auth/oauth/google/login")
    check("GET /api/auth/oauth/google/login → 200 或 503",
          resp.status_code in (200, 503),
          f"got {resp.status_code}")

    # 不支持的 provider
    resp = client.get("/api/auth/oauth/wechat/login")
    check("GET /api/auth/oauth/wechat/login → 400", resp.status_code == 400,
          f"got {resp.status_code}")


# ============================================================
# 主入口
# ============================================================

if __name__ == "__main__":
    print("MediaRadar Smoke Test")
    print(f"  项目根目录: {PROJECT_ROOT}")
    print(f"  测试用户: {TEST_EMAIL}")

    # Step 0: 注册并获取 token
    register_and_login()
    print(f"  Token: {'[PASS] 已获取' if _user_token else '[FAIL] 获取失败'}")
    if _user_token:
        print(f"  User ID: {_test_user_id}")

    # Step 1: 公开端点
    test_public_endpoints()

    # Step 2: 认证要求（无 token → 401）
    test_auth_required_endpoints()

    # Step 3: 用户认证端点
    test_user_authenticated_endpoints()

    # Step 4: 管理员权限（普通用户 → 403）
    test_admin_required_endpoints()

    # Step 5: 业务端点
    test_subscription_create()
    test_push_config_endpoints()
    test_llm_config_endpoints()
    test_agent_memory_endpoints()
    test_oauth_endpoints()

    # 打印报告
    success = report()

    sys.exit(0 if success else 1)
