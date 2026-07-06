# backend/services/platform_service/main.py
import asyncio
from dataclasses import dataclass, field
from typing import Optional

from backend.core.logger import get_logger
from backend.core.config import settings

logger = get_logger("radar.main")


@dataclass
class RadarStatus:
    """线程安全的雷达状态（兼容同步/异步读写）"""
    is_running: bool = False
    status_text: str = "系统闲置中"
    last_run_time: str = "暂无"
    last_new_count: int = 0
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def set_running(self, text: str):
        async with self._lock:
            self.is_running = True
            self.status_text = text
            self.last_new_count = 0

    async def set_idle(self, text: str = "系统闲置中"):
        async with self._lock:
            self.is_running = False
            self.status_text = text

    async def is_busy(self) -> bool:
        async with self._lock:
            return self.is_running

    # 同步写入方法（供 tools.py 这类同步模块使用）
    def set_running_sync(self, text: str):
        self.is_running = True
        self.status_text = text
        self.last_new_count = 0

    def set_idle_sync(self, text: str = "系统闲置中"):
        self.is_running = False
        self.status_text = text

    def set_result_sync(self, new_count: int, run_time: str):
        self.last_new_count = new_count
        self.last_run_time = run_time

    def get_status_dict(self) -> dict:
        """返回当前状态的 dict 快照（同步读取）"""
        return {
            "is_running": self.is_running,
            "status_text": self.status_text,
            "last_run_time": self.last_run_time,
            "last_new_count": self.last_new_count,
        }


# 全局实例（backward compat，owner_id=None）
radar_status = RadarStatus()

# v2.2 per-user radar status
_user_radar_statuses: dict[str, RadarStatus] = {}

def get_radar_status(owner_id: Optional[str] = None) -> RadarStatus:
    """返回指定用户的雷达状态，owner_id=None 返回全局实例（backward compat）"""
    if owner_id is None:
        return radar_status
    if owner_id not in _user_radar_statuses:
        _user_radar_statuses[owner_id] = RadarStatus()
    return _user_radar_statuses[owner_id]

def api_start_task(background_tasks, owner_id: Optional[str] = None):
    """手动触发扫描（已迁移到 Agent 驱动的复合工作流，此处仅记录日志）"""
    logger.info(f"[Scheduler] 手动触发扫描请求已收到（owner_id={owner_id}），建议使用 Agent 工作流替代")
    return True, "请使用信息助手或工作台中的预设工作流发起任务"