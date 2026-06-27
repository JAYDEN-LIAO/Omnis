/**
 * Generate Omnis SA Word Report (docx)
 * ~15+ pages, A4, Arial, 12pt body
 */
const fs = require("fs");
const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  Header, Footer, AlignmentType, LevelFormat,
  HeadingLevel, BorderStyle, WidthType, ShadingType,
  PageNumber, PageBreak
} = require("docx");

// Color scheme matching PPT
const C = {
  purple: "79257A",
  gold: "FFB300",
  lightPurple: "D1C4E9",
  dark: "333333",
};

// ===== Helpers =====
const border = { style: BorderStyle.SINGLE, size: 1, color: "CCCCCC" };
const borders = { top: border, bottom: border, left: border, right: border };

function cell(text, opts = {}) {
  const runs = [];
  if (opts.bold) {
    runs.push(new TextRun({ text, bold: true, font: "Arial", size: opts.size || 22 }));
  } else {
    runs.push(new TextRun({ text, font: "Arial", size: opts.size || 22 }));
  }
  return new TableCell({
    borders,
    width: { size: opts.w || 2000, type: WidthType.DXA },
    shading: opts.shade ? { fill: opts.shade, type: ShadingType.CLEAR } : undefined,
    margins: { top: 60, bottom: 60, left: 100, right: 100 },
    children: [new Paragraph({ children: runs, alignment: opts.align || AlignmentType.LEFT })],
  });
}

function p(text, opts = {}) {
  const runs = [];
  if (typeof text === "string") {
    runs.push(new TextRun({ text, font: "Arial", size: opts.size || 24, ...opts }));
  } else if (Array.isArray(text)) {
    text.forEach(t => {
      if (typeof t === "string") runs.push(new TextRun({ text: t, font: "Arial", size: opts.size || 24 }));
      else runs.push(new TextRun({ font: "Arial", size: 24, ...t }));
    });
  }
  return new Paragraph({
    children: runs,
    spacing: { before: opts.before || 120, after: opts.after || 120 },
    alignment: opts.align,
    pageBreakBefore: opts.pageBreak,
    numbering: opts.numbering,
    indent: opts.indent,
  });
}

function h1(text) { return new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun({ text, font: "Arial", size: 32, bold: true, color: C.purple })], spacing: { before: 360, after: 240 } }); }
function h2(text) { return new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun({ text, font: "Arial", size: 28, bold: true, color: C.purple })], spacing: { before: 280, after: 200 } }); }
function h3(text) { return new Paragraph({ heading: HeadingLevel.HEADING_3, children: [new TextRun({ text, font: "Arial", size: 24, bold: true, color: C.dark })], spacing: { before: 200, after: 160 } }); }

function spacer() { return new Paragraph({ spacing: { before: 200, after: 200 }, children: [] }); }

// ===== Numbering config =====
const numbering = {
  config: [
    { reference: "bullets", levels: [{ level: 0, format: LevelFormat.BULLET, text: "\u2022", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 720, hanging: 360 } } } }] },
    { reference: "bullets2", levels: [{ level: 0, format: LevelFormat.BULLET, text: "\u2022", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 720, hanging: 360 } } } }] },
    { reference: "numbers1", levels: [{ level: 0, format: LevelFormat.DECIMAL, text: "%1.", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 720, hanging: 360 } } } }] },
  ],
};

function bullet(text, ref = "bullets") {
  return new Paragraph({
    numbering: { reference: ref, level: 0 },
    spacing: { before: 60, after: 60 },
    children: [new TextRun({ text, font: "Arial", size: 24 })],
  });
}

// ===== Document Content =====

// --- Cover ---
const cover = [
  spacer(), spacer(), spacer(),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 2000 }, children: [
    new TextRun({ text: "软件体系结构课程报告", font: "Arial", size: 44, bold: true, color: C.purple }),
  ]}),
  spacer(),
  new Paragraph({ alignment: AlignmentType.CENTER, children: [
    new TextRun({ text: "Omnis \u2014 智能媒体信息监控平台", font: "Arial", size: 32, color: C.dark }),
  ]}),
  spacer(), spacer(),
  new Paragraph({ alignment: AlignmentType.CENTER, children: [
    new TextRun({ text: "软件体系结构分析与设计", font: "Arial", size: 28, color: C.purple }),
  ]}),
  spacer(), spacer(), spacer(), spacer(), spacer(),
  new Paragraph({ alignment: AlignmentType.CENTER, children: [
    new TextRun({ text: "南京理工大学  计算机科学与工程学院", font: "Arial", size: 24 }),
  ]}),
  new Paragraph({ alignment: AlignmentType.CENTER, children: [
    new TextRun({ text: "2025\u20132026 学年", font: "Arial", size: 24 }),
  ]}),
  new Paragraph({ children: [new PageBreak()] }),
];

