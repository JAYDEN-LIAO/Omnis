"""
WS4: 用户与认证相关表（users / user_settings / token_blacklist）

幂等建表，存于 STATE_DB_PATH（与 ai_results 等业务表同库）。
"""
import sqlite3
import uuid
from datetime import datetime
from typing import Optional, Dict, Any, List

from backend.core.database import get_db_connection
from backend.core.logger import get_logger
from passlib.hash import bcrypt

logger = get_logger("auth.db")


def _hash_password(password: str) -> str:
    return bcrypt.hash(password)


def _verify_password(password: str, hash_str: str) -> bool:
    try:
        return bcrypt.verify(password, hash_str)
    except Exception:
        return False


def _migrate_add_password_column():
    """幂等添加 password_hash 列（SQLite 不支持 IF NOT EXISTS）"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute("ALTER TABLE users ADD COLUMN password_hash TEXT")
            logger.info("[AuthDB] 迁移: 添加 password_hash 列")
        except sqlite3.OperationalError:
            pass  # 列已存在
        conn.commit()


def _generate_user_id() -> str:
    return f"u_{uuid.uuid4().hex[:16]}"


def _migrate_add_system_access_column():
    """幂等添加 has_system_access 列（新用户注册后默认无系统 Key 权限）"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute("ALTER TABLE users ADD COLUMN has_system_access INTEGER DEFAULT 0")
            logger.info("[AuthDB] 迁移: 添加 has_system_access 列")
        except sqlite3.OperationalError:
            pass
        conn.commit()


