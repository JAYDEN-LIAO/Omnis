# backend/services/platform_service/push_generator.py
"""
LLM 邮件内容生成模块（固定模板 + 结构化数据方案）

- LLM 生成结构化 JSON 数据（保证每次格式一致）
- 固定 HTML 模板渲染，保证邮件样式统一
- 支持所有主流邮件客户端（table 布局 + 内联 CSS）
"""
import asyncio
import json
import datetime
from typing import Optional

from backend.core.logger import get_logger
from backend.core.sanitize import sanitize_email_field, sanitize_url

logger = get_logger("radar.push_generator")

# LLM 使用默认模型（DeepSeek，engine 参数为空时默认走 deepseek 分支）
DEFAULT_ENGINE = ""

# 平台名映射（多处使用）
PLATFORM_MAP = {"wb": "微博", "xhs": "小红书", "bili": "B站", "zhihu": "知乎",
                "dy": "抖音", "ks": "快手", "tieba": "贴吧"}

# 每日简报用的 emoji 平台名映射
PLATFORM_EMOJI_MAP = {"wb": "📱 微博", "xhs": "📕 小红书", "bili": "📺 B站", "zhihu": "💬 知乎",
                      "dy": "🎵 抖音", "ks": "🎬 快手", "tieba": "💬 贴吧"}

# Template loader (Fix P3.3: HTML 模板外置)
import os as _os
_TEMPLATE_DIR = _os.path.join(_os.path.dirname(__file__), "templates")

def _load_template(name: str) -> str:
    """加载 HTML 模板文件"""
    with open(_os.path.join(_TEMPLATE_DIR, name), "r", encoding="utf-8") as f:
        return f.read()

# ============================================================
# 固定 HTML 模板（简约高级，支持基础交互）
# ============================================================

def _build_link_items(urls: list[str]) -> str:
    """构建链接列表 HTML（已净化：URL 协议过滤 + 引号转义）"""
    items = []
    for i, url in enumerate(urls[:10], 1):  # 最多10条
        safe_url = sanitize_url(url)
        # sanitize_url 已对非 http(s) 返回 "about:blank"，已 escape quote
        truncated = (url[:70] + "...") if len(url) > 70 else url
        items.append(
            f'<p style="margin:0 0 8px;font-size:12px;line-height:1.5;">'
            f'<a href="{safe_url}" style="color:#1a3a5c;text-decoration:none;">'
            f'<span style="display:inline-block;min-width:18px;height:18px;background:#1a3a5c;color:#fff;text-align:center;'
            f'border-radius:3px;font-size:10px;line-height:18px;margin-right:8px;vertical-align:middle;">{i}</span>'
            f'<span style="color:#2c3e50;font-size:12px;">{truncated}</span></a></p>'
        )
    return "".join(items) if items else '<p style="margin:0;font-size:12px;color:#8a9aaa;padding:8px 0;">暂无链接</p>'


def _build_daily_keyword_block(keyword: str, items: list, index: int, owner_id: Optional[str] = None) -> str:
    """构建单个关键词的区块
    v2.2 P1#18：新增 owner_id 参数，SQL 查询过滤 p.owner_id = ? OR p.owner_id IS NULL
    """
    if not items:
        return ""

    total = len(items)
    # 取最高风险等级作为块标签
    risk_map = {"critical": 5, "high": 4, "medium": 3, "low": 2, "neutral": 1}
    max_risk = max(items, key=lambda x: risk_map.get(x.get("risk_class", "neutral"), 0))
    risk_class = max_risk.get("risk_class", "neutral")

    risk_meta = {
        "critical": ("#c0392b", "极高"),
        "high": ("#c0392b", "高"),
        "medium": ("#2471a3", "中"),
        "low": ("#1e8449", "低"),
        "neutral": ("#566573", "正常"),
    }
    risk_color, risk_label = risk_meta.get(risk_class, ("#566573", "正常"))

    # 取第一条的核心问题作摘要
    first_item = items[0]
    issue_summary = first_item.get("core_issue", "") or first_item.get("report", "")[:120]
    if len(issue_summary) >= 120:
        issue_summary = issue_summary[:120] + "..."

    # 链接列表 - 从 topic_posts 查实际帖子 URL
    # 修复 v2.2 P1#18：加 owner_id 过滤避免跨租户读 ai_results
    # p.owner_id = ?  → 该用户私有数据
    # p.owner_id IS NULL → 公共/历史数据（兼容 WS4.6 旧数据）
    topic_id = first_item.get("topic_id", "")
    link_items = []
    if topic_id:
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                if owner_id:
                    cursor.execute("""
                        SELECT p.url FROM topic_posts tp
                        JOIN ai_results p ON tp.post_id = p.post_id
                        WHERE tp.topic_id = ? AND tp.is_current = 1
                          AND (p.owner_id = ? OR p.owner_id IS NULL)
                        LIMIT 5
                    """, (topic_id, owner_id))
                else:
                    # 旧路径（无 owner_id 调用方）：保留 NULL-only 过滤，保证公共数据可见
                    cursor.execute("""
                        SELECT p.url FROM topic_posts tp
                        JOIN ai_results p ON tp.post_id = p.post_id
                        WHERE tp.topic_id = ? AND tp.is_current = 1
                          AND p.owner_id IS NULL
                        LIMIT 5
                    """, (topic_id,))
                post_rows = cursor.fetchall()
                for post_row in post_rows:
                    url = post_row[0] if post_row[0] else ""
                    if url:
                        p = first_item.get("platforms", [""])[0] if first_item.get("platforms") else ""
                        pname = PLATFORM_EMOJI_MAP.get(p, p)
                        link_items.append(DAILY_LINK_ITEM_TEMPLATE.format(
                            url=url, platform_icon="🔗", platform_name=pname))
        except Exception:
            pass  # 每日简报链接提取非关键路径，失败时显示"暂无链接"
    link_html = "".join(link_items) if link_items else '<p style="margin:0 12px 6px;font-size:12px;color:#8a9aaa;">暂无帖子链接</p>'

    return DAILY_KEYWORD_BLOCK_TEMPLATE.format(
        keyword_label=f"#{index} {keyword} · {total} 条",
        risk_label=f'<span style="color:{risk_color};">{risk_label}</span>',
        issue_summary=issue_summary,
        link_section=link_html,
        block_open="open" if index == 1 else "",
    )




