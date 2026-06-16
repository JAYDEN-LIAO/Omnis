# backend/services/radar_service/push_generator.py
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

PUSH_HTML_TEMPLATE = _load_template("push_alert.html")


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


def render_push_html(data: dict) -> str:
    """
    用固定模板渲染预警邮件 HTML。

    data 字段：
        keyword, platform, risk_level, risk_class,
        core_issue, report, post_count, urls, generated_at
    """
    risk_class = data.get("risk_class", "neutral")
    risk_level = data.get("risk_level", 3)

    # 风险等级颜色 + 标签（冷色调高级感）
    risk_meta = {
        "critical": ("#c0392b", "极高风险"),
        "high": ("#c0392b", "高风险"),
        "medium": ("#2471a3", "中风险"),
        "low": ("#1e8449", "低风险"),
        "neutral": ("#566573", "舆情通知"),
    }
    banner_meta = {
        "critical": ("#1a1a2e", "极高风险预警"),
        "high": ("#16213e", "高风险预警"),
        "medium": ("#1a3a5c", "中风险预警"),
        "low": ("#145a32", "低风险提醒"),
        "neutral": ("#34495e", "舆情通知"),
    }

    risk_color, risk_label = risk_meta.get(risk_class, ("#6b7280", "舆情通知"))
    banner_bg, banner_label = banner_meta.get(risk_class, ("#6b7280", "舆情通知"))

    now = datetime.datetime.now()
    generated_date = now.strftime("%Y-%m-%d")
    generated_time = now.strftime("%Y-%m-%d %H:%M")

    # 平台名处理
    platform_display = PLATFORM_MAP.get(data.get("platform", ""), data.get("platform", "全部平台"))

    # 处理 core_issue 和 report（修复 #1.2：XSS / URL 注入净化）
    core_issue = data.get("core_issue", "无") or "无"
    report = data.get("report", "无") or "无"
    core_issue = sanitize_email_field(core_issue)
    report = sanitize_email_field(report)

    # 如果 core_issue 或 report 太长，在摘要里截断
    if len(core_issue) > 200:
        core_issue = core_issue[:200] + "..."

    html = PUSH_HTML_TEMPLATE.format(
        banner_bg=banner_bg,
        banner_icon=banner_label.split()[0],
        banner_label=banner_label,
        generated_date=generated_date,
        keyword=data.get("keyword", "未知关键词"),
        platform=platform_display,
        risk_color=risk_color,
        risk_label=risk_label,
        post_count=data.get("post_count", 1),
        core_issue=core_issue,
        report=report,
        link_count=len(data.get("urls", [])),
        link_items=_build_link_items(data.get("urls", [])),
        generated_time=generated_time,
    )
    return html


# ============================================================
# LLM 结构化数据生成
# ============================================================

LLM_JSON_PROMPT = """你是一个舆情分析数据提取专家。从以下舆情数据中提取关键信息，输出标准 JSON 对象。

输出格式（严格 JSON，禁止其他内容）：
{
  "core_issue": "核心问题简述（50字以内）",
  "report_summary": "预警简报摘要（100字以内，抓取最关键内容）",
  "risk_level": 风险等级数字 1-5,
  "risk_class": "low|medium|high|critical|neutral"
}

注意：
- core_issue 要简洁，直击问题本质
- report_summary 要提炼报告中最有价值的信息
- risk_level 和 risk_class 要根据报告内容判断，不要照抄原文的风险等级
- 只输出 JSON，不要有任何其他文字"""


async def _call_llm_async(prompt: str, text: str) -> Optional[str]:
    """异步调用 LLM，返回文本内容"""
    try:
        from .llm_gateway import call_llm
        loop = asyncio.get_running_loop()
        res = await loop.run_in_executor(
            None,
            lambda: call_llm(
                prompt=prompt,
                text=text,
                response_format="text",
                engine=DEFAULT_ENGINE,
            )
        )
        if res.success and res.data:
            return res.data
        else:
            logger.warning(f"[PushGen] LLM 调用失败: {res.error}")
            return None
    except Exception as e:
        logger.error(f"[PushGen] LLM 调用异常: {e}")
        return None