def _migrate_existing_users_access():
    """迁移：为所有已有用户开放系统 Key 权限（存量用户默认信任）"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET has_system_access = 1 WHERE has_system_access IS NULL OR has_system_access = 0")
        affected = cursor.rowcount
        conn.commit()
    if affected:
        logger.info(f"[AuthDB] 迁移: {affected} 个存量用户已获得系统 Key 权限")


def init_auth_tables():
    """WS4：幂等建表（含索引）"""
    with get_db_connection() as conn:
        cursor = conn.cursor()

        # 用户表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                email TEXT UNIQUE,
                nickname TEXT NOT NULL,
                avatar_url TEXT,
                role TEXT DEFAULT 'user',
                oauth_provider TEXT,
                oauth_id TEXT,
                is_active INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_login_at TIMESTAMP,
                tokens_invalid_after TIMESTAMP,
                UNIQUE(oauth_provider, oauth_id)
            )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_users_oauth ON users(oauth_provider, oauth_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_users_role ON users(role)')
        # L2 v2.2: 兼容老库（无 tokens_invalid_after 列）
        cursor.execute("PRAGMA table_info(users)")
        cols = {row[1] for row in cursor.fetchall()}
        if "tokens_invalid_after" not in cols:
            cursor.execute("ALTER TABLE users ADD COLUMN tokens_invalid_after TIMESTAMP")

        # 用户设置
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_settings (
                user_id TEXT PRIMARY KEY,
                settings_json TEXT NOT NULL DEFAULT '{}',
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # token 黑名单（24h TTL）
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS token_blacklist (
                token_hash TEXT PRIMARY KEY,
                expires_at TIMESTAMP NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_token_blacklist_expires ON token_blacklist(expires_at)')

        # 邀请码表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS invite_codes (
                code TEXT PRIMARY KEY,
                max_uses INTEGER DEFAULT 0,
                current_uses INTEGER DEFAULT 0,
                is_active INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                created_by TEXT
            )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_invite_codes_active ON invite_codes(is_active)')

        # 邀请码兑换记录表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS invite_redemptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                code TEXT NOT NULL,
                redeemed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_redemptions_user ON invite_redemptions(user_id)')

        conn.commit()
    _migrate_add_password_column()
    _migrate_add_system_access_column()
    _migrate_existing_users_access()
    _seed_invite_codes()
    logger.info("[AuthDB] 所有认证相关表已就绪")


# ==================== users CRUD ====================

def get_user_by_id(user_id: str) -> Optional[Dict[str, Any]]:
    with get_db_connection() as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        row = cursor.fetchone()
        if row:
            d = dict(row)
            d.pop("password_hash", None)  # v2.2 安全：不暴露 hash
            return d
        return None


def get_user_by_oauth(provider: str, oauth_id: str) -> Optional[Dict[str, Any]]:
    with get_db_connection() as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM users WHERE oauth_provider = ? AND oauth_id = ?",
            (provider, oauth_id),
        )
        row = cursor.fetchone()
        return dict(row) if row else None


def get_user_by_email(email: str) -> Optional[Dict[str, Any]]:
    with get_db_connection() as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE email = ?", (email,))
        row = cursor.fetchone()
        return dict(row) if row else None


def create_user(
    email: Optional[str],
    nickname: str,
    avatar_url: Optional[str] = None,
    oauth_provider: Optional[str] = None,
    oauth_id: Optional[str] = None,
    role: str = "user",
) -> Dict[str, Any]:
    """创建用户。已存在时（同 oauth_provider+oauth_id）返回现有用户。"""
    if oauth_provider and oauth_id:
        existing = get_user_by_oauth(oauth_provider, oauth_id)
        if existing:
            return existing

    user_id = _generate_user_id()
    now = datetime.now().isoformat()
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO users
            (id, email, nickname, avatar_url, role, oauth_provider, oauth_id, is_active, created_at, last_login_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
        ''', (user_id, email, nickname, avatar_url, role, oauth_provider, oauth_id, now, now))
        conn.commit()
    logger.info(f"[AuthDB] 创建用户: id={user_id} email={email} provider={oauth_provider}")
    return get_user_by_id(user_id)  # type: ignore


def create_local_user(email: str, password: str, nickname: str) -> Optional[Dict[str, Any]]:
    """创建邮箱密码用户。邮箱已存在时返回 None。"""
    if get_user_by_email(email):
        return None
    user_id = _generate_user_id()
    now = datetime.now().isoformat()
    pw_hash = _hash_password(password)
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO users
            (id, email, nickname, role, password_hash, is_active, created_at, last_login_at)
            VALUES (?, ?, ?, 'user', ?, 1, ?, ?)
        ''', (user_id, email, nickname, pw_hash, now, now))
        conn.commit()
    logger.info(f"[AuthDB] 创建本地用户: id={user_id} email={email}")
    return get_user_by_id(user_id)


def authenticate_local(email: str, password: str) -> Optional[Dict[str, Any]]:
    """验证邮箱密码，成功返回用户 dict，失败返回 None。"""
    user = get_user_by_email(email)
    if not user:
        return None
    pw_hash = user.get("password_hash") or ""
    if not pw_hash or not _verify_password(password, pw_hash):
        return None
    if not user.get("is_active", 1):
        return None
    return user


def change_password(user_id: str, old_password: str, new_password: str) -> bool:
    """L3 v2.2: 修改密码。需验证旧密码，成功后写入新 hash。

    返回:
        True  - 修改成功
        False - 旧密码错误 / 用户无密码（OAuth-only）/ 用户不存在
    """
    if not new_password or len(new_password) < 8:
        raise ValueError("密码至少 8 位")
    user = get_user_by_id(user_id)
    if not user:
        return False
    pw_hash = user.get("password_hash") or ""
    # OAuth-only 用户无本地密码，必须先设置一个再修改
    if not pw_hash:
        logger.warning(f"[AuthDB] change_password: 用户 {user_id[:8]}... 无本地密码")
        return False
    if not _verify_password(old_password, pw_hash):
        return False
    new_hash = _hash_password(new_password)
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET password_hash = ? WHERE id = ?", (new_hash, user_id))
        conn.commit()
    logger.info(f"[AuthDB] 用户 {user_id[:8]}... 修改密码成功")
    return True


def set_password_for_oauth_user(user_id: str, new_password: str) -> bool:
    """L3 v2.2: OAuth 用户首次设置本地密码（无旧密码校验）。"""
    if not new_password or len(new_password) < 8:
        raise ValueError("密码至少 8 位")
    user = get_user_by_id(user_id)
    if not user:
        return False
    if user.get("password_hash"):
        # 已有密码的用户应走 change_password
        return False
    new_hash = _hash_password(new_password)
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET password_hash = ? WHERE id = ?", (new_hash, user_id))
        conn.commit()
    return True


def update_last_login(user_id: str):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE users SET last_login_at = ? WHERE id = ?",
            (datetime.now().isoformat(), user_id),
        )
        conn.commit()


def list_users(page: int = 1, page_size: int = 20, keyword: str = "") -> Dict[str, Any]:
    """管理后台用：分页 + 关键词搜索（email/nickname）"""
    offset = (page - 1) * page_size
    with get_db_connection() as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        if keyword:
            cursor.execute('''
                SELECT * FROM users
                WHERE email LIKE ? OR nickname LIKE ?
                ORDER BY created_at DESC LIMIT ? OFFSET ?
            ''', (f"%{keyword}%", f"%{keyword}%", page_size, offset))
        else:
            cursor.execute('''
                SELECT * FROM users ORDER BY created_at DESC LIMIT ? OFFSET ?
            ''', (page_size, offset))
        items = [dict(row) for row in cursor.fetchall()]
        for item in items:
            item.pop("password_hash", None)  # v2.2 安全

        if keyword:
            cursor.execute(
                "SELECT COUNT(*) FROM users WHERE email LIKE ? OR nickname LIKE ?",
                (f"%{keyword}%", f"%{keyword}%"),
            )
        else:
            cursor.execute("SELECT COUNT(*) FROM users")
        total = cursor.fetchone()[0]

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "has_next": offset + len(items) < total,
    }


def update_user_role(user_id: str, role: str) -> bool:
    if role not in ("user", "admin"):
        return False
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET role = ? WHERE id = ?", (role, user_id))
        conn.commit()
        return cursor.rowcount > 0


def update_user_profile(user_id: str, nickname: str) -> bool:
    """更新用户昵称等基本信息。"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET nickname = ? WHERE id = ?", (nickname, user_id))
        conn.commit()
        return cursor.rowcount > 0


