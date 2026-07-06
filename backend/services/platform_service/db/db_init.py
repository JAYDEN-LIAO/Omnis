# backend/services/platform_service/db/db_init.py
"""数据库 Schema 初始化"""
import sqlite3

from backend.core.database import get_db_connection
from backend.core.logger import get_logger

logger = get_logger("radar.db")


def init_radar_db():
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('PRAGMA journal_mode=WAL;')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS processed_posts (
                post_id TEXT PRIMARY KEY,
                platform TEXT,
                process_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS ai_results (
                post_id TEXT PRIMARY KEY,
                platform TEXT,
                keyword TEXT,
                title TEXT,
                content TEXT,
                url TEXT,
                risk_level TEXT,
                core_issue TEXT,
                report TEXT,
                publish_time TEXT,
                create_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS system_settings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_id TEXT NOT NULL DEFAULT 'admin',
                config_json TEXT
            )
        ''')
        # 迁移：旧表有 CHECK(id=1) 约束，需重建
        try:
            cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='system_settings'")
            row = cursor.fetchone()
            if row and 'CHECK' in (row[0] or '').upper():
                logger.info("[DB] system_settings 旧版 CHECK 约束，迁移中...")
                try:
                    cursor.execute("ALTER TABLE system_settings ADD COLUMN owner_id TEXT")
                except sqlite3.OperationalError:
                    pass
                cursor.execute("""
                    CREATE TABLE system_settings_new (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        owner_id TEXT NOT NULL DEFAULT 'admin',
                        config_json TEXT
                    )
                """)
                cursor.execute("""
                    INSERT INTO system_settings_new (owner_id, config_json)
                    SELECT COALESCE(owner_id, 'admin'), config_json FROM system_settings
                """)
                cursor.execute("DROP TABLE system_settings")
                cursor.execute("ALTER TABLE system_settings_new RENAME TO system_settings")
                logger.info("[DB] system_settings 迁移完成")
        except Exception as e:
            logger.warning(f"[DB] system_settings 迁移跳过: {e}")
        # 幂等补 owner_id（新表已有则跳过）
        try:
            cursor.execute("ALTER TABLE system_settings ADD COLUMN owner_id TEXT")
        except sqlite3.OperationalError:
            pass

        # v2.2 Fix 5.7: 高频查询列索引
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_ai_results_create_time ON ai_results(create_time DESC)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_ai_results_risk_level ON ai_results(risk_level)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_ai_results_keyword ON ai_results(keyword)')

        # ── 话题聚合表（任务1）───────────────────────────────
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS topic_summary (
                topic_id TEXT PRIMARY KEY,
                keyword TEXT NOT NULL,
                topic_name TEXT NOT NULL,
                cluster_summary TEXT,
                risk_level INTEGER DEFAULT 2,
                risk_class TEXT DEFAULT 'neutral',
                alert_recommendation TEXT DEFAULT 'none',
                core_issue TEXT,
                report TEXT,
                first_seen TEXT,
                last_seen TEXT,
                post_count INTEGER DEFAULT 0,
                platforms TEXT DEFAULT '[]',
                sentiment TEXT DEFAULT 'neutral',
                scan_count INTEGER DEFAULT 1,
                is_processed INTEGER DEFAULT 0,
                create_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS topic_posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                topic_id TEXT NOT NULL,
                post_id TEXT NOT NULL,
                is_current INTEGER DEFAULT 0,
                add_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(topic_id, post_id)
            )
        ''')
        # ──────────────────────────────────────────────────────

        try:
            cursor.execute("ALTER TABLE ai_results ADD COLUMN publish_time TEXT")
        except sqlite3.OperationalError:
            pass

        try:
            cursor.execute("ALTER TABLE ai_results ADD COLUMN topic_id TEXT")
        except sqlite3.OperationalError:
            pass

        try:
            cursor.execute("ALTER TABLE ai_results ADD COLUMN sentiment TEXT DEFAULT 'Neutral'")
        except sqlite3.OperationalError:
            pass

        try:
            cursor.execute("ALTER TABLE ai_results ADD COLUMN email_html TEXT")
        except sqlite3.OperationalError:
            pass

        # 话题表新增字段（存量数据库迁移）
        try:
            cursor.execute("ALTER TABLE topic_summary ADD COLUMN alert_recommendation TEXT DEFAULT 'none'")
        except sqlite3.OperationalError:
            pass

        # 7.1：审计日志表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                action TEXT NOT NULL,
                keyword TEXT,
                topic_id TEXT,
                risk_level INTEGER DEFAULT 0,
                detail TEXT,
                level TEXT DEFAULT 'INFO',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_audit_log_created_at ON audit_log(created_at DESC)')

        # v2.2: audit_log 加 owner_id 列（幂等迁移，旧记录为空串=系统级事件）
        try:
            cursor.execute("ALTER TABLE audit_log ADD COLUMN owner_id TEXT DEFAULT ''")
        except sqlite3.OperationalError:
            pass
        cursor.execute(
            'CREATE INDEX IF NOT EXISTS idx_audit_log_owner ON audit_log(owner_id)'
        )

        # ── WS4.6：数据隔离 owner_id 迁移（幂等）────────────────────
        # 旧数据 owner_id = NULL（公共/历史数据，所有用户可见）
        for alter_sql in [
            "ALTER TABLE ai_results ADD COLUMN owner_id TEXT",
            "ALTER TABLE topic_summary ADD COLUMN owner_id TEXT",
        ]:
            try:
                cursor.execute(alter_sql)
            except sqlite3.OperationalError:
                pass
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_ai_results_owner_id ON ai_results(owner_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_topic_summary_owner_id ON topic_summary(owner_id)')
        # ────────────────────────────────────────────────────────────

        # ── system_settings 迁移：从 id=1 单行 → per-user owner_id ────
        try:
            cursor.execute("ALTER TABLE system_settings ADD COLUMN owner_id TEXT")
        except sqlite3.OperationalError:
            pass
        # 已有数据迁移到 admin（全局保留一份默认配置）
        cursor.execute("UPDATE system_settings SET owner_id = 'admin' WHERE owner_id IS NULL")
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_system_settings_owner ON system_settings(owner_id)')
        # ────────────────────────────────────────────────────────────

        # ── v2.2：订阅表（per-owner，替代 system_settings.keywords）───
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS subscription (
                id TEXT PRIMARY KEY,
                owner_id TEXT NOT NULL,
                name TEXT NOT NULL,
                type TEXT NOT NULL DEFAULT 'keyword',
                polarity TEXT DEFAULT 'all',
                sensitivity TEXT DEFAULT 'balanced',
                frequency_min INTEGER DEFAULT 60,
                platforms TEXT DEFAULT '[]',
                push_mode TEXT DEFAULT 'important',
                show_risk_alert INTEGER DEFAULT 0,
                is_active INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_subscription_owner ON subscription(owner_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_subscription_active ON subscription(is_active)')

        # ── v2.2：订阅-话题多对多关联表 ─────────────────────────
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS subscription_topic (
                subscription_id TEXT NOT NULL,
                topic_id TEXT NOT NULL,
                first_subscribed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (subscription_id, topic_id)
            )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_sub_topic_sub ON subscription_topic(subscription_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_sub_topic_topic ON subscription_topic(topic_id)')

        # ── v2.2：多 Pipeline 迁移（幂等）────────────────────────
        try:
            cursor.execute("ALTER TABLE subscription ADD COLUMN pipeline_types TEXT DEFAULT '[\"risk\"]'")
        except sqlite3.OperationalError:
            pass

        # ── 攻略线结果表 ──
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS guide_reports (
                id TEXT PRIMARY KEY,
                keyword TEXT NOT NULL,
                topic TEXT NOT NULL,
                summary TEXT,
                consensus TEXT DEFAULT '[]',
                controversial TEXT DEFAULT '[]',
                tips TEXT DEFAULT '[]',
                source_breakdown TEXT DEFAULT '{}',
                post_count INTEGER DEFAULT 0,
                owner_id TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_guide_reports_keyword ON guide_reports(keyword)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_guide_reports_owner ON guide_reports(owner_id)')

        # ── 追星线结果表 ──
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS celebrity_reports (
                id TEXT PRIMARY KEY,
                keyword TEXT NOT NULL,
                celebrity TEXT NOT NULL,
                total_posts INTEGER DEFAULT 0,
                sentiment_distribution TEXT DEFAULT '{}',
                heat_trend TEXT DEFAULT 'stable',
                hot_topics TEXT DEFAULT '[]',
                cross_platform TEXT DEFAULT '{}',
                owner_id TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_celebrity_reports_keyword ON celebrity_reports(keyword)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_celebrity_reports_owner ON celebrity_reports(owner_id)')

        # ── 综合简报结果表 ──
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS daily_briefings (
                id TEXT PRIMARY KEY,
                keyword TEXT NOT NULL,
                date TEXT NOT NULL,
                domain TEXT,
                highlight TEXT,
                post_count INTEGER DEFAULT 0,
                sentiment TEXT DEFAULT 'neutral',
                owner_id TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_daily_briefings_keyword ON daily_briefings(keyword)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_daily_briefings_date ON daily_briefings(date)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_daily_briefings_owner ON daily_briefings(owner_id)')
        # ────────────────────────────────────────────────────────
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS model_config (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_id TEXT NOT NULL,
                agent_role TEXT NOT NULL,
                provider TEXT,
                model TEXT,
                api_key TEXT,
                base_url TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(owner_id, agent_role)
            )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_model_config_owner ON model_config(owner_id)')

        # ── v2.2：配额表（per-user，含 v2.2 per-user 扫描配置）────
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS quota (
                owner_id TEXT PRIMARY KEY,
                max_subscriptions INTEGER DEFAULT 20,
                history_retention_days INTEGER DEFAULT 30,
                max_chat_per_month INTEGER DEFAULT 200,
                used_chat_this_month INTEGER DEFAULT 0,
                month_reset_at TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                scan_interval_min REAL DEFAULT 60,
                scan_start_time TEXT DEFAULT '08:00',
                scan_paused INTEGER DEFAULT 0
            )
        ''')
        # ────────────────────────────────────────────────────────────