async def generate_push_data(
    keyword: str,
    platforms: str,
    risk_level: int,
    risk_class: str,
    core_issue: str,
    report: str,
    post_count: int,
    posts_summary: str,
    urls: list[str],
    topic_id: str = "",
) -> dict:
    """
    调用 LLM 提取结构化数据（JSON）。
    返回 dict，失败时返回空 dict。
    """
    input_text = f"""【监控关键词】{keyword}
【涉及平台】{platforms}
【帖子数量】{post_count} 条
【原始风险等级】{risk_level}
【核心问题】{core_issue}
【原始报告内容】
{report}
【帖子摘要示例】
{posts_summary}"""

    result = await _call_llm_async(LLM_JSON_PROMPT, input_text)

    if not result:
        logger.warning(f"[PushGen] LLM 生成结构化数据失败，topic_id={topic_id}")
        return {}

    # 解析 JSON
    try:
        # 清理 markdown 代码块
        text = result.strip()
        if text.startswith("```json"):
            text = text[7:]
        elif text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

        data = json.loads(text)
        logger.info(f"[PushGen] LLM 数据提取成功: {data.get('core_issue', '')}")
        return data
    except json.JSONDecodeError as e:
        logger.error(f"[PushGen] JSON 解析失败: {e}, raw={result[:200]}")
        return {}


# ============================================================
# 每日简报 HTML 模板（汇报 + 回顾风格，区别于预警模板）
# ============================================================

DAILY_SUMMARY_TEMPLATE = _load_template("daily_summary.html")

DAILY_KEYWORD_BLOCK_TEMPLATE = _load_template("daily_keyword_block.html")

DAILY_LINK_ITEM_TEMPLATE = _load_template("daily_link_item.html")


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


