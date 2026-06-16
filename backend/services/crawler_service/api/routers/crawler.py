# -*- coding: utf-8 -*-
# Copyright (c) 2025 relakkes@gmail.com
#
# This file is part of MediaCrawler project.
# Repository: https://github.com/NanmiCoder/MediaCrawler/blob/main/api/routers/crawler.py
# GitHub: https://github.com/NanmiCoder
# Licensed under NON-COMMERCIAL LEARNING LICENSE 1.1
#
# 声明：本代码仅供学习和研究目的使用。使用者应遵守以下原则：
# 1. 不得用于任何商业用途。
# 2. 使用时应遵守目标平台的使用条款和robots.txt规则。
# 3. 不得进行大规模爬取或对平台造成运营干扰。
# 4. 应合理控制请求频率，避免给目标平台带来不必要的负担。
# 5. 不得用于任何非法或不当的用途。
#
# 详细许可条款请参阅项目根目录下的LICENSE文件。
# 使用本代码即表示您同意遵守上述原则和LICENSE中的所有条款。

from fastapi import APIRouter, HTTPException

from ..schemas import CrawlerStartRequest, CrawlerStatusResponse
from ..services import crawler_manager

router = APIRouter(prefix="/crawler", tags=["crawler"])


@router.post("/start")
async def start_crawler(request: CrawlerStartRequest):
    """Start crawler task"""
    success = await crawler_manager.start(request)
    if not success:
        # Handle concurrent/duplicate requests: if process is already running, return 400 instead of 500
        if crawler_manager.process and crawler_manager.process.poll() is None:
            raise HTTPException(status_code=400, detail="Crawler is already running")
        raise HTTPException(status_code=500, detail="Failed to start crawler")

    return {"status": "ok", "message": "Crawler started successfully"}


@router.post("/stop")
async def stop_crawler():
    """Stop crawler task"""
    success = await crawler_manager.stop()
    if not success:
        # Handle concurrent/duplicate requests: if process already exited/doesn't exist, return 400 instead of 500
        if not crawler_manager.process or crawler_manager.process.poll() is not None:
            raise HTTPException(status_code=400, detail="No crawler is running")
        raise HTTPException(status_code=500, detail="Failed to stop crawler")

    return {"status": "ok", "message": "Crawler stopped successfully"}


@router.get("/status", response_model=CrawlerStatusResponse)
async def get_crawler_status():
    """Get crawler status"""
    return crawler_manager.get_status()


@router.get("/logs")
async def get_logs(limit: int = 100):
    """Get recent logs"""
    logs = crawler_manager.logs[-limit:] if limit > 0 else crawler_manager.logs
    return {"logs": [log.model_dump() for log in logs]}


@router.post("/{platform}/pause")
async def pause_crawler(platform: str):
    """暂停爬虫采集（当前页面完成后停止）"""
    ok = await crawler_manager.pause()
    return {"code": 200 if ok else 400, "msg": "已暂停" if ok else "不在运行中"}


@router.post("/{platform}/resume")
async def resume_crawler(platform: str):
    """恢复已暂停的爬虫采集"""
    ok = await crawler_manager.resume()
    return {"code": 200 if ok else 400, "msg": "已恢复" if ok else "不在暂停状态"}


@router.post("/{platform}/cancel")
async def cancel_crawler(platform: str):
    """优雅取消爬虫采集（等当前页面完成，超时 30s 后 SIGTERM）"""
    ok = await crawler_manager.cancel()
    return {"code": 200 if ok else 400, "msg": "已取消" if ok else "不在运行中"}


@router.get("/heal/status")
async def get_heal_status(platform: str = ""):
    """获取爬虫自愈状态"""
    if not hasattr(crawler_manager, '_healer'):
        return {"events": [], "platforms": {}}
    healer = crawler_manager._healer
    return {
        "events": healer.get_history(platform=platform, limit=20),
        "platforms": {
            p: healer.get_platform_health(p)
            for p in ["xhs", "dy", "ks", "bili", "wb", "tieba", "zhihu"]
        },
    }
