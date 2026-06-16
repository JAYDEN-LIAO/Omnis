"""
web_search 专项测试 — 验证全网搜索功能
"""
import sys, os, json, time

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from fastapi.testclient import TestClient
from backend.gateway.main import app

client = TestClient(app)

# 登录
resp = client.post("/api/auth/login", json={
    "email": "agent_live_test@example.com", "password": "test123456"
})
if resp.status_code != 200:
    client.post("/api/auth/register", json={
        "email": "agent_live_test@example.com", "password": "test123456", "nickname": "搜索测试"
    })
    resp = client.post("/api/auth/login", json={"email": "agent_live_test@example.com", "password": "test123456"})

TOKEN = resp.json()["data"]["access_token"]
HEADERS = {"Authorization": f"Bearer {TOKEN}"}

def call_agent(prompt, session="test-ws"):
    result = {"text": "", "tool_calls": [], "tool_results": [], "error": None}
    resp = client.post(
        "/api/agent/chat",
        headers=HEADERS,
        json={"messages": [{"role": "user", "content": prompt}], "session_id": session},
    )
    current_event = ""
    for line in resp.iter_lines():
        if not line:
            continue
        line = line.decode("utf-8") if isinstance(line, bytes) else line
        if line.startswith("event: "):
            current_event = line[7:].strip()
        elif line.startswith("data: "):
            raw = line[6:].strip()
            if not raw:
                continue
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                data = raw
            if current_event == "text":
                result["text"] += data if isinstance(data, str) else ""
            elif current_event == "tool_call":
                result["tool_calls"].append(data)
            elif current_event == "tool_result":
                result["tool_results"].append(data)
            elif current_event == "error":
                result["error"] = data
            elif current_event == "done":
                break
    return result

def test(name, prompt, session="test-ws"):
    print(f"\n{'='*60}")
    print(f"[{name}] 用户: {prompt}")
    print(f"{'='*60}")
    start = time.time()
    result = call_agent(prompt, session)
    elapsed = time.time() - start
    text = result["text"][:500] if result["text"] else "(空)"
    tools = [t.get("tool","?") for t in result["tool_calls"]]
    print(f"  耗时: {elapsed:.1f}s")
    print(f"  工具: {' → '.join(tools) if tools else '(无)'}")
    print(f"  回复: {text}")
    if result["error"]:
        print(f"  [错误] {result['error']}")

# C1: search_alerts
test("C1 数据查询", "最近微博上关于小米的讨论有哪些", "test-c1")

# F1: web_search
test("F1 全网搜索", "帮我在网上搜一下小米SU7的最新消息", "test-f1")