def deactivate_user(user_id: str) -> bool:
    """L2 v2.2: 同时设置 tokens_invalid_after = NOW，使该用户所有未过期 token 立即失效"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE users SET is_active = 0, tokens_invalid_after = ? WHERE id = ?",
            (datetime.now().isoformat(timespec="seconds"), user_id),
        )
        conn.commit()
        return cursor.rowcount > 0


def get_tokens_invalid_after(user_id: str) -> Optional[str]:
    """L2 v2.2: 读取用户的 token 撤销时间戳。返回 ISO 字符串或 None。"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT tokens_invalid_after FROM users WHERE id = ?", (user_id,))
        row = cursor.fetchone()
        if not row:
            return None
        val = row[0]
        return val if isinstance(val, str) else None


def reactivate_user(user_id: str) -> bool:
    """L2 v2.2: 重新激活用户时清空 tokens_invalid_after（避免误踢后续新签发的 token）"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE users SET is_active = 1, tokens_invalid_after = NULL WHERE id = ?",
            (user_id,),
        )
        conn.commit()
        return cursor.rowcount > 0


# ==================== user_settings ====================

def get_user_settings(user_id: str) -> Dict[str, Any]:
    import json
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT settings_json FROM user_settings WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        if not row:
            return {}
        try:
            return json.loads(row[0])
        except (json.JSONDecodeError, TypeError):
            return {}


def save_user_settings(user_id: str, settings: Dict[str, Any]):
    import json
    payload = json.dumps(settings, ensure_ascii=False)
    now = datetime.now().isoformat()
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO user_settings (user_id, settings_json, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                settings_json = excluded.settings_json,
                updated_at = excluded.updated_at
        ''', (user_id, payload, now))
        conn.commit()


# ==================== token_blacklist ====================

def add_to_blacklist(token_hash: str, expires_at_iso: str):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR IGNORE INTO token_blacklist (token_hash, expires_at) VALUES (?, ?)
        ''', (token_hash, expires_at_iso))
        conn.commit()


def is_blacklisted(token_hash: str) -> bool:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM token_blacklist WHERE token_hash = ?", (token_hash,))
        return cursor.fetchone() is not None


def cleanup_expired_blacklist() -> int:
    """删除过期黑名单条目（24h 后自动清）"""
    now = datetime.now().isoformat()
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM token_blacklist WHERE expires_at < ?", (now,))
        deleted = cursor.rowcount
        conn.commit()
    return deleted


# ==================== 邀请码系统 ====================

INVITE_CODE_PRESET = "KSKBL1027"


def _seed_invite_codes():
    """初始化预设邀请码（幂等）"""
    now = datetime.now().isoformat()
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR IGNORE INTO invite_codes (code, max_uses, current_uses, is_active, created_at, created_by)
            VALUES (?, 0, 0, 1, ?, 'system')
        ''', (INVITE_CODE_PRESET, now))
        conn.commit()


def get_user_system_access(user_id: str) -> bool:
    """查询用户是否有系统 Key 权限"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT has_system_access FROM users WHERE id = ?", (user_id,))
        row = cursor.fetchone()
        if row is None:
            return False
        return bool(row[0])