async def generate_daily_summary_html(owner_id: Optional[str] = None) -> str:
    """
    生成每日简报 HTML（per-user 隔离）。
    查询今日入库的 topic_summary，汇总后返回 HTML。
    owner_id 必须传入；为空时返回空字符串以避免跨用户数据混合。
    """
    if not owner_id:
        logger.warning("[PushGen] generate_daily_summary_html 缺少 owner_id，跳过")
        return ""

    try:
        from .db_manager import get_db_connection
    except Exception as e:
        logger.error(f"[PushGen] 无法导入 db_manager: {e}")
        return ""

    # 查询今日数据（从 topic_summary，仅取该 owner 的话题聚合结果）
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    today_start = today + " 00:00:00"
    today_end = today + " 23:59:59"
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT keyword, platforms, risk_level, risk_class,
                       core_issue, report, last_seen, topic_id, post_count
                FROM topic_summary
                WHERE last_seen >= ? AND last_seen <= ?
                  AND owner_id = ?
                ORDER BY risk_level DESC, last_seen DESC
            """, (today_start, today_end, owner_id))
            rows = cursor.fetchall()
    except Exception as e:
        logger.error(f"[PushGen] 查询今日舆情失败: {e}")
        return ""

    if not rows:
        logger.info(
            f"[PushGen] 用户 {owner_id[:8]}... 今日({today})无新舆情，跳过简报"
        )
        return ""

    # 构建原始数据列表
    raw_items = []
    for row in rows:
        try:
            platforms_list = json.loads(row[1]) if row[1] else []
        except Exception:
            platforms_list = []
        raw_items.append({
            "keyword": row[0] or "未知",
            "platforms": platforms_list,
            "risk_level": row[2] or 3,
            "risk_class": row[3] or "neutral",
            "core_issue": row[4] or "",
            "report": row[5] or "",
            "last_seen": row[6] or "",
            "topic_id": row[7] or "",
            "post_count": row[8] or 0,
        })

    # 按关键词分组
    keyword_groups: dict[str, list] = {}
    for item in raw_items:
        kw = item["keyword"]
        if kw not in keyword_groups:
            keyword_groups[kw] = []
        keyword_groups[kw].append(item)

    # 统计
    total_count = sum(item.get("post_count", 1) for item in raw_items)
    high_count = sum(1 for i in raw_items if i.get("risk_class") in ("high", "critical"))
    platform_set = set()
    for i in raw_items:
        for p in i.get("platforms", []):
            platform_set.add(p)
    platform_count = len(platform_set)

    # 构建关键词区块
    # 修复 v2.2 P1#18：透传 owner_id 给 _build_daily_keyword_block
    keyword_blocks = ""
    for idx, (kw, items) in enumerate(keyword_groups.items(), 1):
        keyword_blocks += _build_daily_keyword_block(kw, items, idx, owner_id=owner_id)

    # 调用 LLM 生成 AI 总结
    ai_summary = await _generate_daily_summary_text(raw_items, keyword_groups)

    now = datetime.datetime.now()
    report_date = now.strftime("%Y-%m-%d")
    generated_time = now.strftime("%Y-%m-%d %H:%M")

    html = DAILY_SUMMARY_TEMPLATE.format(
        report_date=report_date,
        keyword_count=len(keyword_groups),
        total_count=total_count,
        high_count=high_count,
        platform_count=platform_count,
        keyword_blocks=keyword_blocks,
        ai_summary=ai_summary,
        generated_time=generated_time,
    )
    logger.info(f"[PushGen] 每日简报生成成功: {total_count}条舆情, {len(keyword_groups)}个关键词")
    return html


async def _generate_daily_summary_text(raw_items: list, keyword_groups: dict) -> str:
    """调用 LLM 生成今日舆情总结"""
    if not raw_items:
        return "今日暂无新舆情数据。"

    # 构建输入摘要
    lines = []
    for kw, items in keyword_groups.items():
        risk_classes = [i.get("risk_class", "neutral") for i in items]
        all_platforms = []
        for i in items:
            all_platforms.extend(i.get("platforms", []))
        platforms = list(set(all_platforms))
        p_names = [PLATFORM_MAP.get(p, p) for p in platforms]
        total_posts = sum(item.get("post_count", 1) for item in items)
        lines.append(f"【{kw}】风险等级: {', '.join(risk_classes)}，涉及平台: {', '.join(p_names)}，共 {total_posts} 条")

    input_text = "\n".join(lines[:10])  # 最多10个关键词

    prompt = f"""你是一个舆情监测报告分析师。请根据以下今日舆情数据，生成一段简洁的总结分析。

要求：
1. 总结今日整体舆情态势（50-100字）
2. 指出最需要关注的关键词和风险点
3. 用中性、专业的语气，避免夸大
4. 不要列出具体帖子链接

今日舆情数据：
{input_text}

