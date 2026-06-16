"""
OutputValidator：爬虫产出物质量检测器

在 CrawlerManager 检测到子进程正常退出 (exit_code == 0) 时调用。
只检测和标记，不修不补。下游 Healer 根据检测结果做恢复决策。
"""
from __future__ import annotations

import json
import re
from typing import Any


class OutputValidator:
    """验证爬虫产出物质量。"""

    # 各平台最低期望采集条数
    MIN_EXPECTED: dict = {
        "wb": 5, "xhs": 5, "bili": 3, "dy": 5, "ks": 3,
    }

    def validate(self, platform: str, posts: list[dict], logs: list | None = None) -> dict[str, Any]:
        """
        全量质量检测入口。

        参数:
            platform: 平台标识 (xhs/dy/ks/bili/wb/tieba/zhihu)
            posts:    本次采集到的笔记/帖子列表
            logs:     采集过程中的日志（暂留接口，当前 unused）

        返回:
            {
                "platform": str,
                "posts": int,              # 总条数
                "expected": int,           # 该平台最低期望
                "issues": [                # 检测到的问题列表
                    {
                        "type": str,       # empty_result | structural_change | likely_blocked | encoding_error
                        "severity": str,   # critical | warning | info
                        "detail": str,     # 可读描述
                    }
                ]
            }
        """
        issues = []
        expected = self.MIN_EXPECTED.get(platform, 3)

        # 1. 数量空洞
        if len(posts) < expected:
            severity = "critical" if len(posts) == 0 else "warning"
            issues.append({
                "type": "empty_result",
                "severity": severity,
                "detail": f"采集到 {len(posts)} 条，预期 ≥ {expected}",
            })

        # 2. 字段空洞（标题/正文大量缺失 → 可能 HTML 选择器失效）
        if posts:
            null_titles = sum(1 for p in posts if not self._safe_str(p.get("title", "")).strip())
            null_contents = sum(1 for p in posts if not self._safe_str(p.get("content", "")).strip())
            total = len(posts)
            if null_titles > total * 0.5:
                issues.append({
                    "type": "structural_change",
                    "severity": "critical",
                    "detail": f"标题缺失率 {null_titles}/{total}，疑似页面结构变更",
                })
            if null_contents > total * 0.5:
                issues.append({
                    "type": "structural_change",
                    "severity": "critical",
                    "detail": f"正文缺失率 {null_contents}/{total}，疑似页面结构变更",
                })

        # 3. 内容同质化（反爬返回了统一提示文案）
        if len(posts) >= 3:
            first50 = [self._safe_str(p.get("content", ""))[:50] for p in posts[:5]]
            if len(set(first50)) <= 1:
                issues.append({
                    "type": "likely_blocked",
                    "severity": "critical",
                    "detail": "多条内容高度相似，可能进入了验证页",
                })

        # 4. 编码异常
        garbled = self._check_garbled(posts)
        if garbled > 0:
            issues.append({
                "type": "encoding_error",
                "severity": "warning",
                "detail": f"检测到 {garbled} 条含异常字符",
            })

        return {
            "platform": platform,
            "posts": len(posts),
            "expected": expected,
            "issues": issues,
        }

    # ──────────────── 内部工具 ────────────────

    @staticmethod
    def _safe_str(v: Any) -> str:
        return str(v) if v is not None else ""

    @staticmethod
    def _check_garbled(posts: list[dict]) -> int:
        count = 0
        for p in posts:
            text = json.dumps(p, ensure_ascii=False)
            if len(re.findall(r"[�\ufffd]", text)) > 50:
                count += 1
        return count