// --- Chapter 1: 引言 ---
const ch1 = [
  h1("一、引言"),
  h2("1.1 项目背景"),
  p("互联网时代，社交媒体已成为信息传播的核心载体。微博、抖音、小红书、知乎、B站等平台每天产生海量内容，涵盖公众讨论、产品评测、行业动态、消费决策等各个维度。如何从这些分散的跨平台信息中高效获取所需情报，是个人用户和企业面临的共同挑战。"),
  p("与此同时，大语言模型（LLM）技术的快速发展，尤其是 DeepSeek、GPT 等模型的广泛应用，为智能信息处理开辟了全新可能。AI 不仅能够理解自然语言，还能进行情感分析、趋势预测、观点对比、结构化信息提取等复杂任务。将 AI Agent 与媒体信息采集相结合，可以实现从\"人工监控\"到\"智能代理\"的范式转变。"),
  p("Omnis 正是在此背景下诞生的跨平台媒体信息数据采集与分析智能体平台。其核心理念是 \"where Agents meet Media Intelligence\" \u2014\u2014 让 AI Agent 成为用户的智能信息管家，用户只需用自然语言表达需求，系统自动完成跨平台的数据采集、智能分析和报告生成。"),

  h2("1.2 Omnis 平台定位"),
  p("Omnis（名称源自拉丁语 omnis，意为\"全知\"）定位为跨平台媒体信息数据采集与分析智能体平台，而非传统的舆情监控系统。系统可处理多种类型的媒体信息分析任务："),
  bullet("舆情风险扫描：监测品牌相关的负面舆论，自动判定风险等级并推送预警"),
  bullet("攻略规划聚合：从多平台采集旅游、出行等攻略信息，结构化对比并生成行程计划"),
  bullet("实体追踪：追踪明星、KOL、品牌等实体的跨平台热度和情感变化趋势"),
  bullet("跨平台对比：对比同一话题在不同平台的叙事差异和情感分布"),
  bullet("工作流自动化：用户可创建自定义定时工作流，系统自动按计划执行数据采集和分析"),
  p("系统的核心设计理念是：让 AI 成为用户的智能管家，用户只需用自然语言表达需求，系统自动完成后续的分析和决策工作。"),

  h2("1.3 技术架构概览"),
  p("系统采用双前端架构：主推形态为 Next.js 15 Web 端（面向 PC 用户），同时保留 uni-app 小程序端（面向移动用户）。后端采用 FastAPI 统一网关，SQLite + Qdrant 双数据库方案兼顾关系存储和向量检索。AI 引擎基于 LangGraph 框架，通过四种独立的 LangGraph 子图（风险分析图、攻略聚合图、热度追踪图、综合简报图）覆盖不同业务场景。"),

  h2("1.4 报告结构"),
  p("本报告从软件体系结构的角度对 Omnis 系统进行全面分析。第二章介绍系统概述与技术栈，第三章阐释系统总体架构，第四章分析系统的体系结构风格，第五章使用4+1视图模型描述系统架构，第六章对系统进行质量评估，第七章总结全文并展望改进方向。"),
  new Paragraph({ children: [new PageBreak()] }),
];

