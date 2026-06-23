"""
crawler_adapter.py — 爬虫适配器

通过线程池 + subprocess.run 运行爬虫，彻底绕过 asyncio 事件循环类型限制
（SelectorEventLoop 不支持 create_subprocess_exec）。
"""
import asyncio
import concurrent.futures
import os
import subprocess
import sys
from typing import AsyncGenerator, Optional

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend.core.logger import get_logger
from backend.core.config import settings

logger = get_logger("search.crawler_adapter")

CRAWLER_DIR = os.path.join(BASE_DIR, "backend", "services", "crawler_service")
VENV_PYTHON = os.path.join(BASE_DIR, "venv", "Scripts", "python.exe")
if not os.path.exists(VENV_PYTHON):
    VENV_PYTHON = sys.executable

PLATFORM_TABLE_MAP = {
    "wb": "weibo_note", "xhs": "xhs_note", "bilibili": "bilibili_video",
    "bili": "bilibili_video", "zhihu": "zhihu_question",
    "dy": "douyin_aweme", "ks": "kuaishou_aweme", "tieba": "tieba_post",
}


def _read_latest_posts(platform: str, query: str, max_count: int = 10) -> list[dict]:
    """从爬虫 DB 读取指定平台的最新帖子"""
    table = PLATFORM_TABLE_MAP.get(platform)
    if not table:
        logger.warning(f"[CrawlerAdapter] 不支持的平台: {platform}")
        return []

    db_path = settings.CRAWLER_DB_PATH
    if not os.path.exists(db_path):
        logger.warning(f"[CrawlerAdapter] 爬虫 DB 不存在: {db_path}")
        return []

    try:
        import sqlite3
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute(f"PRAGMA table_info({table})")
        columns_info = cursor.fetchall()
        if not columns_info:
            conn.close()
            return []
        existing_columns = {col['name'] for col in columns_info}

        def find_col(candidates):
            for c in candidates:
                if c in existing_columns:
                    return c
            return None

        id_col = find_col(['note_id', 'aweme_id', 'tweet_id', 'id', 'item_id'])
        content_col = find_col(['desc', 'content', 'text', 'detail', 'article'])
        url_col = find_col(['note_url', 'url', 'video_url', 'article_url', 'link'])
        title_col = find_col(['title', 'name'])
        image_col = find_col(['image_list', 'pic_list', 'images', 'pics', 'image_url'])

        if not id_col or not content_col:
            conn.close()
            return []

        cols = [id_col, content_col]
        if url_col: cols.append(url_col)
        if title_col: cols.append(title_col)
        if image_col: cols.append(image_col)

        cols_str = ", ".join(cols)
        cursor.execute(f"SELECT {cols_str} FROM {table} ORDER BY ROWID DESC LIMIT 50")
        rows = cursor.fetchall()
        conn.close()

        results = []
        for r in rows:
            post_id = str(r[id_col])
            content = r[content_col] or ""
            image_urls = []
            if image_col and r[image_col]:
                val = str(r[image_col])
                if val.startswith('['):
                    try: image_urls = __import__('json').loads(val)
                    except Exception: pass
                else:
                    image_urls = [u.strip() for u in val.split(',') if u.strip()]

            results.append({
                "post_id": post_id,
                "title": r[title_col] if title_col else "无标题",
                "content": content,
                "url": r[url_col] if url_col else "",
                "image_urls": image_urls,
                "platform": platform,
            })
        return results
    except Exception as e:
        logger.error(f"[CrawlerAdapter] 读取平台 {platform} 失败: {e}", exc_info=True)
        return []


async def quick_crawl_stream(
    query: str,
    platforms: Optional[list[str]] = None,
    max_per_platform: int = 5,
    cookie_str: str = "",
) -> AsyncGenerator[dict, None]:
    """跨平台快速爬虫：线程池 subprocess.run，兼容所有事件循环类型"""
    if platforms is None:
        platforms = list(PLATFORM_TABLE_MAP.keys())

    loop = asyncio.get_running_loop()

    for plat in platforms:
        table = PLATFORM_TABLE_MAP.get(plat)
        if not table:
            continue

        logger.info(f"[CrawlerAdapter] 启动爬虫: platform={plat}, query={query}" + (" (cookie)" if cookie_str else ""))
        headless = "true" if cookie_str else "false"
        cmd = [
            VENV_PYTHON, "main.py",
            "--platform", plat,
            "--type", "search",
            "--save_data_option", "sqlite",
            "--headless", headless,
            "--init_db", "sqlite",
            "--keywords", query,
        ]
        # Popen + 轮询：不阻塞事件循环，定期 yield 心跳保持 SSE 活跃
        _env = os.environ.copy()
        _env["MEDIARADAR_SKIP_CDP"] = "true"  # 用标准 Playwright 模式，不连 CDP
        if cookie_str:
            _env["WEIBO_COOKIE_STR"] = cookie_str
        proc = subprocess.Popen(cmd, cwd=CRAWLER_DIR,
                                stdout=None, stderr=None, env=_env)
        deadline = loop.time() + 300
        heartbeat_interval = 5
        db_poll_interval = 3
        last_heartbeat = loop.time()
        last_db_poll = loop.time()
        seen_ids: set = set()
        enough = False
        try:
            while proc.poll() is None:
                await asyncio.sleep(1)
                if loop.time() - last_heartbeat >= heartbeat_interval:
                    yield {"type": "heartbeat", "platform": plat, "elapsed": int(loop.time() - (deadline - 300))}
                    last_heartbeat = loop.time()
                if loop.time() - last_db_poll >= db_poll_interval:
                    new_posts = _read_latest_posts(plat, query, max_count=max_per_platform)
                    for post in new_posts:
                        if post["post_id"] not in seen_ids:
                            seen_ids.add(post["post_id"])
                            yield {"type": "item", "item": post}
                            if len(seen_ids) >= max_per_platform:
                                enough = True
                                break
                    last_db_poll = loop.time()
                if enough or loop.time() > deadline:
                    if enough:
                        proc.kill()
                        logger.info(f"[CrawlerAdapter] {plat} 已收够 {len(seen_ids)} 条，终止爬虫")
                    else:
                        proc.kill()
                        logger.warning(f"[CrawlerAdapter] {plat} 爬虫超时")
                    break
            if proc.returncode == 0 or proc.poll() is not None:
                logger.info(f"[CrawlerAdapter] {plat} 爬虫完成, returncode={proc.returncode}")
        except Exception as e:
            proc.kill()
            logger.error(f"[CrawlerAdapter] {plat} 爬虫异常 [{type(e).__name__}]: {e!r}", exc_info=True)
            continue
        finally:
            try: proc.wait(timeout=1)
            except Exception: proc.kill()

        if proc.returncode is None or proc.returncode != 0:
            logger.warning(f"[CrawlerAdapter] {plat} 爬虫异常退出, returncode={proc.returncode}")
            continue

        posts = _read_latest_posts(plat, query, max_count=max_per_platform)
        remaining = [p for p in posts if p["post_id"] not in seen_ids]
        yield {"type": "progress", "platform": plat, "scanned": len(posts)}
        for post in remaining:
            yield {"type": "item", "item": post}

    logger.info("[CrawlerAdapter] 全平台搜索完成")
