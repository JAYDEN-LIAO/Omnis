"""
验证注入数据后，原空返回项是否恢复正常
只测之前空返回的，加快速率
"""
import sys, os, json, time

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from fastapi.testclient import TestClient
from backend.gateway.main import app
client = TestClient(app)

resp = client.post("/api/auth/login", json={
    "email": "agent_live_test@example.com", "password": "test123456"
})
TOKEN = resp.json()["data"]["access_token"]
HEADERS = {"Authorization": f"Bearer {TOKEN}"}
USER_ID = "u_60753a963a3740ac"

def call_agent(prompt, session="test"):
    result = {"text": "", "tool_calls": [], "tool_results": [], "error": None}
    resp = client.post(
        "/api/agent/chat", headers=HEADERS,
        json={"messages": [{"role": "user", "content": prompt}], "session_id": session},
    )
    current_event = ""
    for line in resp.iter_lines():
        if not line: continue
        line = line.decode("utf-8") if isinstance(line, bytes) else line
        if line.startswith("event: "):
            current_event = line[7:].strip()
        elif line.startswith("data: "):
            raw = line[6:].strip()
            if not raw: continue
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

def test(name, prompt, expect_tool="", expect_data=False, session="test"):
    print(f"\n{'='*60}")
    print(f"[{name}] {prompt}")
    print(f"{'='*60}")
    start = time.time()
    result = call_agent(prompt, session)
    elapsed = time.time() - start

    tools_used = [t.get("tool","") for t in result["tool_calls"]]
    tools_str = " → ".join(tools_used) if tools_used else "(无)"
    text = result["text"][:300] if result["text"] else "(空)"
    error = result["error"]

    # 判断结果
    verdict = "PASS"
    if error:
        verdict = "FAIL"
        reason = f"错误: {error}"
    elif not result["text"] and not tools_used:
        verdict = "FAIL"
        reason = "完全无回复"
    else:
        # 检查工具返回数据
        has_data = False
        for tr in result["tool_results"]:
            d = tr.get("data", [])
            if isinstance(d, list) and len(d) > 0:
                has_data = True
            elif isinstance(d, dict) and len(d) > 0:
                has_data = True
        if expect_data and not has_data:
            verdict = "[WARN] NO_DATA"
            reason = "工具调了但返回空"
        else:
            reason = ""

    tool_detail = ""
    for tr in result["tool_results"]:
        ok = tr.get("success", False)
        d = tr.get("data", "")
        if isinstance(d, (list, dict)):
            d_str = json.dumps(d, ensure_ascii=False)[:100]
        else:
            d_str = str(d)[:100]
        tool_detail += f"\n    {'[OK]' if ok else '❌'} {d_str}"

    print(f"  {verdict} ({elapsed:.1f}s)")
    print(f"  工具: [{tools_str}]")
    print(f"  回复: {text[:200]}")
    if tool_detail:
        print(f"  数据:{tool_detail}")
    if reason:
        print(f"  原因: {reason}")


print("")
print("="*60)
print("  注入数据后的空返回项验证")
print(f"  用户: {USER_ID}")
print("="*60)

# A2 列出订阅 - 现在应有3条
test("A2 列出订阅", "帮我看看我当前订阅了什么", expect_tool="list_subscriptions", expect_data=True, session="s-a2")

# A4 修改频率 - 现在应有小米订阅
test("A4 修改频率", "把小米的扫描频率改成30分钟", expect_tool="update_subscription", session="s-a4")

# A5 删除订阅 - 现在应有数据
test("A5 删除订阅", "帮我删除小米的订阅", expect_tool="remove_subscription", session="s-a5")

# C2 高危预警 - 已注入5条高风险数据
test("C2 高危预警", "上周有什么高危预警", expect_tool="search_alerts", expect_data=True, session="s-c2")

# C3 话题详情 - 已注入4个话题
test("C3 话题详情", "帮我看看小米SU7安全事故的话题详情", expect_tool="get_topic_detail", expect_data=True, session="s-c3")

# D2 打开推送 - 已配置通道
test("D2 启用企业微信", "帮我打开企业微信推送", expect_tool="toggle_channel", session="s-d2")

# E2 切换模型 - 应调用switch_model
test("E2 切换模型", "把分析员的模型换成GPT-4o，API Key是sk-test-key", expect_tool="switch_model", session="s-e2")

# G2 负面舆情 - 已注入风险数据
test("G2 负面舆情", "最近有什么负面舆情", expect_data=True, session="s-g2")

# G4 近期活动 - 已注入审计日志
test("G4 近期活动", "最近两小时发生了什么", expect_tool="get_recent_activity", expect_data=True, session="s-g4")

print("\n"+"="*60)
print("  验证完成")
print("="*60)