// --- Chapter 2: 系统概述 ---
const ch2 = [
  h1("二、系统概述"),
  h2("2.1 系统定位"),
  p("Omnis 定位为跨平台媒体信息数据采集与分析智能体平台，slogan 为 \"where Agents meet Media Intelligence\"。系统不是传统的舆情监控工具，而是一个由 AI Agent 驱动、可处理多种类型媒体信息任务的智能平台。其核心价值包括："),
  bullet("多平台信息采集：覆盖微博、抖音、小红书、知乎、B站等主流平台"),
  bullet("AI 智能分析引擎：基于 DeepSeek + Kimi 双模型交叉验证，支持风险分析、攻略聚合、热度追踪、综合简报四种管线"),
  bullet("Multi-Agent 交互：AI管家式对话，用户通过自然语言即可完成复杂信息分析任务"),
  bullet("多通道推送：企业微信、飞书、邮箱、RSS 等多渠道，支持按需配置"),
  bullet("工作流自动化：预设组合工具 + 自动累积 + 用户自定义，三种工作流来源统一管理"),

  h2("2.2 核心功能"),
  p("系统围绕\"AI Agent + 媒体信息智能\"的核心理念，设计了以下核心功能模块："),

  // Table
  new Table({
    width: { size: 9026, type: WidthType.DXA },
    columnWidths: [2500, 6526],
    rows: [
      new TableRow({ children: [cell("功能模块", { bold: true, shade: C.lightPurple, w: 2500 }), cell("说明", { bold: true, shade: C.lightPurple, w: 6526 })] }),
      new TableRow({ children: [cell("舆情风险扫描"), cell("监测品牌相关的负面舆论，自动判定风险等级并推送预警（仅为核心功能之一）")] }),
      new TableRow({ children: [cell("攻略规划聚合"), cell("从多平台采集旅游、出行等攻略信息，结构化对比并生成可执行行程计划")] }),
      new TableRow({ children: [cell("实体热度追踪"), cell("追踪明星、KOL、品牌等实体在各大平台的提及量和情感变化趋势")] }),
      new TableRow({ children: [cell("综合简报生成"), cell("按主题汇总多平台信息，生成结构化的每日/定时综合简报")] }),
      new TableRow({ children: [cell("跨平台对比"), cell("对比同一话题在不同平台的叙事差异、情感分布和声量分布")] }),
      new TableRow({ children: [cell("Agent 对话交互"), cell("AI管家式交互，12+ 原子工具 + 组合工具流，支持用户自定义工作流")] }),
      new TableRow({ children: [cell("工作流自动化"), cell("预设组合工具 + 自动累积 + 用户自定义，三种来源统一管理，支持 cron 调度")] }),
    ],
  }),
  spacer(),

  h2("2.3 技术栈"),
  new Table({
    width: { size: 9026, type: WidthType.DXA },
    columnWidths: [2500, 3000, 3526],
    rows: [
      new TableRow({ children: [cell("层次", { bold: true, shade: C.lightPurple, w: 2500 }), cell("技术", { bold: true, shade: C.lightPurple, w: 3000 }), cell("用途", { bold: true, shade: C.lightPurple, w: 3526 })] }),
      new TableRow({ children: [cell("后端框架"), cell("FastAPI (Python)"), cell("RESTful API 网关")] }),
      new TableRow({ children: [cell("数据库"), cell("SQLite / Qdrant"), cell("关系存储 / 向量检索")] }),
      new TableRow({ children: [cell("AI 引擎"), cell("LangGraph / LangChain"), cell("多 Agent 协作编排")] }),
      new TableRow({ children: [cell("LLM"), cell("DeepSeek + Kimi + Qwen-VL"), cell("分析/复核/视觉")] }),
      new TableRow({ children: [cell("Web前端"), cell("Next.js 15 + shadcn/ui"), cell("用户界面")] }),
      new TableRow({ children: [cell("部署"), cell("Docker Compose"), cell("容器化编排")] }),
    ],
  }),
  spacer(),
  p("此外，系统采用 Prometheus 进行指标采集，AgentOpsEngine 进行 LLM 运维健康巡检。爬虫模块支持 Playwright/Selenium 两种驱动模式。AI 引擎使用 BGE-M3 模型进行文本向量化，HDBSCAN 算法进行话题聚类，实现从原始数据到结构化情报的完整转化。"),
  new Paragraph({ children: [new PageBreak()] }),
];

// --- Chapter 3: 总体架构 ---
const ch3 = [
  h1("三、系统总体架构"),
  h2("3.1 Agent-Centric 架构"),
  p("Omnis 的核心架构设计采用 Agent-Centric 模式。与传统的分层架构不同，系统的所有能力都通过 AI Agent 对话接口暴露给用户。系统架构从底向上分为六个层次："),

  new Table({
    width: { size: 9026, type: WidthType.DXA },
    columnWidths: [2000, 7026],
    rows: [
      new TableRow({ children: [cell("层次", { bold: true, shade: C.lightPurple, w: 2000 }), cell("说明", { bold: true, shade: C.lightPurple, w: 7026 })] }),
      new TableRow({ children: [cell("用户交互层"), cell("Next.js 15  Web 端 + uni-app 小程序，提供多端一致的用户体验")] }),
      new TableRow({ children: [cell("API 网关层"), cell("FastAPI 统一网关，负责认证鉴权、限流保护、请求路由")] }),
      new TableRow({ children: [cell("Agent 核心层"), cell("Agent Core 主循环 + Phase Plan 四维规划引擎 + Tool Executor")] }),
      new TableRow({ children: [cell("工具执行层"), cell("12+ 原子工具 (H组) + 组合工具 (I组)，通过适配器执行")] }),
      new TableRow({ children: [cell("分析引擎层"), cell("ScreenerStage / ClusterStage / LangGraph 子图 / Vision 视觉分析")] }),
      new TableRow({ children: [cell("数据存储层"), cell("SQLite 持久化 + Qdrant 向量检索 + Redis 缓存")] }),
    ],
  }),
  spacer(),

  h2("3.2 原子工具与组合工具流"),
  p("系统将数据分析流程拆解为 12+ 个精细化原子工具，每个工具使用 @tool 装饰器注册，支持独立执行和任意组合。原子工具包括 search_posts（跨平台搜索）、filter_content（按意图过滤）、cluster_related（话题聚类）、analyze_sentiment（情感判定）、compare_opinions（观点对比）等。"),
  p("组合工具（I组）通过 execute_workflow_steps 统一执行器将多个原子工具编排为完整的工作流。系统预置了四个组合工具：deep_analyze_topic（深度话题分析，覆盖舆情风险、实体追踪等场景）、scan_and_alert（扫描预警）、quick_guide（攻略查询规划）、briefing_digest（综合简报生成）。"),

  h2("3.3 工作流三源合一"),
  p("系统支持三种来源的工作流，统一存储在 workflows 表中："),

  new Table({
    width: { size: 9026, type: WidthType.DXA },
    columnWidths: [2000, 7026],
    rows: [
      new TableRow({ children: [cell("来源", { bold: true, shade: C.lightPurple, w: 2000 }), cell("说明", { bold: true, shade: C.lightPurple, w: 7026 })] }),
      new TableRow({ children: [cell("预设 Preset"), cell("系统预置的 4 个组合工具，不可删除可停用")] }),
      new TableRow({ children: [cell("自动累积 Auto Template"), cell("Agent 自主完成任务后自动保存执行步骤，下次命中直接复用")] }),
      new TableRow({ children: [cell("用户自建 User"), cell("用户通过自然语言创建，支持 cron 定时调度")] }),
    ],
  }),
  new Paragraph({ children: [new PageBreak()] }),
];

