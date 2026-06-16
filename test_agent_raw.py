"""Quick agent test to see raw SSE format"""
import sys, os, json
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

resp = client.post(
    "/api/agent/chat",
    headers={"Authorization": f"Bearer {TOKEN}"},
    json={"messages": [{"role": "user", "content": "你好"}], "session_id": "test-raw"}
)

for i, line in enumerate(resp.iter_lines()):
    if not line or i > 10:
        break
    print(f"LINE {i}: {line!r}")
    raw = line.decode("utf-8") if isinstance(line, bytes) else line
    print(f"TEXT {i}: {raw}")
    if raw.startswith("data: "):
        parsed = raw[6:]
        print(f"DATA {i}: {parsed}")
        try:
            obj = json.loads(parsed)
            print(f"TYPE {i}: {obj}")
        except:
            pass
