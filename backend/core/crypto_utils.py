"""
core/crypto_utils.py
API Key 加密/解密工具（v2.3）

使用 Fernet (AES-128-CBC + HMAC-SHA256) 对模型配置中的 api_key 进行透明加密。

密钥来源：
  - 优先：环境变量 DB_ENCRYPTION_KEY（base64 编码的 32 字节密钥）
  - 兜底：从 JWT_SECRET 推导（保证同一部署环境下可解密）

设计原则：
  - 加密/解密失败不抛异常，返回 None 或空字符串（不阻塞登录/查询）
  - 现有明文 key 自动兼容：解密失败时按明文返回
  - 自动延迟初始化：不干扰启动流程
"""
import base64
import hashlib
import os
from typing import Optional

from backend.core.logger import get_logger

logger = get_logger("core.crypto")

# ── 缓存 Fernet 实例（延迟初始化） ──
_fernet_instance = None


def _get_fernet() -> Optional[object]:
    """获取 Fernet 实例（延迟加载，线程安全写由 GIL 保障）"""
    global _fernet_instance
    if _fernet_instance is not None:
        return _fernet_instance

    # 1. 优先从环境变量读取
    key_b64 = os.getenv("DB_ENCRYPTION_KEY", "").strip()
    if key_b64:
        try:
            # 确保 44 字符 base64（Fernet 要求）
            key_bytes = base64.urlsafe_b64decode(key_b64)
            if len(key_bytes) != 32:
                logger.warning("[Crypto] DB_ENCRYPTION_KEY 长度不是 32 字节，忽略")
                key_b64 = ""
            else:
                key_b64_clean = base64.urlsafe_b64encode(key_bytes).decode()
        except Exception:
            logger.warning("[Crypto] DB_ENCRYPTION_KEY 格式无效，忽略")
            key_b64 = ""

    # 2. 从 JWT_SECRET 推导（保证同部署可解密）
    if not key_b64:
        jwt_secret = os.getenv("JWT_SECRET", "") or ""
        if jwt_secret:
            derived = hashlib.sha256(jwt_secret.encode("utf-8")).digest()
            key_b64 = base64.urlsafe_b64encode(derived).decode()
            _env = os.getenv("ENV", "dev")
            if _env != "prod":
                logger.info("[Crypto] 从 JWT_SECRET 推导加密密钥（dev 模式）")
        else:
            # 无密钥 → 加密不可用，记录警告
            logger.warning("[Crypto] 无可用加密密钥，API Key 将以明文存储")
            return None

    try:
        from cryptography.fernet import Fernet
        _fernet_instance = Fernet(key_b64)
        return _fernet_instance
    except Exception as e:
        logger.error(f"[Crypto] Fernet 初始化失败: {e}")
        return None


def encrypt_api_key(plaintext: str) -> str:
    """加密 API Key。失败时返回原文（不阻塞写入）。"""
    if not plaintext:
        return plaintext
    f = _get_fernet()
    if f is None:
        return plaintext  # 无法加密 → 存明文（降级）
    try:
        return f.encrypt(plaintext.encode("utf-8")).decode()
    except Exception as e:
        logger.error(f"[Crypto] 加密失败: {e}")
        return plaintext


def decrypt_api_key(ciphertext: str) -> str:
    """解密 API Key。自动兼容明文（解密失败时返回原文）。"""
    if not ciphertext:
        return ciphertext
    # 检测是否已是明文（非 base64 Fernet 格式）
    # Fernet 密文格式: gAAAAAB... 以 gA 开头
    if not ciphertext.startswith("gAAAAA"):
        return ciphertext  # 明文，无需解密

    f = _get_fernet()
    if f is None:
        return ciphertext  # 无法解密 → 返回原文
    try:
        return f.decrypt(ciphertext.encode("utf-8")).decode()
    except Exception as e:
        logger.warning(f"[Crypto] 解密失败（可能是旧明文数据），返回原文: {e}")
        return ciphertext


def encrypt_dict_api_key(cfg: dict) -> dict:
    """加密配置 dict 中的 api_key 字段（用于写入前处理）。"""
    if cfg and cfg.get("api_key"):
        cfg["api_key"] = encrypt_api_key(cfg["api_key"])
    return cfg


def decrypt_dict_api_key(cfg: dict) -> dict:
    """解密配置 dict 中的 api_key 字段（用于读出后处理）。"""
    if cfg and cfg.get("api_key"):
        cfg["api_key"] = decrypt_api_key(cfg["api_key"])
    return cfg