def set_user_system_access(user_id: str, has_access: bool) -> bool:
    """设置用户的系统 Key 权限"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE users SET has_system_access = ? WHERE id = ?",
            (1 if has_access else 0, user_id),
        )
        conn.commit()
        return cursor.rowcount > 0


def redeem_invite_code(code: str, user_id: str) -> tuple[bool, str]:
    """兑换邀请码。

    Returns:
        (成功?, 消息)
    """
    code = code.strip().upper()
    with get_db_connection() as conn:
        cursor = conn.cursor()

        # 检查邀请码是否存在且有效
        cursor.execute(
            "SELECT max_uses, current_uses, is_active FROM invite_codes WHERE code = ?",
            (code,),
        )
        row = cursor.fetchone()
        if not row:
            return False, "邀请码不存在"
        max_uses, current_uses, is_active = row
        if not is_active:
            return False, "邀请码已停用"
        if max_uses > 0 and current_uses >= max_uses:
            return False, "邀请码已被用完"

        # 检查该用户是否已兑换过
        cursor.execute(
            "SELECT 1 FROM invite_redemptions WHERE user_id = ? AND code = ?",
            (user_id, code),
        )
        if cursor.fetchone():
            return False, "该邀请码已被你使用过"

        # 检查用户是否已有系统权限
        cursor.execute("SELECT has_system_access FROM users WHERE id = ?", (user_id,))
        user_row = cursor.fetchone()
        if user_row and user_row[0]:
            return False, "你已拥有系统 Key 权限，无需重复兑换"

        # 增加使用次数
        cursor.execute(
            "UPDATE invite_codes SET current_uses = current_uses + 1 WHERE code = ?",
            (code,),
        )
        # 记录兑换
        cursor.execute(
            "INSERT INTO invite_redemptions (user_id, code) VALUES (?, ?)",
            (user_id, code),
        )
        # 开通权限
        cursor.execute(
            "UPDATE users SET has_system_access = 1 WHERE id = ?",
            (user_id,),
        )
        conn.commit()

    logger.info(f"[AuthDB] 邀请码兑换成功: user={user_id[:8]}... code={code}")
    return True, "邀请码兑换成功，已开通系统 Key 权限"