// --- Chapter 4: 体系结构风格 ---
// ===== Style selection matrix data (for display) =====
const styleMatrixRows = (headers, ...rows) => {
  const hRow = new TableRow({ children: headers.map(h => cell(h, { bold: true, shade: C.lightPurple, w: 1500 })) });
  const dRows = rows.map(r => new TableRow({ children: r.map((c, i) => cell(c, { w: headers[i] ? 1500 : 1500 })) }));
  return [hRow, ...dRows];
};

ch4_extras = [
  h2("4.8 体系结构风格选择分析"),
  p("参照课程第13章介绍的体系选择矩阵法，从组件重用、组件更换、组件无关性、计算性能等维度对 Omnis 中涉及的体系结构风格进行评分分析："),
  new Table({
    width: { size: 9026, type: WidthType.DXA },
    columnWidths: [1800, 1400, 1400, 1400, 1400, 1400],
    rows: [
      new TableRow({ children: ["质量维度", "分层", "管道-过滤器", "黑板/仓库", "面向Agent", "事件驱动"].map(h => cell(h, { bold: true, shade: C.lightPurple, w: h === "质量维度" ? 1800 : 1400 })) }),
      ...[
        ["组件重用", "3", "5", "5", "5", "5"],
        ["组件更换", "5", "5", "5", "5", "5"],
        ["组件无关性", "1", "5", "3", "1", "5"],
        ["计算性能", "4", "5", "5", "4", "5"],
        ["接口变换", "4", "2", "1", "1", "1"],
      ].map(r => new TableRow({ children: r.map((c, i) => cell(c, { w: i === 0 ? 1800 : 1400, align: i === 0 ? AlignmentType.LEFT : AlignmentType.CENTER })) })),
    ],
  }),
  spacer(),
  p("从上表可以看出，管道-过滤器和事件驱动风格在组件重用和无关性方面表现突出，适合频繁增减分析工具的场景；分层风格在组件更换和接口变换方面优势明显，适合系统长期演进的架构需求。Omnis 选择异构融合正是为了在不同质量维度之间取得平衡。"),

  h2("4.9 设计模式在架构中的应用"),
  p("除体系结构风格外，Omnis 在实现层面应用了多种设计模式："),
  bullet("适配器模式 (Adapter)：DirectAdapter 和 MCPAdapter 实现统一的 AbstractToolAdapter 接口，支持本地函数调用和远程 MCP Server 调用两种方式"),
  bullet("装饰器模式 (Decorator)：@tool 装饰器自动将函数注册到工具注册表，@with_owner 强制注入 owner_id，实现了关注分离"),
  bullet("注册表模式 (Registry)：_REGISTRY 全局字典驱动 Function Calling Schema 的生成，支持运行时的工具发现和调用"),
  bullet("模板方法模式 (Template Method)：execute_workflow_steps 定义了工具链执行的通用骨架，各步骤通过参数注入实现差异化的行为"),
  bullet("工厂模式 (Factory)：Pipeline 配置通过工厂注册表创建不同模式的管线实例（risk/guide/celebrity/briefing）"),
];

