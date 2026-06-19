"""
领域情感词典 — 追星/娱乐/舆情场景专用

来自 pipeline升级 3.3 节移植，约 80 个种子词。
"""
from __future__ import annotations

SENTIMENT_DICT: dict[str, set[str]] = {
    "positive": {
        "绝了", "太绝了", "炸裂", "宝藏", "爱了", "太帅了",
        "演技在线", "神颜", "天花板", "yyds", "绝美",
        "太好看了", "惊艳", "出圈", "封神", "经典",
        "帅炸", "美哭", "心动", "入股不亏", "可盐可甜",
        "绝绝子", "太可了", "好绝", "杀疯了",
    },
    "negative": {
        "糊了", "塌房", "翻车", "油腻", "尴尬", "退圈",
        "太丑了", "恶心", "下头", "毁三观", "演技差",
        "面瘫", "抠图", "替身", "耍大牌", "劣迹",
        "割韭菜", "圈钱", "敷衍", "摆烂", "脱粉",
        "回踩", "粉转黑", "滤镜碎了",
    },
    "neutral_hints": {
        "据说", "听说", "可能", "好像", "貌似",
        "传闻", "爆料", "网传", "据传",
    },
}


def classify_sentiment(text: str) -> str:
    """规则层情感判定，零 token 成本，覆盖约 80% 的追星内容。"""
    pos = sum(1 for w in SENTIMENT_DICT["positive"] if w in text)
    neg = sum(1 for w in SENTIMENT_DICT["negative"] if w in text)
    if pos > neg * 2:
        return "positive"
    if neg > pos * 2:
        return "negative"
    return "neutral"  # 含模糊内容，由 LLM 补充判定
