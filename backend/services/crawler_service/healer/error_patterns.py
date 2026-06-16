"""
爬虫错误模式库 — 启发式匹配（快速路径）
每条模式的 regex 只匹配错误信号，通过否定断言排除"成功绕过"等假阳性
"""
import re

CRAWLER_ERROR_PATTERNS = [
    {
        "name": "ip_blocked",
        "patterns": [
            r"^(?!.*(?:成功|跳过|绕过)).*IP.*(?:block|封|限制|ban)",
            r"(?i)too many requests",
            r"\b429\b",
            r"访问过于频繁",
            r"(?<!成功)请求被拒绝",
        ],
        "recovery": "rotate_proxy",
        "severity": "medium",
    },
    {
        "name": "login_expired",
        "patterns": [
            r"login.*(?:expir|过期|失效|失败)",
            r"请.*登录",
            r"会话.*过期",
            r"session.*expir",
            r"cookie.*invalid",
            r"auth.*(?:fail|denied)",
        ],
        "recovery": "re_login",
        "severity": "high",
    },
    {
        "name": "rate_limited",
        "patterns": [
            r"(?i)rate.*limit",
            r"请求.*过快",
            r"操作频繁",
            r"frequency.*exceed",
        ],
        "recovery": "slow_down",
        "severity": "low",
    },
    {
        "name": "captcha_required",
        "patterns": [
            r"verify_check",
            r"滑块",
            r"captcha",
            r"验证码",
            r"人机验证",
        ],
        "recovery": "escalate",
        "severity": "critical",
    },
    {
        "name": "network_error",
        "patterns": [
            r"ConnectError",
            r"Connection.*refused",
            r"(?<!no )Timeout",
            r"\btimeout\b",
            r"NetworkError",
        ],
        "recovery": "retry_with_backoff",
        "severity": "low",
    },
]


def classify_error(log_lines: list[str]) -> dict | None:
    """
    对一段日志行做全文扫描（非逐行），返回第一个命中。
    扫描全部行而非逐行判断，降低误匹配。
    """
    combined = "\n".join(log_lines[-100:])
    for entry in CRAWLER_ERROR_PATTERNS:
        for pat in entry["patterns"]:
            if re.search(pat, combined, re.IGNORECASE):
                return {
                    "error_type": entry["name"],
                    "recovery": entry["recovery"],
                    "severity": entry["severity"],
                    "source": "heuristic",
                }
    return None