请直接输出总结文字，不要 JSON，不要列表，只要一段话。"""

    result = await _call_llm_async(prompt, "")
    if not result:
        return "今日舆情态势平稳，暂无异常高危信息。"
    return result.strip()


# ============================================================
# 话题级推送模板（v2.2）
# ============================================================

TOPIC_PUSH_HTML_TEMPLATE = _load_template("topic_push.html")

TOPIC_BATCH_HTML_TEMPLATE = _load_template("topic_batch.html")

TOPIC_BATCH_ITEM_TEMPLATE = _load_template("topic_batch_item.html")


def generate_topic_push_html(topic_data: dict) -> str:
    """
    生成话题级推送 HTML（单话题）。

    topic_data 字段:
        topic_name, summary, core_issue, post_count, platforms,
        heat_pct, risk_level, risk_class, urls
    """
    risk_class = topic_data.get("risk_class", "neutral")
    risk_level = topic_data.get("risk_level", 0)
    risk_meta = {
        "critical": ("#c0392b", "极高风险"),
        "high": ("#c0392b", "高风险"),
        "medium": ("#2471a3", "中风险"),
        "low": ("#1e8449", "低风险"),
        "neutral": ("#566573", "动态"),
    }
    risk_bg, risk_label = risk_meta.get(risk_class, ("#566573", "动态"))

    platforms = topic_data.get("platforms", [])
    platform_count = len(platforms)
    post_count = topic_data.get("post_count", 1)
    heat_pct = topic_data.get("heat_pct", 0)
    heat_color = "#c0392b" if heat_pct > 0 else "#1e8449"

    urls = topic_data.get("urls", [])
    link_items = _build_link_items(urls)

    return TOPIC_PUSH_HTML_TEMPLATE.format(
        topic_name=topic_data.get("topic_name", "未命名话题"),
        risk_bg=risk_bg,
        risk_label=risk_label,
        post_count=post_count,
        platform_count=platform_count,
        heat_pct=f'{"▲" if heat_pct >= 0 else "▼"} {abs(heat_pct)}%',
        heat_color=heat_color,
        summary=topic_data.get("summary", ""),
        core_issue=topic_data.get("core_issue", ""),
        link_count=len(urls),
        link_items=link_items,
        generated_time=datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
    )


def generate_topic_batch_html(topics: list[dict]) -> str:
    """
    生成话题级批量推送 HTML（多条话题合并推送）。

    topics: list of topic_data dicts（与 generate_topic_push_html 同结构）
    """
    topic_items = "".join(
        TOPIC_BATCH_ITEM_TEMPLATE.format(
            topic_name=t.get("topic_name", "未命名"),
            risk_bg={"critical": "#c0392b", "high": "#c0392b", "medium": "#2471a3",
                     "low": "#1e8449"}.get(t.get("risk_class", "neutral"), "#566573"),
            risk_label={"critical": "极高风险", "high": "高风险", "medium": "中风险",
                        "low": "低风险", "neutral": "动态"}.get(t.get("risk_class", "neutral"), "动态"),
            post_count=t.get("post_count", 1),
            platform_count=len(t.get("platforms", [])),
            heat_pct=f'{"▲" if t.get("heat_pct", 0) >= 0 else "▼"} {abs(t.get("heat_pct", 0))}%',
            summary=(t.get("summary") or "")[:200],
        )
        for t in topics
    )

    return TOPIC_BATCH_HTML_TEMPLATE.format(
        topic_count=len(topics),
        topic_items=topic_items,
        generated_time=datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
    )


# ============================================================
# 主入口：生成 HTML
# ============================================================

async def generate_push_html(
    keyword: str,
    platforms: str,
    risk_level: int,
    risk_class: str,
    core_issue: str,
    report: str,
    post_count: int,
    posts_summary: str,
    urls: list[str],
    topic_id: str = "",
) -> str:
    """
    生成精美 HTML 邮件内容。

    流程：LLM 提取结构化数据 → 填入固定模板 → 返回一致风格 HTML
    失败时返回空字符串。
    """
    # 1. LLM 提取结构化数据
    llm_data = await generate_push_data(
        keyword=keyword,
        platforms=platforms,
        risk_level=risk_level,
        risk_class=risk_class,
        core_issue=core_issue,
        report=report,
        post_count=post_count,
        posts_summary=posts_summary,
        urls=urls,
        topic_id=topic_id,
    )

    # 2. 构建最终渲染数据（LLM 数据优先级，但保留原始字段作兜底）
    render_data = {
        "keyword": keyword,
        "platform": platforms,
        "risk_level": risk_level,
        "risk_class": llm_data.get("risk_class", risk_class) if llm_data else risk_class,
        "core_issue": llm_data.get("core_issue", core_issue) if llm_data else core_issue,
        "report": llm_data.get("report_summary", report) if llm_data else report,
        "post_count": post_count,
        "urls": urls,
        "generated_at": datetime.datetime.now().isoformat(),
    }

    # 3. 固定模板渲染
    html = render_push_html(render_data)
    logger.info(f"[PushGen] HTML 生成成功，topic_id={topic_id}")
    return html


# ============================================================
# 批量预警 HTML 模板
# ============================================================

BATCH_PUSH_HTML_TEMPLATE = _load_template("batch_alert.html")


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
