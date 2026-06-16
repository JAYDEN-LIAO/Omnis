"""
数据库测试数据注入 — 模拟真实用户场景
插入后 Agent 查询时能返回有意义的真实数据
"""
import sys, os, json, uuid, datetime

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# 直接 sqlite3 操作（绕过 ORM，保持幂等）
import sqlite3

DB_PATH = os.path.join(PROJECT_ROOT, "backend", "data", "radar_state.db")
TEST_USER_ID = "u_60753a963a3740ac"  # 当前测试用户

def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn

def ensure_tables():
    """确保所有必要表存在"""
    conn = db()
    c = conn.cursor()
    # init_radar_db 已经创建了这些表，但我们再确认
    tables = [
        "subscription", "ai_results", "topic_summary", "topic_posts",
        "push_settings", "audit_log", "model_config", "quota"
    ]
    for t in tables:
        try:
            c.execute(f"SELECT 1 FROM {t} LIMIT 1")
        except sqlite3.OperationalError:
            print(f"  ! 表 {t} 不存在，跳过")
    conn.close()

def now():
    return datetime.datetime.now()

def clear_previous():
    """清除上次测试数据（幂等）"""
    print("清除上次测试数据...")
    conn = db()
    c = conn.cursor()
    for table in ["subscription", "ai_results", "topic_summary", "topic_posts",
                   "push_settings", "audit_log", "model_config"]:
        try:
            c.execute(f"DELETE FROM {table} WHERE owner_id = ?", (TEST_USER_ID,))
        except sqlite3.OperationalError:
            pass
    conn.commit()
    conn.close()
    print("  完成")