const ch4 = [
  h1("四、软件体系结构风格分析"),
  p("Omnis 融合了多种体系结构风格，形成异构体系结构。每种风格在系统不同层面发挥作用，共同支撑系统的各项质量属性。"),

  h2("4.1 分层架构风格 (Layered)"),
  p("分层风格贯穿系统全局，将系统按抽象层次纵向划分为六个层次：表现层、网关层、服务层、工具层、引擎层、数据层。每层职责明确，上层依赖下层接口，遵循关注分离（Separation of Concerns）原则。修改一层最多影响相邻层，接口稳固时支持层实现替换。"),
  p("这种风格对应于课程第8章所述的层次化风格。在 Omnis 中，分层架构为系统提供了高可维护性和可重用性，新的服务可以在不破坏现有结构的情况下加入。"),

  h2("4.2 管道-过滤器风格 (Pipe-Filter)"),
  p("原子工具链构成了典型的管道-过滤器风格。数据在工具之间流动：search_posts -> filter_content -> cluster_related -> extract_slots -> compare_opinions。每个过滤器是独立的计算单元，对输入流进行处理和转换，处理结果在输出端流出。"),
  p("这种风格对应于课程第4章所述的数据流风格中的管道-过滤器。在 Omnis 中，组合工具（如 deep_analyze_topic）本质上是一个多步管道的动态注册，execute_workflow_steps 充当管道编排器。系统整体可以视为增量式递进处理的数据流系统，上一个过滤器的输出作为下一个的输入。"),

  h2("4.3 黑板与仓库风格 (Repository/Blackboard)"),
  p("SQLite 和 Qdrant 向量库作为中央数据仓库，各 Agent 和工具独立读写共享数据。这种风格对应于课程第5章所述的仓库与黑板风格。SQLite 持久化话题、报告、工作流和用户配置，Qdrant 支撑语义检索与话题演化追踪。"),
  p("各组件独立性强，新增和替换方便，便于模块间的数据共享。这种风格特别适用于 Omnis 的多 Agent 协作场景，其中多个知识源（各分析工具）需要共享和操作同一个数据集。"),

  h2("4.4 面向 Agent 风格 (Agent-Oriented)"),
  p("LangGraph 多 Agent 协作是系统的核心智能层。Agent Core 实现 Plan-Act 循环：感知（接收用户输入）-> 规划（模板匹配/LLM 生成计划）-> 执行（调用工具）-> 反馈（结果检测，异常时动态调整）。这种风格对应于课程第11章所述的面向 Agent 风格。"),
  p("系统中的关键 Agent 包括：Agent Core（主控制器，协调工具调用，管理 Token 预算与取消事件）、Plan Agent（规划器，Jaccard 模板匹配 + LLM 规划）、Tool Executor（执行器，支持流式进度推送与超时取消）、Memory Manager（记忆管理器，对话摘要/实体提取）、Cancel Registry（取消注册表，Session 级 asyncio.Event 支持跨协程取消）。"),

  h2("4.5 事件驱动风格 (Event-Driven)"),
  p("系统的流式交互基于事件驱动风格。SSE（Server-Sent Events）实现 AI 助手对话的逐块推送，asyncio 异步事件循环支撑高并发工具执行，Cancel 事件机制实现用户随时中断正在执行的工具链。这种风格在流式对话和异步并发场景中发挥关键作用，保证了系统的响应速度和用户体验。"),

  h2("4.6 Agent 风格的关键特征"),
  p("Omnis 的 Agent 架构与课程第11章中介绍的面向 Agent 风格高度吻合。Agent 组件具有三个关键特征：自主性（可自主决策工具调用序列）、智能性（LLM 驱动的规划与推理）、交互性（通过 SSE 与用户实时交互）。不同 Agent 之间的连接根据运行时状态动态决定，而非显式固定连接。"),

  h2("4.7 异构风格融合分析"),
  p("在实际系统中，以上五种风格并非独立存在，而是有机融合。分层风格定义了系统的总体骨架，管道-过滤器风格组织了数据分析流程，黑板风格管理了数据共享，面向 Agent 风格提供了智能决策能力，事件驱动风格支撑了实时交互。这种异构融合使得系统能够同时满足多种质量需求。"),
  p("如课程第13章所述，绝大多数实际运行的系统都是几种体系结构的复合。在系统的某些部分采用一种体系结构，在其他部分采用另外的体系结构，形成复合体系结构，这是大型软件系统的普遍特征。"),
  new Paragraph({ children: [new PageBreak()] }),
];

