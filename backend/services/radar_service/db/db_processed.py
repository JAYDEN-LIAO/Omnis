# backend/services/radar_service/db/db_processed.py
"""processed_posts 表操作"""
import os
import json
import sqlite3

from backend.core.database import get_db_connection
from backend.core.logger import get_logger

logger = get_logger("radar.db")


def is_processed(post_id):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT 1 FROM processed_posts WHERE post_id = ?', (post_id,))
        result = cursor.fetchone()
    return result is not None


def mark_processed(post_id, platform):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('INSERT OR IGNORE INTO processed_posts (post_id, platform) VALUES (?, ?)', (post_id, platform))


def get_processed_status_batch(post_ids):
    if not post_ids:
        return set()

    with get_db_connection() as conn:
        cursor = conn.cursor()
        placeholders = ','.join(['?'] * len(post_ids))
        query = f"SELECT post_id FROM processed_posts WHERE post_id IN ({placeholders})"
        cursor.execute(query, tuple(post_ids))
        processed_ids = {row[0] for row in cursor.fetchall()}

    return processed_ids


def mark_processed_batch(post_info_list):
    if not post_info_list:
        return

    with get_db_connection() as conn:
        cursor = conn.cursor()
        try:
            cursor.executemany(
                'INSERT OR IGNORE INTO processed_posts (post_id, platform) VALUES (?, ?)',
                post_info_list
            )
        except sqlite3.Error as e:
            logger.error(f"Database batch insert failed: {e}")


def get_unprocessed_posts(crawler_db_path, platform):
    if not os.path.exists(crawler_db_path):
        logger.warning(f"Crawler database not found: {crawler_db_path}")
        return []

    conn = get_db_connection(db_path=crawler_db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    unprocessed_posts = []

    platform_table_map = {
        "wb": "weibo_note",
        "xhs": "xhs_note",
        "bilibili": "bilibili_video",
        "bili": "bilibili_video",
        "zhihu": "zhihu_question",
        "dy": "douyin_aweme",
        "ks": "kuaishou_aweme",
        "tieba": "tieba_post"
    }

    table_name = platform_table_map.get(platform)
    if not table_name:
        logger.warning(f"Unsupported platform type: {platform}")
        conn.close()
        return []

    try:
        cursor.execute(f"PRAGMA table_info({table_name})")
        columns_info = cursor.fetchall()

        if not columns_info:
            return []

        existing_columns = [col['name'] for col in columns_info]

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
            return []

        query_cols = [id_col, content_col]
        if url_col: query_cols.append(url_col)
        if title_col: query_cols.append(title_col)
        if image_col: query_cols.append(image_col)

        query_cols_str = ", ".join(query_cols)

        cursor.execute(f'''
            SELECT {query_cols_str}
            FROM {table_name}
            ORDER BY ROWID DESC LIMIT 200
        ''')
        rows = cursor.fetchall()

        all_post_ids = [str(row[id_col]) for row in rows]
        processed_ids_set = get_processed_status_batch(all_post_ids)

        for row in rows:
            post_id = str(row[id_col])
            if post_id not in processed_ids_set:
                image_urls = []
                if image_col and row[image_col]:
                    val = str(row[image_col])
                    if val.startswith('['):
                        try:
                            image_urls = json.loads(val)
                        except (json.JSONDecodeError, TypeError, ValueError):
                            pass
                    else:
                        image_urls = [u.strip() for u in val.split(',') if u.strip()]

                post_time = "未知时间"
                time_fields = ['time', 'create_time', 'add_ts', 'date']
                for field in time_fields:
                    if field in row.keys():
                        val = row[field]
                        if val:
                            # 处理 MediaCrawler 常见的13位或10位时间戳
                            if isinstance(val, (int, float)) or (isinstance(val, str) and str(val).isdigit()):
                                val_int = int(val)
                                if val_int > 1e11:  # 13位毫秒级时间戳
                                    val_int = val_int / 1000
                                import datetime
                                post_time = datetime.datetime.fromtimestamp(val_int).strftime('%Y-%m-%d %H:%M:%S')
                            else:
                                post_time = str(val) # 如果已经是字符串日期，直接用
                            break

                unprocessed_posts.append({
                    "post_id": post_id,
                    "title": row[title_col] if title_col else "无标题",
                    "content": row[content_col] or "无正文",
                    "publish_time": post_time,
                    "url": row[url_col] if url_col else f"未知链接 ({post_id})",
                    "image_urls": image_urls, # 塞入提取好的图片列表
                    "platform": platform
                })

    except sqlite3.OperationalError as e:
        logger.error(f"Database read exception: {e}")
    finally:
        conn.close()

    return unprocessed_posts
