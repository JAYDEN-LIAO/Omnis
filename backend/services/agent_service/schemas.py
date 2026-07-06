"""
数据契约层（Data Schemas）

所有 Pydantic 模型定义，集中管理，
供其他模块导入使用。
"""

from typing import Optional, TypedDict
from pydantic import BaseModel, Field


class ScreenerResult(BaseModel):
    """Screener 阶段 LLM 返回结果"""
    analysis_process: str = Field(default="", description="模型的思考分析过程")
    is_relevant: bool = Field(default=False, description="是否相关")
    matched_keyword: str = Field(default="", description="匹配到的具体实体名")
    reason: str = Field(default="", description="判断理由")
    needs_vision: bool = Field(default=False, description="是否需要调用视觉模型看图确认")
    generated_title: str = Field(default="", description="LLM生成的标准化的舆情标题（用于后续聚类）")


class AnalystResult(BaseModel):
    """Analyst 节点 LLM 返回结果"""
    analysis_process: str = Field(default="", description="风险评估的思考过程")
    sentiment: str = Field(default="Neutral", description="情感倾向")
    risk_level: int = Field(default=1, description="风险等级1-5")
    core_issue: str = Field(default="无", description="核心问题概括")


class ReviewerResult(BaseModel):
    """Reviewer 节点 LLM 返回结果"""
    analysis_process: str = Field(default="", description="交叉验证思考过程")
    is_confirmed: bool = Field(default=False, description="是否同意高风险")
    adjusted_risk_level: int = Field(default=2, description="调整后的风险等级")
    reason: str = Field(default="", description="维持或驳回的理由")


# ============================================================
# 多 Pipeline Screener Schema（攻略/追星/简报）
# ============================================================


class GuideScreenerResult(BaseModel):
    """攻略线 Screener 返回结果"""
    generated_title: str = Field(default="", description="标准化标题（20字内）")
    info_type: str = Field(default="guide", description="信息类型: guide/review/comparison/experience")
    topic: str = Field(default="", description="核心主题（如长沙旅游、AirPods实测）")
    sentiment: str = Field(default="neutral", description="情感: positive/negative/mixed")
    key_points: list[str] = Field(default_factory=list, description="关键信息点")
    usefulness: int = Field(default=1, description="有用性评分 1-5")
    is_relevant: bool = Field(default=False, description="是否相关")
    needs_vision: bool = Field(default=False, description="是否需要看图")
    matched_keyword: str = Field(default="", description="匹配到的关键词")
    reason: str = Field(default="", description="判断理由")


class CelebrityScreenerResult(BaseModel):
    """追星线 Screener 返回结果"""
    generated_title: str = Field(default="", description="标准化标题")
    celebrity_name: str = Field(default="", description="明星/偶像名称")
    event_type: str = Field(default="", description="事件类型: release/event/discussion/controversy/endorsement")
    sentiment: str = Field(default="neutral", description="情感: positive/negative/neutral")
    heat_score: int = Field(default=1, description="热度评分 1-10")
    is_relevant: bool = Field(default=False, description="是否相关")
    needs_vision: bool = Field(default=False, description="是否需要看图")
    matched_keyword: str = Field(default="", description="匹配到的关键词")
    reason: str = Field(default="", description="判断理由")


class BriefingScreenerResult(BaseModel):
    """简报线 Screener 返回结果"""
    generated_title: str = Field(default="", description="标准化标题")
    info_type: str = Field(default="", description="信息类型: tech/entertainment/travel/finance/other")
    domain: str = Field(default="", description="领域标签")
    sentiment: str = Field(default="neutral", description="情感: positive/negative/neutral")
    abstract: str = Field(default="", description="20字摘要")
    is_relevant: bool = Field(default=True, description="是否相关（简报线默认全收）")
    needs_vision: bool = Field(default=False, description="是否需要看图")
    matched_keyword: str = Field(default="", description="匹配到的关键词")
    reason: str = Field(default="", description="判断理由")


# ============================================================
# v2.0 P0 新增：Guide / Opinion / Itinerary 输出 Schema
# ============================================================


class WeightedOpinion(BaseModel):
    """跨平台加权观点"""
    point: str = Field(description="观点内容")
    support_count: int = Field(default=0, description="支持数")
    oppose_count: int = Field(default=0, description="反对数")
    neutral_count: int = Field(default=0, description="中立数")
    platforms: dict[str, int] = Field(default_factory=dict, description="各平台分布")
    weighted_score: float = Field(default=3.0, description="加权评分 1-5")
    recommendation: str = Field(default="中立", description="推荐/谨慎/不推荐")


class GuideSlot(BaseModel):
    """攻略信息槽位"""
    time_slot: str = Field(default="", description="上午/午餐/下午/晚上/全天")
    location: str = Field(default="", description="地点")
    action: str = Field(default="", description="参观/用餐/住宿/购物")
    description: str = Field(default="", description="详细描述")
    rating: int = Field(default=1, description="评分 1-5")
    cost_min: int = Field(default=0, description="最低花费")
    cost_max: int = Field(default=0, description="最高花费")
    platform: str = Field(default="", description="来源平台 xhs/bili/zhihu")
    author_type: str = Field(default="", description="素人/KOL/商家")
    confidence: float = Field(default=0.8, description="置信度 0-1")


class GuidePlanOutput(BaseModel):
    """完整的攻略规划输出"""
    keyword: str = Field(description="关键词")
    itinerary: list[dict] = Field(default_factory=list, description="多日行程列表")
    budget: dict = Field(default_factory=dict, description="{min, max, unit, note}")
    high_confidence: list[WeightedOpinion] = Field(default_factory=list, description="高置信观点")
    controversial: list[WeightedOpinion] = Field(default_factory=list, description="争议观点")
    tips: list[dict] = Field(default_factory=list, description="实用贴士")
    source_summary: dict[str, int] = Field(default_factory=dict, description="来源统计")


class RadarGraphState(TypedDict):
    """
    LangGraph 全局状态字典。

    贯穿 analyst → reviewer → director 整个节点数据流。
    """
    # 输入
    mock_post: dict              # 帖子/话题数据
    keyword: str                  # 监控关键字
    sensitivity: str              # 监控等级 (balanced / aggressive / conservative)
    level_instruction: str       # 动态生成的监控指令

    # 节点执行结果
    analyst_result: dict
    reviewer_result: dict
    final_report: str

    # 最终输出
    status: str                   # "safe" 或 "alert"
    risk_level: int
    reason: str
    core_issue: str

    # 中间状态（各 node 共享）
    text_to_analyze: str          # analyst_node 构造，后续节点复用

    # 话题演化追踪（RAG 增强）
    evolution_timeline: dict     # build_evolution_timeline() 的输出