// --- Chapter 5: 4+1 视图 ---
const ch5 = [
  h1("五、4+1 视图模型分析"),
  p("根据 Philippe Kruchten 在 1995 年提出的 4+1 视图模型，本节从逻辑视图、过程视图、开发视图、物理视图和场景视图五个角度对 Omnis 进行描述。"),

  h2("5.1 逻辑视图 (Logical View)"),
  p("逻辑视图主要支持功能需求，关注系统向用户提供的服务。采用面向对象的方法，核心类包括："),
  bullet("AgentContext：统一状态对象，封装 session_id、owner_id、messages、plan、iteration 等属性，提供 build_context()、get_last_user_message() 等方法"),
  bullet("Tool：通过 @tool 装饰器注册的工具定义，包含 name、description、parameters、func 等关键属性"),
  bullet("ToolResult：工具统一返回结构，包含 success、data、error、ui 等字段"),
  bullet("ToolExecutor：统一工具执行器，通过 DirectAdapter 或 MCPAdapter 执行工具"),
  bullet("WorkflowsDB：统一工作流 CRUD，支持 preset/auto_template/user 三种来源"),
  bullet("PipelineStage：抽象分析引擎基类，ScreenerStage 和 ClusterStage 为其具体实现"),
  bullet("TokenBudgetManager：Token 预算管理器，防止 LLM 上下文溢出"),
  bullet("CancelRegistry：取消注册表，支持 Session 级跨协程取消"),

  p("这些类之间的关系如下：ToolExecutor 使用 AbstractToolAdapter 接口（依赖关系），DirectAdapter 和 MCPAdapter 实现该接口（继承关系），AgentContext 编排 ToolExecutor（关联关系），ScreenerStage 和 ClusterStage 继承自 PipelineStage（泛化关系）。"),

  h2("5.2 过程视图 (Process View)"),
  p("过程视图关注系统的并发、同步和性能问题。Omnis 的并发架构基于 Python asyncio："),
  bullet("asyncio 事件循环支撑 Agent Core、工具执行、LLM 调用等所有并发操作"),
  bullet("SSE 流式响应：chat_with_agent_stream() 通过 SSE 逐步推送文本、工具调用和工具结果，支持逐块渲染"),
  bullet("Cancel 机制：CancelRegistry 维护每个 session 的 asyncio.Event，支持跨协程取消"),
  bullet("Token 预算管理：TokenBudgetManager 实时计算 tokens，超限时自动压缩历史对话为 LLM 摘要"),
  bullet("工具重试与降级：execute_workflow_steps 支持 critical/required/optional 三级，失败自动重试或跳过"),

  h2("5.3 开发视图 (Development View)"),
  p("开发视图关注软件模块的实际组织。系统采用分层结构组织代码："),
  p("backend/ 目录下包含 gateway/（FastAPI 入口与路由）、core/（config/database/auth 等核心组件）、services/（agent_service/  Agent 核心引擎、radar_service/ 分析管线、crawler_service/ 爬虫、search_lib/ 搜索库）等子模块。"),
  p("frontend/ 包含 web/（Next.js 15 应用，采用 App Router 架构，含 dashboard/agent/yq-list/settings 等路由）和 MiniApp/（uni-app 小程序，旧版保留形态）。"),

  h2("5.4 物理视图 (Physical View)"),
  p("物理视图关注软件到硬件的映射。系统采用 Docker 容器化部署：Nginx 反向代理接收客户端请求，分发到 FastAPI 应用服务器和 Next.js Web 服务。FastAPI 服务器连接 SQLite 持久化存储、Qdrant 向量数据库和 Redis 缓存。Prometheus 负责指标采集，AgentOpsEngine 进行运维巡检。"),

  h2("5.5 场景视图 (Scenario View)"),
  p("场景视图将四个视图串联，验证体系结构设计的正确性。以下选取三个典型场景分别覆盖系统的攻略规划、实体追踪和工作流自动化能力："),

  h3("场景一：攻略规划"),
  p("用户输入\"帮我规划一下南京三日游\"后，Agent 接收请求，Phase Plan 匹配 quick_guide 模板，生成执行计划。系统先查询缓存中是否存在已有报告，若无则启动跨平台采集。依次执行 search_posts（从小红书、马蜂窝等多平台采集攻略）、filter_content（guide 意图过滤，提取攻略相关内容）、cluster_related（按景点和路线聚类）、extract_slots（提取时间/地点/花费等结构化槽位）、compare_opinions（跨平台加权对比观点）、generate_itinerary（生成可执行行程计划）。"),
  p("该场景展示了 Omnis 在攻略规划这一非舆情场景下的完整能力，验证了系统的通用媒体信息分析架构。"),

  h3("场景二：实体热度追踪"),
  p("用户输入\"最近周杰伦的动态怎么样\"后，Phase Plan 匹配追踪任务模板，执行 search_posts（跨平台搜索相关内容）、filter_content（celebrity 意图过滤，提取追星相关内容）、analyze_sentiment（分析正负面情感分布）、compare_platforms（对比各平台讨论热度和情感差异）等步骤。返回跨平台的情感趋势分析报告。"),

  h3("场景三：创建定时工作流"),
  p("用户输入\"每天早9点搜华为动态推我邮箱\"后，Phase Plan 的 LLM 规划生成 mode=scheduled 的执行计划，提取 cron 表达式并通过 croniter 校验合法性。计划持久化到 workflows 表（source=user），绑定 APScheduler 定时调度器。每天 9:00 系统自动执行搜索和推送流程。"),
  p("该场景验证了系统的定时调度能力和工作流持久化机制，展示了用户自定义工作流的完整生命周期。"),
  new Paragraph({ children: [new PageBreak()] }),
];