def seed_subscriptions():
    """创建 3 个订阅：小米(品牌)、华为(品牌)、AI行业(行业)"""
    print("1. 注入订阅...")
    conn = db()
    c = conn.cursor()
    subs = [
        {
            "id": str(uuid.uuid4()),
            "owner_id": TEST_USER_ID,
            "name": "小米",
            "type": "brand",
            "platforms": json.dumps(["微博", "小红书", "B站"]),
            "polarity": "all",
            "sensitivity": "balanced",
            "frequency_min": 60,
            "push_mode": "important",
            "show_risk_alert": True,
            "is_active": 1,
            "created_at": now().isoformat(),
            "updated_at": now().isoformat(),
        },
        {
            "id": str(uuid.uuid4()),
            "owner_id": TEST_USER_ID,
            "name": "华为",
            "type": "brand",
            "platforms": json.dumps(["微博", "知乎"]),
            "polarity": "negative",
            "sensitivity": "high",
            "frequency_min": 30,
            "push_mode": "every",
            "show_risk_alert": True,
            "is_active": 1,
            "created_at": now().isoformat(),
            "updated_at": now().isoformat(),
        },
        {
            "id": str(uuid.uuid4()),
            "owner_id": TEST_USER_ID,
            "name": "AI行业动态",
            "type": "industry",
            "platforms": json.dumps(["微博", "B站", "知乎"]),
            "polarity": "all",
            "sensitivity": "balanced",
            "frequency_min": 120,
            "push_mode": "important",
            "show_risk_alert": False,
            "is_active": 1,
            "created_at": now().isoformat(),
            "updated_at": now().isoformat(),
        },
    ]
    for s in subs:
        c.execute("""
            INSERT OR REPLACE INTO subscription
            (id, owner_id, name, type, platforms, polarity, sensitivity,
             frequency_min, push_mode, show_risk_alert, is_active, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (s["id"], s["owner_id"], s["name"], s["type"], s["platforms"],
              s["polarity"], s["sensitivity"], s["frequency_min"], s["push_mode"],
              s["show_risk_alert"], s["is_active"], s["created_at"], s["updated_at"]))
    conn.commit()
    conn.close()
    print(f"  已创建 {len(subs)} 个订阅")

def seed_ai_results():
    """注入 15 条各风险等级的舆情数据（模拟真实扫描结果）"""
    print("2. 注入舆情数据（ai_results）...")
    conn = db()
    c = conn.cursor()
    posts = [
        # 高风险（4-5）
        ("小米SU7自燃事故引发关注，车主称行驶中电池起火", "小米汽车被曝在行驶过程中电池突然起火，消防已介入调查", "微博", "小米", 5, "产品质量缺陷，安全隐患严重", "2026-06-13 10:30:00", "Negative"),
        ("华为鸿蒙系统被曝严重漏洞，数百万设备面临风险", "安全研究员发现鸿蒙核心组件存在远程代码执行漏洞", "知乎", "华为", 5, "系统安全漏洞，影响范围广", "2026-06-13 09:15:00", "Negative"),
        ("小米集团被指虚假宣传：发布会数据与实际不符", "第三方机构测试发现小米宣称的性能数据与实测存在显著差异", "B站", "小米", 4, "虚假宣传风险，品牌信誉受损", "2026-06-13 08:00:00", "Negative"),
        ("AI大模型被爆训练数据包含用户隐私信息", "多家AI企业的训练数据被曝包含大量未脱敏的用户个人信息", "知乎", "AI行业动态", 4, "数据合规风险，监管关注", "2026-06-13 07:30:00", "Negative"),
        # 中风险（3）
        ("小米15系列销量低于预期，供应链砍单", "据产业链消息，小米15系列首月销量较上一代下降约20%", "微博", "小米", 3, "销量下滑，需关注后续走势", "2026-06-12 14:00:00", "Negative"),
        ("华为Pura 80供货紧张：黄牛加价3000元", "华为最新旗舰手机上市后持续缺货，黄牛市场溢价严重", "微博", "华为", 3, "供需失衡，但品牌热度高", "2026-06-12 11:00:00", "Neutral"),
        ("多家企业联合发布AI安全白皮书", "华为、小米等科技巨头联合发布AI安全白皮书，提出行业自律准则", "微博", "AI行业动态", 3, "行业正向发展，无风险信号", "2026-06-12 10:00:00", "Positive"),
        ("小米生态链新品发布：智能家居再扩容", "小米发布新款智能门锁、扫地机器人等生态链产品", "小红书", "小米", 3, "产品发布，正常商业行为", "2026-06-11 16:00:00", "Positive"),
        # 低风险（1-2）
        ("小米之家旗舰店在深圳开业", "小米全球最大旗舰店在深圳万象天地开业，吸引大量消费者", "小红书", "小米", 2, "正常商业拓展", "2026-06-11 09:00:00", "Positive"),
        ("华为开发者大会2026日程公布", "华为宣布将于7月举办年度开发者大会，将发布鸿蒙5.0", "微博", "华为", 2, "常规活动预告", "2026-06-10 15:00:00", "Positive"),
        ("小米投资AI芯片初创公司", "小米旗下产业基金完成对一家AI芯片初创公司的战略投资", "B站", "小米", 2, "战略投资，正面信号", "2026-06-10 12:00:00", "Positive"),
        ("华为云发布新AI算力服务", "华为云宣布推出新一代AI训练算力服务，性能提升3倍", "知乎", "AI行业动态", 2, "产品升级，正面", "2026-06-10 09:00:00", "Positive"),
        ("小米手环9 Pro发布", "小米手环9 Pro新增血压监测功能，售价299元起", "小红书", "小米", 1, "常规新品，无风险", "2026-06-09 14:00:00", "Positive"),
        ("华为FreeBuds 7体验评测", "华为新款降噪耳机获得媒体一致好评", "B站", "华为", 1, "正面评测", "2026-06-09 10:00:00", "Positive"),
        ("雷军出席世界人工智能大会", "雷军在WAIC 2026上分享小米AI战略", "微博", "小米", 1, "出席活动，品牌曝光", "2026-06-08 11:00:00", "Positive"),
    ]
    count = 0
    for title, content, platform, keyword, risk_level, core_issue, pub_time, sentiment in posts:
        pid = f"seed_{uuid.uuid4().hex[:12]}"
        c.execute("""
            INSERT OR REPLACE INTO ai_results
            (post_id, platform, keyword, title, content, url, risk_level, core_issue, report,
             publish_time, create_time, sentiment, owner_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (pid, platform, keyword, title, content, f"https://example.com/{pid}", risk_level,
              core_issue, f"AI分析报告：{title}", pub_time, now().isoformat(), sentiment, TEST_USER_ID))
        count += 1
    conn.commit()
    conn.close()
    print(f"  已注入 {count} 条舆情数据")

def seed_topics():
    """创建话题聚合（模拟扫描后的话题聚类结果）"""
    print("3. 注入话题数据...")
    conn = db()
    c = conn.cursor()
    topics = [
        ("topic_xiaomi_su7", "小米SU7安全事故", "小米汽车自燃事件舆情分析", 5, "critical", "产品质量与安全隐患", now().isoformat(), now().isoformat(), 3),
        ("topic_huawei_bug", "华为鸿蒙安全漏洞", "鸿蒙系统安全漏洞事件持续发酵", 5, "critical", "系统安全与数据保护", now().isoformat(), now().isoformat(), 1),
        ("topic_xiaomi_sales", "小米15销量讨论", "小米15系列销量下滑引发的市场讨论", 3, "high", "产品竞争力与市场表现", now().isoformat(), now().isoformat(), 2),
        ("topic_ai_safety", "AI安全治理", "多家企业联合推动AI安全标准化", 3, "medium", "行业规范与政策合规", now().isoformat(), now().isoformat(), 0),
    ]
    for tid, name, summary, risk_level, risk_class, issue, first, last, processed in topics:
        c.execute("""
            INSERT OR REPLACE INTO topic_summary
            (topic_id, keyword, topic_name, cluster_summary, risk_level, risk_class,
             core_issue, first_seen, last_seen, owner_id, is_processed, post_count)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (tid, "小米" if "xiao" in tid else "华为" if "hua" in tid else "AI行业动态",
              name, summary, risk_level, risk_class, issue, first, last, TEST_USER_ID,
              1 if processed else 0, 3))
        # 关联帖子
        c.execute("""
            INSERT OR REPLACE INTO topic_posts (topic_id, post_id, is_current)
            VALUES (?, ?, 1)
        """, (tid, "seed_" + tid))
    conn.commit()
    conn.close()
    print(f"  已创建 {len(topics)} 个话题")

def seed_quota():
    """设置用户配额（确保能创建订阅等操作）"""
    print("4. 配置用户配额...")
    conn = db()
    c = conn.cursor()
    c.execute("""
        INSERT OR REPLACE INTO quota (owner_id, max_subscriptions, scan_interval_min, scan_paused)
        VALUES (?, ?, ?, ?)
    """, (TEST_USER_ID, 100, 60, 0))
    conn.commit()
    conn.close()
    print("  完成")

def seed_audit_log():
    """注入审计日志（模拟近期活动）"""
    print("5. 注入审计日志...")
    conn = db()
    c = conn.cursor()
    logs = [
        ("scan_completed", "小米", f"{(now() - datetime.timedelta(hours=2)).isoformat()}", "全平台扫描完成，发现 5 条新内容"),
        ("scan_completed", "华为", f"{(now() - datetime.timedelta(hours=3)).isoformat()}", "微博/知乎扫描完成，发现 2 条新内容"),
        ("alert_sent", "小米", f"{(now() - datetime.timedelta(hours=2, minutes=30)).isoformat()}", "高危预警已推送：小米SU7安全事故"),
        ("subscription_created", "AI行业动态", f"{(now() - datetime.timedelta(hours=5)).isoformat()}", "新增行业订阅：AI行业动态"),
        ("scan_started", "全平台", f"{(now() - datetime.timedelta(hours=2, minutes=5)).isoformat()}", "定时扫描启动"),
    ]
    for action, keyword, ts, detail in logs:
        try:
            c.execute("""
                INSERT INTO audit_log (action, keyword, detail, owner_id, created_at)
                VALUES (?, ?, ?, ?, ?)
            """, (action, keyword, detail, TEST_USER_ID, ts))
        except sqlite3.OperationalError as e:
            print(f"  ! 审计日志写入失败（表结构问题？）: {e}")
    conn.commit()
    conn.close()
    print(f"  已注入 {len(logs)} 条审计记录")

def seed_push_settings():
    """配置推送通道（模拟已配置的邮箱通道）"""
    print("6. 推送通道配置...")
    conn = db()
    c = conn.cursor()
    # 先创建表（如果不存在）
    try:
        c.execute("""
            CREATE TABLE IF NOT EXISTS push_settings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_id TEXT NOT NULL,
                channel TEXT NOT NULL,
                config_json TEXT NOT NULL
            )
        """)
    except sqlite3.OperationalError:
        pass
    configs = [
        ("email", json.dumps({"enabled": True, "risk_min_level": 2,
                              "smtp_host": "smtp.qq.com", "smtp_port": 587,
                              "from_addr": "test@qq.com", "to_addrs": ["user@example.com"]})),
        ("wecom", json.dumps({"enabled": True, "risk_min_level": 3,
                              "webhook_url": "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=test"})),
    ]
    for channel, config in configs:
        c.execute("""
            INSERT OR REPLACE INTO push_settings (owner_id, channel, config_json)
            VALUES (?, ?, ?)
        """, (TEST_USER_ID, channel, config))
    conn.commit()
    conn.close()
    print(f"  已配置 {len(configs)} 个推送通道")

def seed_model_config():
    """配置模型覆盖（模拟用户自定义模型）"""
    print("7. 模型配置...")
    conn = db()
    c = conn.cursor()
    c.execute("""
        INSERT OR REPLACE INTO model_config (owner_id, agent_role, provider, model, api_key, base_url)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (TEST_USER_ID, "ANALYST", "deepseek", "deepseek-chat",
          "sk-mocked-key", "https://api.deepseek.com/v1"))
    conn.commit()
    conn.close()
    print("  ANALYST 角色已自定义为 deepseek-chat")

if __name__ == "__main__":
    print("=" * 60)
    print(f"  测试数据注入 - 用户 {TEST_USER_ID}")
    print(f"  数据库: {DB_PATH}")
    print("=" * 60)

    clear_previous()
    print()
    seed_subscriptions()
    seed_ai_results()
    seed_topics()
    seed_quota()
    seed_audit_log()
    seed_push_settings()
    seed_model_config()

    print("\n" + "=" * 60)
    print("  数据注入完成！")
    print("=" * 60)
    print("现在可以执行：python test_agent_all.py")
