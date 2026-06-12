"""
v2.2 P4.3：平台别名映射统一常量。
- search_alerts: 平台别名 → 实际值
- get_topic_summary_list: plat_map 简写 → 全名
"""
PLATFORM_ALIAS = {
    "wb": "weibo", "微博": "weibo", "weibo": "weibo",
    "xhs": "xiaohongshu", "小红书": "xiaohongshu", "xiaohongshu": "xiaohongshu",
    "bili": "bilibili", "bilibili": "bilibili", "B站": "bilibili", "b站": "bilibili",
    "tieba": "tieba", "贴吧": "tieba", "百度贴吧": "tieba",
    "zhihu": "zhihu", "知乎": "zhihu",
    "kuaishou": "kuaishou", "快手": "kuaishou",
    "dy": "douyin", "douyin": "douyin", "抖音": "douyin",
}


def normalize_platform(name: str) -> str:
    """统一入口：所有平台名走这里归一化"""
    return PLATFORM_ALIAS.get((name or "").strip().lower(), (name or "").strip().lower())