// --- Chapter 6: 质量评估 ---
const ch6 = [
  h1("六、软件体系结构质量评估"),
  p("软件体系结构的质量分为内部质量（软件体系结构自身质量）和外部质量（基于该体系结构的最终软件产品质量），二者相辅相成。"),

  h2("6.1 内部质量分析"),
  new Table({
    width: { size: 9026, type: WidthType.DXA },
    columnWidths: [1800, 7226],
    rows: [
      new TableRow({ children: [cell("指标", { bold: true, shade: C.lightPurple, w: 1800 }), cell("评价", { bold: true, shade: C.lightPurple, w: 7226 })] }),
      new TableRow({ children: [cell("可维护性"), cell("分层架构 + @tool 装饰器注册，新增工具无需修改已有代码，WorkflowsDB CRUD 统一管理工作流")] }),
      new TableRow({ children: [cell("可重用性"), cell("12+ 原子工具可任意组合，适配器模式 (Direct/MCP) 支持多种后端，ToolResult 统一返回格式")] }),
      new TableRow({ children: [cell("可移植性"), cell("Docker 容器化 + 环境变量配置 (Settings 三层回退策略)，平台无关键依赖")] }),
      new TableRow({ children: [cell("可集成性"), cell("AbstractToolAdapter 标准接口，MCPAdapter 支持 HTTP 远程工具，@tool 注册表统一管理")] }),
      new TableRow({ children: [cell("可测试性"), cell("Pipeline Stages 独立可测，工具函数输入输出清晰，@with_owner 注入解耦")] }),
    ],
  }),
  spacer(),

  h2("6.2 外部质量分析"),
  new Table({
    width: { size: 9026, type: WidthType.DXA },
    columnWidths: [1800, 7226],
    rows: [
      new TableRow({ children: [cell("指标", { bold: true, shade: C.lightPurple, w: 1800 }), cell("评价", { bold: true, shade: C.lightPurple, w: 7226 })] }),
      new TableRow({ children: [cell("性能"), cell("Python asyncio 全异步架构，Semaphore 爬虫限流，SSE 流式减少首字节延迟")] }),
      new TableRow({ children: [cell("可用性"), cell("Circuit Breaker 防止 LLM 雪崩，Direct->MCP 自动降级，三级容错")] }),
      new TableRow({ children: [cell("可靠性"), cell("execute_workflow_steps 内置重试机制，critical 步骤失败终止，optional 跳过")] }),
      new TableRow({ children: [cell("安全性"), cell("JWT + API Key 双认证，OAuth (Google/微信)，rate_limiter 限流")] }),
      new TableRow({ children: [cell("易用性"), cell("自然语言交互 Agent 化，四维规划自动匹配模板，无需技术背景")] }),
    ],
  }),
  spacer(),

  h2("6.3 质量场景评估"),
  p("基于场景的评估方法，通过三个典型场景对系统质量进行验证："),
  h3("场景一：高并发搜索（性能）"),
  p("100 用户同时发起搜索请求。系统通过 asyncio 并发 + Semaphore 10 限流控制爬虫并发数，搜索库 3 分钟超时兜底，保证系统在 3 秒内返回结果。"),

  h3("场景二：爬虫宕机（可用性/可靠性）"),
  p("微博平台爬虫服务无响应。系统通过 asyncio.wait_for timeout 180 秒检测超时，触发 _read_cached_posts 缓存兜底，跳过故障平台返回其他平台数据，单平台故障不影响整体。"),

  h3("场景三：新增工具（可修改性）"),
  p("需求新增功能。通过 @tool 装饰器 + @with_owner 自动注入 owner_id，系统自动注册到 TOOLS_SCHEMA，无需修改核心代码。"),

  h2("6.4 质量评估总结"),
  p("综合以上分析，Omnis 在内部质量和外部质量方面表现均衡："),

  new Table({
    width: { size: 9026, type: WidthType.DXA },
    columnWidths: [3000, 3000, 3026],
    rows: [
      new TableRow({ children: ["评价维度", "评分（满分10分）", "关键优势"].map(h => cell(h, { bold: true, shade: C.lightPurple, w: h === "关键优势" ? 3026 : 3000 })) }),
      ...[
        ["可维护性", "8", "分层架构，@tool 注册机制"],
        ["可重用性", "9", "原子工具自由组合，适配器模式"],
        ["可移植性", "7", "Docker 容器化，环境配置"],
        ["可集成性", "8", "标准适配器接口，MCP 协议"],
        ["可测试性", "7", "Pipeline 独立可测"],
        ["性能", "8", "asyncio 全异步并发"],
        ["可用性", "8", "熔断器+降级+健康检查"],
        ["可靠性", "7", "三级重试机制"],
        ["安全性", "8", "JWT+API Key+OAuth"],
        ["易用性", "9", "自然语言交互，智能规划"],
      ].map(r => new TableRow({ children: r.map((c, i) => cell(c, { w: i === 0 ? 3000 : i === 1 ? 3000 : 3026, align: i === 1 ? AlignmentType.CENTER : AlignmentType.LEFT })) })),
    ],
  }),
  new Paragraph({ children: [new PageBreak()] }),
];