def _build_batch_alert_item_html(index: int, alert, risk_colors: dict) -> str:
    """构建单条预警的 HTML 片段"""
    color = risk_colors.get(alert.risk_class, "#8c8c8c")
    level_label = {
        "low": "低风险",
        "medium": "中风险",
        "high": "高风险",
        "critical": "极高风险",
        "neutral": "舆情通知",
    }.get(alert.risk_class, "未知")

    urls_html = "".join(
        f'<a href="{u}" style="color:#1a3a5c;text-decoration:none;font-size:12px;">链接{i+1}</a>&nbsp;&nbsp;'
        for i, u in enumerate(alert.urls[:5])
    ) or "<span style='color:#999;font-size:12px;'>无</span>"

    return f"""
    <tr>
      <td style="padding:16px 28px;border-bottom:1px solid #eee;">
        <!-- 序号 + 话题 -->
        <div style="display:flex;align-items:center;margin-bottom:10px;">
          <span style="display:inline-block;width:24px;height:24px;background:#c0392b;color:#fff;
                       text-align:center;border-radius:4px;font-size:13px;line-height:24px;font-weight:bold;
                       margin-right:10px;flex-shrink:0;">{index}</span>
          <h3 style="margin:0;font-size:16px;color:#2c3e50;font-weight:bold;">{alert.core_issue}</h3>
        </div>
        <!-- 风险 + 波及 -->
        <div style="padding-left:34px;margin-bottom:8px;">
          <span style="display:inline-block;padding:2px 10px;background:{color}20;color:{color};
                       border-radius:4px;font-size:12px;font-weight:bold;margin-right:12px;">
            {level_label}（{alert.risk_level}级）
          </span>
          <span style="font-size:13px;color:#7f8c8d;">波及 {alert.post_count} 条</span>
        </div>
        <!-- 预警简报 -->
        <div style="padding-left:34px;font-size:13px;color:#555;line-height:1.6;margin-bottom:10px;">
          {alert.report[:300]}{'...' if len(alert.report) > 300 else ''}
        </div>
        <!-- 链接 -->
        <div style="padding-left:34px;font-size:12px;color:#8a9aaa;">
          溯源链接：{urls_html}
        </div>
      </td>
    </tr>"""


def generate_batch_push_html(keyword: str, platform: str, alerts: list) -> str:
    """
    生成批量预警 HTML 邮件。
    顶部摘要：本轮扫描共 N 条风险舆情，按风险等级分组列出。
    """
    sorted_alerts = sorted(alerts, key=lambda a: a.risk_level, reverse=True)

    risk_colors = {
        "low": "#52c41a",
        "medium": "#faad14",
        "high": "#f5222d",
        "critical": "#d9363e",
        "neutral": "#8c8c8c",
    }
    banner_colors = {
        "critical": ("#c0392b", "#1a1a2e"),
        "high": ("#c0392b", "#16213e"),
        "medium": ("#2471a3", "#1a3a5c"),
        "low": ("#1e8449", "#145a32"),
        "neutral": ("#566573", "#34495e"),
    }

    # 取最高风险等级确定 banner 颜色
    top_risk = sorted_alerts[0].risk_class if sorted_alerts else "neutral"
    banner_color, banner_bg = banner_colors.get(top_risk, ("#566573", "#34495e"))

    # 统计各级别数量
    critical_count = sum(1 for a in sorted_alerts if a.risk_class == "critical")
    high_count = sum(1 for a in sorted_alerts if a.risk_class == "high")
    medium_count = sum(1 for a in sorted_alerts if a.risk_class == "medium")

    # 构建每条预警的 HTML
    alert_items_html = "".join(
        _build_batch_alert_item_html(i + 1, alert, risk_colors)
        for i, alert in enumerate(sorted_alerts)
    )

    now = datetime.datetime.now()
    generated_time = now.strftime("%Y-%m-%d %H:%M")

    platform_display = PLATFORM_MAP.get(platform, platform)

    return BATCH_PUSH_HTML_TEMPLATE.format(
        banner_bg=banner_bg,
        keyword=keyword,
        alert_count=len(sorted_alerts),
        critical_count=critical_count,
        high_count=high_count,
        medium_count=medium_count,
        alert_items=alert_items_html,
        generated_time=generated_time,
    )