// --- Chapter 7: 总结 ---
const ch7 = [
  h1("七、总结与展望"),
  h2("7.1 核心优势"),
  bullet("Agent-Centric 架构：以 AI 对话为核心，所有功能通过自然语言暴露，用户无需技术背景即可操作"),
  bullet("多任务能力：不局限于舆情监控，覆盖攻略规划、实体追踪、跨平台对比、工作流自动化等多种媒体信息分析场景"),
  bullet("异构风格融合：分层 + 管道-过滤器 + 黑板 + 面向 Agent + 事件驱动五种风格有机组合"),
  bullet("三种工作流合一：preset / auto_template / user 统一存储在 workflows 表，支持动态注册"),
  bullet("高质量工程实践：asyncio 并发 + 熔断器 + 重试/降级 + Prometheus 监控，保障系统稳定性"),

  h2("7.2 不足与改进方向"),
  bullet("单库 SQLite 在高并发下的写入瓶颈，可迁移至 PostgreSQL 集群"),
  bullet("测试覆盖度不足，需引入集成测试套件 + Mock 爬虫框架"),
  bullet("MCP 适配器处于早期阶段，需完善协议标准与更多第三方工具集成"),
  bullet("Qdrant 单节点向量查询性能受限，可配置分片集群"),

  h2("7.3 课程总结"),
  p("通过本课程的学习和 Omnis 系统的体系结构分析实践，深入理解了软件体系结构的基本概念、核心风格、4+1 视图模型和质量评估方法。在分析过程中，我们运用了课程中学习的多种知识："),
  bullet("第4章数据流风格：分析系统的管道-过滤器架构，理解数据驱动计算的特点"),
  bullet("第5章仓库与黑板风格：分析系统的共享数据架构，理解多 Agent 协作文档模式"),
  bullet("第6章事件驱动风格：分析系统的 SSE 流式交互和异步事件循环"),
  bullet("第8章层次风格：分析系统的六层分层架构和组织方式"),
  bullet("第11章面向 Agent 风格：分析系统的 Multi-Agent 协作和智能规划机制"),
  bullet("第12章4+1模型：从五个视图全面描述系统架构"),
  bullet("第13章体系结构选择：使用体系选择矩阵法对 Omnis 的多种风格进行综合评价"),
  spacer(),
  p("Omnis 融合了多种体系结构风格，体现了\"绝大多数实际运行的系统都是几种体系结构的复合\"（课程第13章）这一核心理念。每种风格在系统不同层面发挥作用，共同支撑起一个功能完善、易于扩展的智能媒体信息监控平台。"),

  h2("7.4 参考文献"),
  p("[1] Philippe Kruchten. Architectural Blueprints \u2014 The \"4+1\" View Model of Software Architecture. IEEE Software 12 (6), 1995."),
  p("[2] Mary Shaw, David Garlan. Software Architecture: Perspectives on an Emerging Discipline. Prentice Hall, 1996."),
  p("[3] Bass, Clements, Kazman. Software Architecture in Practice (3rd Edition). Addison-Wesley, 2012."),
  p("[4] 赵庆玲, 李晅松. 软件体系结构课程讲义. 南京理工大学, 2025."),
  p("[5] LangGraph Documentation. https://langchain-ai.github.io/langgraph/"),
  p("[6] FastAPI Documentation. https://fastapi.tiangolo.com/"),
  p("[7] Next.js Documentation. https://nextjs.org/docs"),
];

// ===== Build Document =====
const doc = new Document({
  styles: {
    default: { document: { run: { font: "Arial", size: 24 } } },
    paragraphStyles: [
      { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 32, bold: true, font: "Arial", color: C.purple },
        paragraph: { spacing: { before: 360, after: 240 }, outlineLevel: 0 } },
      { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 28, bold: true, font: "Arial", color: C.purple },
        paragraph: { spacing: { before: 280, after: 200 }, outlineLevel: 1 } },
      { id: "Heading3", name: "Heading 3", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 24, bold: true, font: "Arial", color: C.dark },
        paragraph: { spacing: { before: 200, after: 160 }, outlineLevel: 2 } },
    ],
  },
  numbering,
  sections: [{
    properties: {
      page: {
        size: { width: 11906, height: 16838 },
        margin: { top: 1440, right: 1440, bottom: 1440, left: 1440 },
      },
    },
    headers: {
      default: new Header({
        children: [new Paragraph({
          alignment: AlignmentType.RIGHT,
          children: [new TextRun({ text: "Omnis \u2014 智能媒体信息监控平台  软件体系结构课程报告", font: "Arial", size: 18, color: "999999" })],
        })],
      }),
    },
    footers: {
      default: new Footer({
        children: [new Paragraph({
          alignment: AlignmentType.CENTER,
          children: [new TextRun({ text: "- ", font: "Arial", size: 18 }), new TextRun({ children: [PageNumber.CURRENT], font: "Arial", size: 18 }), new TextRun({ text: " -", font: "Arial", size: 18 })],
        })],
      }),
    },
    children: [
      ...cover,
      ...ch1,
      ...ch2,
      ...ch3,
      ...ch4,
      ...ch4_extras,
      ...ch5,
      ...ch6,
      ...ch7,
    ],
  }],
});

const outPath = "D:\\JAYDEN\\develop\\work\\MediaRadar\\软件体系结构\\大作业\\Omnis_SA_Report.docx";
Packer.toBuffer(doc).then(buf => {
  fs.writeFileSync(outPath, buf);
  console.log(`OK => ${outPath}`);
  console.log(`Size: ${(buf.length / 1024).toFixed(0)} KB`);
}).catch(e => { console.error(e); process.exit(1); });
