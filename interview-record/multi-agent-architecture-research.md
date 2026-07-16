# 主流 Multi-Agent 架构调研报告

> 目标：为从 0 到 1 搭建 multi-agent 平台提供架构选型与工程落地依据。
>
> 调研时间：2026-07 ｜ 材料来源：Anthropic / Cognition / Google / Microsoft / OpenAI 工程博客、Linux Foundation 协议规范、MAST 失败分类学论文及 2026 年多篇框架对比（见文末[参考资料](#十参考资料)）。全文结论按"通用工程判断 + 一手材料"给出，涉及数字均标注出处与时间，避免过时。

---

## 目录

1. [执行摘要（一页结论）](#一执行摘要一页结论)
2. [先决问题：到底要不要做 Multi-Agent](#二先决问题到底要不要做-multi-agent)
3. [核心架构模式（编排拓扑）](#三核心架构模式编排拓扑)
4. [框架全景（2026）与选型](#四框架全景2026与选型)
5. [通信与互操作协议栈（MCP / A2A / AGNTCY / AP2）](#五通信与互操作协议栈mcp--a2a--agntcy--ap2)
6. [平台的六个工程硬骨头](#六平台的六个工程硬骨头)
7. [失败模式与教训（MAST + 两派对照）](#七失败模式与教训mast--两派对照)
8. [平台参考架构（分层设计）](#八平台参考架构分层设计)
9. [0→1 落地路线图与选型决策](#九01-落地路线图与选型决策)
10. [参考资料](#十参考资料)

---

## 一、执行摘要（一页结论）

**一句话**：2026 年做 multi-agent 平台，正确姿势不是"上来就编排一堆 agent"，而是先把**单 agent + 上下文工程 + 工具层**做扎实，再用**编排层**在"确实需要并行、确实超出单上下文窗口、确实有清晰专业分工"的场景引入多 agent；协议层用 **MCP（对工具）+ A2A（对 agent）** 打底，可观测性与评估从第一天就建。

**五条核心结论**：

1. **架构模式已收敛**。生产环境几乎 100% 落在四种拓扑：`Supervisor（主管）` / `Orchestrator-Worker（编排器-工人）` / `Hierarchical（分层）` / `Swarm（去中心化蜂群）`，外加一个常见的 `Sequential Pipeline（顺序流水线）`。**默认从 Supervisor 起步**，agent 数超 5–8 或单协调者扛不住上下文时再升级 Hierarchical，Swarm 仅用于探索型场景。（来源：usetransactional 2026 对 350+ 论文与 120 个企业部署的统计 —— Supervisor 38%、Hierarchical 22%、Swarm 极少）

2. **框架格局在 2025→2026 大洗牌**。`LangGraph`（1.0 稳定、状态图+检查点、可控性最强）是当前"生产默认"；`CrewAI`（角色制、原型最快）；`OpenAI Agents SDK`（极简、handoff 一等公民）；`Google ADK 2.0`（多语言+企业级）；`Claude Agent SDK`（环境/文件系统/MCP 最深）。**AutoGen 已进入维护模式**，其能力并入 `Microsoft Agent Framework`（Semantic Kernel + AutoGen 合并），社区分叉为 `AG2`。

3. **协议栈已分层且由 Linux Foundation 统一治理**。`MCP` = agent↔工具/数据（垂直，事实标准，5800+ server）；`A2A` = agent↔agent（水平，v1.0，已吸收 IBM ACP）；`AGNTCY/OASF` = 发现与身份（"agent 界的 DNS"）；`AP2` = agent 间支付。**不是二选一，是分层叠加**。

4. **多 agent 不是银弹，失败率高得惊人**。研究显示生产环境多 agent 系统失败率 41%–86%，且 **~79% 的失败来自"规格定义 + 协调"而非模型本身**（MAST 分类学，1600+ 轨迹）。Anthropic 的多 agent 研究系统虽比单 agent 强 90.2%，但**代价是约 15× 的 token 成本**，且只在"广度优先、可并行"的研究类任务上成立。Cognition 则直接主张"别做多 agent"，对**写类/强依赖任务**（如编码）用单线程 agent + 上下文工程更可靠。

5. **平台真正的护城河在"非 agent 部分"**：上下文/记忆工程、状态持久化与恢复、工具可靠性、可观测性（OpenTelemetry 级 tracing）、评估体系与成本控制。谁能把这几层做成**可复用、可观测、可回滚**的基础设施，谁就赢。

**给你的落地建议（详见第九章）**：技术栈首选 **LangGraph（编排/状态）+ MCP（工具接入）+ OpenTelemetry/LangSmith（可观测）**，模式从 **Supervisor** 起步，第一个里程碑做"单 supervisor + 2–3 个专职 worker + 一个独立校验 agent"，同步搭最小 eval 集。

---

## 二、先决问题：到底要不要做 Multi-Agent

> 这是整个调研里**最重要**、也最容易被跳过的一章。选错拓扑是"生产 AI 里最贵的单一决策"（metacto 2026）。

### 2.1 什么是"multi-agent"（先对齐定义）

一个 **agent** = "LLM 在循环里自主调用工具"（plan → tool call → observe → 反思 → 再决策）。**multi-agent 系统** = 多个这样的 agent 协作完成一个目标，它们各自拥有**独立的上下文窗口、角色/系统提示、工具子集**，通过某种编排机制交换信息。

关键区分：**多 agent ≠ 多步/多工具/多 prompt 链**。prompt chaining（把一次调用的输出喂给下一次）只是线性流程；multi-agent 的本质特征是**多个独立上下文 + 需要协调/委派**。很多号称"multi-agent"的系统其实是单 agent 多工具，这完全没问题——**能用单 agent 解决就别拆**。

### 2.2 多 agent 的收益从哪来（三个真实理由）

只有以下三种情况，拆成多 agent 才有正收益（Anthropic / neverbiasu 归纳）：

| 收益来源 | 机理 | 典型场景 |
|---|---|---|
| **并行加速** | 多个 subagent 同时探索不同方向，墙钟时间下降 | 广度优先研究、多源信息聚合（Anthropic 实测复杂查询提速最高 90%） |
| **突破单上下文窗口** | 每个 subagent 用自己的窗口深挖，只回传压缩摘要（1–2k token） | 需要读取的信息量远超单窗口；大规模代码库/文档分析 |
| **关注点隔离 + 专业化** | 每个角色只看自己该看的上下文，错误局限在本工序 | 研究/写作/复审分离；一个独立 agent 专门做引用核验 |

**一句判据**：*read（读）比 write（写）更容易并行*。研究/检索是读密集、子任务弱依赖 → 适合多 agent；编码/写作是写密集、决策强耦合 → 并行写容易产生"冲突的隐含决策"，多 agent 反而更糟（neverbiasu / Cognition）。

### 2.3 多 agent 的代价（诚实清单）

- **成本爆炸**：Anthropic 明确指出多 agent 研究系统约 **15× 于普通对话**的 token 消耗；agent 越多、层级越深，成本越不可控。
- **可靠性下降**：失败率 41%–86%（futureagi 2026 综述）；每一次 agent 间 handoff 都是一次**上下文丢失**的机会（Cognition）。
- **调试地狱**：错误可能藏在三层委派之下；出现"静默失败 / fail-plausible"——LLM 把错误包装成看似合理的叙述交付给用户（arXiv 2606.14589）。
- **协调开销**：agent 越多，用于"对齐彼此在做什么"的开销越大，边际收益递减。

### 2.4 决策树：先自问四个问题

```
Q1. 单个强 agent + 好的上下文工程能不能解决？
      └─ 能  → 就用单 agent（别拆）。多数运营/客服/内部工具属于这一档。
      └─ 不能 ↓
Q2. 任务能否在"动手前"就定好完整计划？
      └─ 能  → Orchestrator-Worker（编排器一次性派发，worker 之间不通信）
      └─ 不能（需边做边调整）↓
Q3. 单个协调者的上下文窗口装得下"全局状态 + 各 worker 回传"吗？
      └─ 装得下 → Supervisor（主管在环，每步根据结果调整）← 生产默认
      └─ 装不下 / 跨多领域 / agent > 5–8 个 → Hierarchical（多级主管）
Q4. 任务是"对等协作、无明确权威层级"的探索型吗？
      └─ 是 → Swarm（去中心化，慎用，仅探索/研究）
```

> 关键提醒（Anthropic 的"隐藏彩蛋"）：即使你**不**搭完整多 agent，也能单独复用它最有价值的三个模式——**(1) 上下文写满前先外置到记忆；(2) 用自包含任务描述隔离 worker；(3) 高风险输出用独立一遍校验**。这三招在单 agent 内就能拿到大部分可靠性收益，而没有 15× 成本。

---

## 三、核心架构模式（编排拓扑）

生产环境的多 agent 拓扑高度收敛。下面 6 种覆盖了几乎所有真实系统，逐一给出**结构、适用、风险、代表实现**。

### 3.1 Orchestrator-Worker（编排器-工人 / 又名 Router-Specialist）

```
                ┌──────────────┐
        ┌──────►│ Orchestrator │◄──────┐        · 编排器一次性分解任务并派发
        │       └──────┬───────┘       │        · worker 之间【不】直接通信
        │      派发↓      ↑回传          │        · 所有结果汇总回编排器
   ┌────┴───┐   ┌────┴────┐   ┌────┴───┐
   │Worker A│   │Worker B │   │Worker C│
   └────────┘   └─────────┘   └────────┘
```

- **适用**：动手前就能把完整计划定下来、子任务边界清晰、有明确专家分工。运营、财务、客服、内部工具多属此类。
- **风险**：当"下一步依赖上一步结果"时，编排器成瓶颈（串行化）。
- **变体**：**Map-Reduce / Fan-out-Fan-in**（并行派发独立子任务→汇总）是它最常见的执行变体。
- **代表**：Anthropic 研究系统（lead + 并行 subagent）本质就是这个模式。

### 3.2 Supervisor（主管 / 又名 Manager-Subordinate）—— 生产默认

```
        ┌───────────────┐
        │   Supervisor   │  每个 subordinate 返回后，主管【留在环里】
        │  (在环协调者)   │  读取结果 → 更新计划 → 决定下一步
        └───┬───────┬───┘
       委派↓   ↑结果  委派↓   ↑结果
     ┌─────┴──┐    ┌─────┴──┐
     │ Agent1 │    │ Agent2 │   ← 专职 agent（检索/写作/校验…）
     └────────┘    └────────┘
```

- **与 Orchestrator-Worker 的区别**：编排器倾向"一次派发完就等汇总"；主管是**每一步都在环里**，根据每个下属的返回动态调整计划，更适合"边做边看"的跨域任务（研究、编码）。
- **适用**：当前**最主流**（生产占比约 38%）。可观测性与控制力最佳，天然对应组织的层级结构，单点观测。
- **代表**：LangGraph 的默认架构、Claude Agent SDK 都默认这个模式。
- **升级信号**：当 agent 超过 5–8 个、或主管上下文窗口装不下全局时 → 升 Hierarchical。

### 3.3 Hierarchical（分层 / 多级主管）

```
                    ┌──────────────┐
                    │  Top Manager │  战略层：拆大方向
                    └───┬──────┬───┘
             ┌──────────┘      └──────────┐
      ┌──────┴──────┐            ┌────────┴────┐
      │ Mid-Supervisor A │        │ Mid-Supervisor B │  战术层
      └──┬───────┬──┘            └───┬────────┬──┘
     ┌───┴─┐  ┌──┴──┐          ┌───┴─┐   ┌───┴─┐
     │Wkr  │  │Wkr  │          │Wkr  │   │Wkr  │      执行层（叶子）
     └─────┘  └─────┘          └─────┘   └─────┘
```

- **适用**：复杂多领域、大规模 agent 网络；层级可**映射企业的部门结构**。每一级独立管理自己的上下文窗口，没有任何单个 agent 需要装下整个问题。
- **核心风险**：**上下文不一致沿层级级联**——若某个中层主管对关键概念的定义与同级不同，错误会传导到它下面所有 worker；三层之下出错，根因定位极难，强依赖成熟的可观测性工具。
- **占比**：约 22%。

### 3.4 Sequential Pipeline（顺序流水线）

```
  ┌────────┐   ┌────────┐   ┌────────┐   ┌────────┐
  │ Stage1 │──►│ Stage2 │──►│ Stage3 │──►│ Stage4 │   每阶段专注一件事，
  │ 规划    │   │ 执行    │   │ 优化    │   │ 复审    │   输出即下一阶段输入
  └────────┘   └────────┘   └────────┘   └────────┘
```

- **适用**：固定顺序、无需分支的确定性工作流（如"规划→执行→优化→复审"）。可控性最高、最好调试。
- **风险**：不灵活；任一阶段失败需要明确的回退/重试策略。
- **说明**：这也是很多"看起来像多 agent、实则是角色化流水线"的系统，工程上非常稳，推荐作为**多 agent 的入门形态**。

### 3.5 Swarm / Mesh（去中心化蜂群 / 网状）

```
     ┌───────┐        ┌───────┐        · 无中心协调者
     │Agent A│◄──────►│Agent B│        · agent 之间【直接】handoff / 对等协作
     └───┬───┘        └───┬───┘        · 谁最合适谁接手
         │    ┌───────┐   │
         └───►│Agent C│◄──┘
              └───────┘
```

- **适用**：对等协作、无明确权威层级的探索型/研究型工作流。
- **风险（大）**：极易 **handoff 死循环**、难收敛、难调试；把它用在"本该有权威层级"的问题上会灾难。生产采用率极低。
- **代表**：OpenAI 早期的 Swarm（已演进为 Agents SDK 的 handoff 机制）。

### 3.6 拓扑对比速查表

| 拓扑 | 控制力/可观测 | 成本 | 并行度 | 调试难度 | 何时用 | 生产占比\* |
|---|---|---|---|---|---|---|
| Orchestrator-Worker | 高 | 中 | 高（fan-out） | 低 | 计划可前置、分工清晰 | 高（最常见） |
| **Supervisor** | **高** | 中 | 中 | 低-中 | **跨域、边做边调（默认）** | **~38%** |
| Hierarchical | 中 | 高 | 高 | 高 | 多领域、>5–8 agent | ~22% |
| Sequential Pipeline | 最高 | 低 | 低 | 最低 | 固定顺序、确定性 | 常见 |
| Swarm / Mesh | 低 | 高 | 高 | 最高 | 探索型、对等协作 | 极少 |

> \*占比引自 usetransactional 2026（350+ 论文 + 120 企业部署）与 metacto/glukhov 2026，作趋势参考而非精确统计。
>
> **选型口诀**：*能单 agent 就别多 agent；要多 agent 先 Supervisor；装不下再 Hierarchical；固定流程用 Pipeline；Swarm 只做实验。*

---

## 四、框架全景（2026）与选型

> 2025→2026 发生了大洗牌，务必用**当前**的事实做选型（很多旧教程已过时）：
> - OpenAI 把实验性的 **Swarm** 毕业为生产级 **Agents SDK**（2025-03）。
> - Google **ADK** 2025 年 alpha，**2.0 于 2026-04** 生产可用，覆盖四语言。
> - Anthropic 把 Claude Code SDK 更名为 **Claude Agent SDK**（野心超出编码）。
> - Microsoft 把 **Semantic Kernel + AutoGen 合并**为 **Microsoft Agent Framework**（已 GA）；原 **AutoGen 进入维护模式**，社区分叉出 **AG2**。
> - **LangGraph 1.0（2025-10）** 带 API 稳定性承诺，成为"最接近生产默认"的选择。

### 4.1 七个主流框架逐一定位

| 框架 | 核心抽象 | 编排风格 | 状态管理 | MCP | 生产成熟度 | 最适合 | 许可 |
|---|---|---|---|---|---|---|---|
| **LangGraph** | 显式状态图（StateGraph） | Supervisor / 图 | **检查点 + 持久化执行 + HITL** | 适配器 | **高** | 有状态、需强控制、需审计与人在环的工作流 | MIT |
| **CrewAI** | 角色/目标/背景（Crew） | 角色制 crew + 事件驱动 flow | flow 内会话态 | 经工具 | 中 | 快速原型、"专家团队"映射业务流程 | MIT |
| **OpenAI Agents SDK** | 模型+工具+循环 | **Handoffs（一等公民）** + agent-as-tool | 内置 sessions + tracing | 是 | 中-高 | OpenAI 生态、MCP 优先、极简快发 | MIT |
| **Google ADK 2.0** | 生产 agent 运行时 | 分层 agent + 工作流 | 会话态 | 是（双向流） | **高（Google Cloud 内）** | Vertex AI 生态、多语言、企业可观测/部署 | Apache 2.0 |
| **Claude Agent SDK** | agent + 文件系统/shell/环境 | Supervisor + subagent | 外置记忆/文件 | **最深** | 高（上升快） | 构建在 Claude 上、环境型任务、编码/computer use | 专有 SDK |
| **Microsoft Agent Framework** | Workflows + chat 模式 | 工作流 + 群聊 | 会话态 + 检查点 | 是 | 中-高（GA） | C#/.NET、深度 Azure 集成 | MIT |
| **AG2**（AutoGen 分叉） | GroupChat + 事件驱动 | 会话式群聊 | 有状态运行时 | 是 | 中 | 研究、需拼接多框架 agent 的"通用运行时" | Apache 2.0 |

补充：**DSPy** 不是编排框架而是**提示/流水线优化器**——把 prompt 从"手调"变成"编译优化"，适合高吞吐流水线；与上面任一编排框架正交组合。

### 4.2 框架抽象哲学对比（选型的关键是"匹配隐喻"）

不同框架把"多 agent"抽象成不同心智模型，**选型的本质是让框架的隐喻匹配你的问题形状**：

- **LangGraph = 状态机 / 图**：你显式定义节点、边、条件跳转、共享 state。样板代码多、学习曲线陡，但**任何能画成状态图的流程都能可靠落地**，且"必须能从崩溃中恢复"的场景只有它做得最好（检查点 + durable execution）。
- **CrewAI = 一支队伍**：给每个 agent 设"角色/目标/背景故事"，像组建团队。一下午能出原型，但复杂控制流不如图清晰。
- **OpenAI Agents SDK = 路由/交接**：核心是 handoff——"这事该交给谁"。API 最小最可读，适合"routing 形状"的问题。
- **Claude Agent SDK = 给 agent 一个环境**：它问的不是"如何编排 agent"，而是"如果 agent 有文件系统、shell 和判断力会怎样"。MCP 集成最深、有 extended thinking 和 computer use。据 LangChain《State of AI》报告，其生产部署量在 2026 年初**超过了 AutoGen**。
- **Google ADK = 企业运行时**：主管派发、工人上报，最"多语言"（Python/Java/Go/TS），且模型锁定最软（虽为 Gemini 优化，但原生支持 Claude/Ollama/vLLM/LiteLLM）。

### 4.3 选型决策（按你的约束）

```
你的首要约束是什么？
├─ 需要长时运行、可恢复、强审计的有状态工作流 ────────► LangGraph
├─ 想一周内出一个"专家团队"原型、映射某条业务流 ──────► CrewAI
├─ 已在 OpenAI 生态、要 MCP 优先、要最小可读代码 ─────► OpenAI Agents SDK
├─ 构建在 Claude 上、任务是环境/文件/编码型 ──────────► Claude Agent SDK
├─ 团队是 C#/.NET 或深度 Azure ──────────────────────► Microsoft Agent Framework
├─ 需要 Python/Java/Go/TS 多语言 + Google Cloud 部署 ─► Google ADK 2.0
└─ 要把多个框架的 agent 拼在一起（通用运行时）────────► AG2
```

**给"从 0→1 自建平台"的建议**：**首选 LangGraph 作为编排/状态内核**。理由：(1) 状态图 + 检查点直接命中平台最难的"持久化/恢复/人在环"；(2) 1.0 稳定 + MIT + 无厂商锁定；(3) 与 MCP、LangSmith 可观测无缝；(4) Supervisor/Hierarchical 都能显式表达。若团队是 .NET 则用 Microsoft Agent Framework，若强绑 Google Cloud 则用 ADK。

> ⚠️ **不要给新项目选 AutoGen**（已维护模式）。存量 AutoGen 迁移路径：要 Azure → Microsoft Agent Framework；要中立/无锁定 → LangGraph（架构最接近）或 CrewAI（角色制最易迁）。

---

## 五、通信与互操作协议栈（MCP / A2A / AGNTCY / AP2）

> 2026 年最重要的认知：**这些协议不是竞争关系，而是同一栈的不同分层**，且已统一由 **Linux Foundation（Agentic AI Foundation, AAIF）** 治理。类比网络协议栈：MCP≈把外设插进电脑的 USB-C，A2A≈agent 之间的 HTTP，AGNTCY≈agent 界的 DNS/IP。

### 5.1 协议分层全景

```
┌─────────────────────────────────────────────────────────────┐
│  商务层    AP2 (Agent Payments Protocol)                       │
│           agent↔agent 支付/交易（A2A 的正式扩展）               │
├─────────────────────────────────────────────────────────────┤
│  协作层    A2A (Agent2Agent)  —— 水平：agent ↔ agent           │
│           发现(Agent Card)、任务委派、协商、跨厂商/框架协作      │
├─────────────────────────────────────────────────────────────┤
│  基础设施  AGNTCY / "Internet of Agents"                       │
│           OASF(身份/schema/注册) + SLIM(安全低延迟消息)         │
│           —— agent 界的 DNS：定位与验证对端                     │
├─────────────────────────────────────────────────────────────┤
│  工具层    MCP (Model Context Protocol) —— 垂直：agent ↔ 工具  │
│           连接数据库、API、文件系统、prompt（事实标准）         │
└─────────────────────────────────────────────────────────────┘

生产组合范式：每个专职 agent 【对内是 MCP 客户端】（用自己的工具），
              【对外是 A2A 对端】（与其他 agent 协作）。
```

### 5.2 逐个协议速览（含关键事实与时间）

| 协议 | 作者/治理 | 层/用途 | 传输 | 发现机制 | 2026 年中状态 |
|---|---|---|---|---|---|
| **MCP** | Anthropic（2024-11）；2025-12 捐给 Linux Foundation | agent→工具/数据/prompt（垂直） | JSON-RPC 2.0 over stdio 或 Streamable HTTP（可选 SSE） | `initialize` 握手协商 | **事实标准**，最广采用；OpenAI/Google/MS 都支持；约 97M SDK 下载/月、5800+ server；最新 spec `2025-11-25` |
| **A2A** | Google（2025-04）；捐 Linux Foundation | agent↔agent（水平） | JSON-RPC over HTTP，SSE 流式 | **Agent Card** @ `/.well-known/agent.json` | **v1.0**（2026）；已吸收 IBM ACP（2025-08）；150+ 组织；显式分层规范 |
| **IBM ACP** | IBM Research / BeeAI（2025-03） | agent↔agent（与 A2A 重叠） | REST/HTTP、WebSocket | REST 端点 | **已并入 A2A 生态**；其"长任务持久态/异步"概念被 A2A 吸收 |
| **AGNTCY** | Cisco/Outshift + LangChain + Galileo（2025-03 开源） | 发现/身份/注册（基础设施） | SLIM 消息 | OASF（agent schema/身份） | Linux Foundation 项目；定位"管道"，承载 A2A/MCP 而非竞争 |
| **AP2** | Google + Coinbase（2025-09） | agent↔agent 支付 | A2A 扩展 | 继承 A2A | A2A 的正式扩展 |

### 5.3 工程建议

- **第一步只做 MCP**：它解决最具体、最迫切的问题——让你的 agent 可靠地接入工具与数据。采用面最广、生态最成熟（5800+ server 可直接复用）。**平台的工具层直接建在 MCP 上**，让"同一个工具"能被 LLM、HTTP、UI 多路复用。
- **有"真正独立、需跨团队/跨厂商协作的多 agent"时再上 A2A**：用 Agent Card 做能力发现，用它的任务生命周期做长任务/异步。**不要一上来就 A2A 化一切**——2026 最常见的错误就是"什么都用 A2A"或"什么都用 MCP"，二者是不同层。
- **AGNTCY / AP2 保持跟踪**：除非你要做"开放 agent 市场/跨组织 agent 发现"或"agent 自主支付"，否则暂不需要投入。
- **安全基线**：MCP 公共 server 用 OAuth 2.1 + PKCE；A2A 在 Agent Card 的 `securitySchemes` 声明鉴权。**agent 的工具权限要最小化 + 可审计**（这是企业/政企场景的红线）。

---

## 六、平台的六个工程硬骨头

> 选拓扑、选框架、选协议只是"骨架"。平台能不能用、稳不稳、贵不贵，取决于下面六个维度——**这也是平台真正的护城河所在**。

### 6.1 上下文工程与记忆（最核心）

"context engineering"（上下文工程）在 2025→2026 成为核心范式：**不是把 prompt 写好，而是精细管理"在每个时刻，什么信息、以什么格式、进入模型有限的注意力预算"**（Anthropic）。

**记忆分层**（平台需要显式建模）：

- **短期/工作记忆**：对话窗口、scratchpad、任务状态。易失、受窗口限制。
- **长期记忆**三类：**语义**（事实/知识/画像 → 向量库+图）、**情景**（事件/轨迹 → DB）、**过程**（技能/工具用法/成功模板 → 模板库）。

**四个核心操作**：写入（重要性打分 + 抽取结构化事实，不存原始对话）→ 召回（`score = α·相关性 + β·新近性 + γ·重要性`，再 rerank）→ 压缩（递归摘要 + 分页换出 + 结构化替代原文）→ 更新/遗忘（ADD/UPDATE/DELETE/NOOP + 冲突消解）。

**Anthropic 给的三招具体技术**：
- **Compaction（压紧）**：对话接近窗口上限时，摘要压缩后继续——适合需要大量来回的任务。
- **结构化笔记（note-taking）**：把关键信息写到外部笔记，适合有清晰里程碑的迭代开发。
- **Sub-agent 架构**：让 subagent 用干净窗口深挖（可烧几万 token），**只回传 1–2k token 的蒸馏摘要**——主 agent 专注综合，检索细节隔离在 subagent 内。

> **"窗口够大就不用记忆了吗？"→ 不对**。①成本随 token 线性涨；②lost-in-middle，长上下文利用率反而降；③跨会话仍需持久化；④全塞进去会引入噪声降准确率。记忆 = 按需注入最小相关上下文，是**效果 + 成本的联合优化**。

### 6.2 状态管理、持久化与恢复

多 agent 是长时运行系统，**状态必须能持久化、能从崩溃点恢复、能人在环介入**。

- **检查点（checkpointing）**：LangGraph 的核心能力，每步存快照，可回退、可恢复、可分支。企业场景几乎是刚需。
- **外置状态**：Anthropic 明确——上下文接近上限时，**把计划写到外部记忆而非指望更大窗口**；subagent 之间重置上下文避免携带无关状态。
- **Artifact 模式**：subagent 把产出写到**共享存储**，只给 lead 返回轻量引用，而不是冗长易失真的摘要。这对"大产物"（代码、报告、数据集）尤其重要。

### 6.3 编排与控制流

- **终止条件**是最容易漏的一环——MAST 显示"缺少终止条件/过早终止"是重要失败源。必须有：最大步数、墙钟超时、stall（连续无进展）检测、循环/振荡检测。
- **委派契约**（Anthropic 的硬教训）：给每个 subagent 必须明确**四件事——目标(objective)、输出格式(output format)、工具与数据源指引、清晰的任务边界(何为"完成")**。缺任何一个，subagent 就会漂移、重复劳动或留下空白。反例：早期只说"研究半导体短缺"，结果三个 subagent 重复搜同样内容。
- **按复杂度缩放投入**（把规则写进 prompt，防止"杀鸡用牛刀"）：简单事实查找 → 1 个 agent、3–10 次工具调用；直接对比 → 2–4 个 subagent、各 10–15 次；复杂研究 → 10+ 个 subagent 分工。
- **确定性优先**：能用确定性代码/规则做的（路由、校验、机械执行）就别花 LLM round-trip。这是降本增稳的关键工程手筋。

### 6.4 工具层（可靠性 5 要素）

工具调用是 agent 出错的重灾区，平台层应提供统一的可靠性保障：

1. **统一注册与多路复用**：同一个工具被 LLM / HTTP / UI 调用走同一段代码、同一 preflight、同一 trace（基于 MCP 实现）。
2. **参数校验与纠错**：类型/枚举校验、拼写纠错（如 Levenshtein "didYouMean"）、方向/语义校验。
3. **幂等**：同参数重复调用返回 noop 而非报错，避免污染。
4. **原子批量**：多步操作要么全成要么全 reject，避免半成品状态。
5. **反振荡**：滑动窗口检测 delete→add / add→delete / 同工具同参数≥N 次，注入 coaching，必要时**硬停**（实测"光提示止不住"某些循环）。

### 6.5 可观测性（多 agent 的生命线）

单 agent 的日志不够用——多 agent 必须捕获**跨 agent 的委派、推理轨迹、规划步骤**。

- **标准**：以 **OpenTelemetry** 为底，把每次 LLM 调用、工具调用、agent handoff 都记为结构化 **span**，可重建完整执行路径、定位失败起点。
- **工具生态**：LangSmith（LangChain 系）、Future AGI TraceAI、Orq.ai、LumiMAS（监控+异常检测+根因分析）等。
- **警惕"静默失败 / fail-plausible"**：LLM 会把错误**包装成流畅可信的叙述**交付给用户——这是 LLM 时代特有、也最危险的失败（arXiv 2606.14589）。对策：关键输出独立校验 + 断言/治理检查 + 引用核验。

### 6.6 评估（Eval）与成本/延迟

- **从第一天就搭最小 eval 集**——这是把"我觉得有效"变成"我能证明有效"的唯一途径，也是 MAST 强调"79% 失败来自规格与协调"的直接对策。
- **指标分层**：端到端（任务成功率、准确率）+ 组件级（召回命中率/MRR、无效重试数、平均工具调用数、token 量、延迟、单任务成本）。
- **方法**：固定回归集 + LLM-as-a-Judge（MAST 论文验证其与人工标注高一致）+ A/B（开/关某层防线对比）。
- **成本红线**：多 agent 约 15× token，必须监控**单任务成本**并设预算护栏；用"按复杂度缩放"和"小模型跑 subagent、大模型做 lead"控成本（Anthropic：Opus 做 lead、Sonnet 做 subagent）。

---

## 七、失败模式与教训（MAST + 两派对照）

### 7.1 MAST 失败分类学（用数据说话）

论文《Why Do Multi-Agent LLM Systems Fail?》（arXiv 2503.13657）分析 7 个主流框架、1600+ 标注轨迹，建立首个多 agent 失败分类学（14 种模式、3 大类，标注一致性 kappa=0.88）。生产环境失败率 **41%–86%**（futureagi 2026）。三大类占比：

| 大类 | 占比 | 典型模式 | 平台对策 |
|---|---|---|---|
| **① 系统设计/规格** | **~42%** | 任务误解、角色定义模糊、分解不当、重复角色、**缺终止条件** | 委派契约四要素、显式终止条件、角色去重、Pipeline 化 |
| **② Agent 间失配** | **~37%** | 通信破裂、**handoff 时上下文丢失**、输出冲突、格式不匹配 | 共享上下文/轨迹、结构化消息 schema、格式校验、冲突消解 |
| **③ 任务校验/终止** | **~21%** | 过早终止(6.2%)、校验不完整(8.2%)、校验错误(9.1%) | 独立校验 agent、完成度断言、引用核验 |

> **最反直觉的结论**：**~79% 的失败来自"规格 + 协调"，而不是模型或基础设施**。工程师总想着"换个更强模型 / 优化 token"，但真正的病根在上游的**规格定义与协调设计**。这直接指导平台投入方向：**把钱花在编排契约、上下文传递、可观测与评估上，而不是无脑堆模型**。

### 7.2 两派对照：Anthropic vs Cognition（同一周发布、观点看似对立）

2025 年同一周，Anthropic 发《How we built our multi-agent research system》（力挺多 agent），Cognition 发《Don't Build Multi-Agents》（劝退多 agent）。**二者其实不矛盾，只是任务类型不同**：

| 维度 | Anthropic（挺多 agent） | Cognition（劝退多 agent） |
|---|---|---|
| 任务类型 | **研究**（读密集、广度优先、子任务弱依赖） | **编码**（写密集、决策强耦合、需全局一致） |
| 核心主张 | orchestrator-worker，lead+并行 subagent，隔离上下文 | **单线程线性 agent** + 上下文工程；别拆 |
| 实测 | 多 agent 比单 Opus **强 90.2%**（内部研究 eval） | 拆分导致上下文丢失、决策冲突，系统脆弱 |
| 两条铁律 | 委派契约四要素、外置状态、独立校验 | ①**共享完整上下文与轨迹**；②**"行动即隐含决策"**，冲突的决策 → 坏结果 |
| 隐含边界 | 只在"可并行、超单窗口、有清晰分工"时成立 | 违反上面两条铁律的架构应"从一开始就排除" |

**融合结论（本报告立场）**：

1. **读并行、写串行**：research/检索类拆多 agent；coding/writing 类默认单 agent。
2. **能共享全上下文就共享**——每个动作都应被"其他部分做过的所有相关决策"告知；受窗口所限做不到时，才谨慎拆分并承担对应的可靠性代价。
3. **多 agent 是"效果 vs 成本/可靠性"的显式取舍**，不是默认选项。先榨干单 agent，再上多 agent。

### 7.3 十条可直接落地的教训清单

1. 能单 agent 解决就别拆（默认单 agent + 上下文工程）。
2. 要拆，先 Supervisor；委派必给"目标/格式/工具/边界"四要素。
3. 按查询复杂度缩放 agent 数与工具调用数，写进 prompt。
4. 上下文写满前外置到记忆，别指望更大窗口。
5. subagent 只回传 1–2k token 蒸馏摘要 + 共享存储放大产物（artifact 模式）。
6. 每个循环都要有硬终止（步数/墙钟/stall/振荡）。
7. 高风险输出（引用/代码/事实）用**独立一遍**校验 agent。
8. read 可并行、write 慎并行（并行写易产生冲突的隐含决策）。
9. 从第一天就上 OpenTelemetry 级 tracing + 最小 eval 集。
10. 警惕 fail-plausible：错误信号必须以可行动形式到达人类。

---

## 八、平台参考架构（分层设计）

综合以上，给出一个**厂商中立、可演进**的 multi-agent 平台参考架构。设计原则：*编排与执行解耦、工具统一复用、状态可持久可恢复、可观测与评估内建、模型可插拔*。

```
┌──────────────────────────────────────────────────────────────────────┐
│  ⑦ 接入层  Chat UI / API / SDK / IM 接入   +   SSE/WS 流式（reasoning） │
├──────────────────────────────────────────────────────────────────────┤
│  ⑥ 编排层  Orchestration (LangGraph)                                    │
│     · 路由/分类（优先确定性规则，避免多一次 LLM）                        │
│     · 拓扑：Supervisor（默认）→ 可插拔 Hierarchical / Pipeline          │
│     · 控制流：检查点 · 终止条件 · 反振荡 · 人在环(HITL)                  │
├──────────────────────────────────────────────────────────────────────┤
│  ⑤ Agent 层  角色化 agent（system prompt + 工具子集 + 独立上下文）       │
│     · Lead/Supervisor · 专职 Worker(检索/写作/分析) · 独立校验 Agent     │
│     · 对内 = MCP 客户端；对外(可选) = A2A 对端                           │
├──────────────────────────────────────────────────────────────────────┤
│  ④ 记忆层  Memory Manager（中间件，不侵入编排）                          │
│     工作记忆(状态机) · 语义(向量库+图) · 情景(轨迹DB) · 过程(模板库)     │
│     操作：写入(抽事实) · 召回(相关+新近+重要+rerank) · 压缩 · 更新/消解  │
├──────────────────────────────────────────────────────────────────────┤
│  ③ 工具层  Tool Registry over MCP                                       │
│     · 统一注册/多路复用 · preflight 校验/纠错 · 幂等 · 原子批量           │
│     · MCP server 生态（DB/API/文件/检索/代码执行…）                      │
├──────────────────────────────────────────────────────────────────────┤
│  ② 模型层  Model Gateway（可插拔 + LiteLLM 兜底）                        │
│     · lead 用强模型、worker 用性价比模型 · 降级/重试/限流 · 成本核算      │
├──────────────────────────────────────────────────────────────────────┤
│  ① 基础设施  可观测(OpenTelemetry+LangSmith) · Eval · 会话隔离 · 鉴权    │
│     · 每次 LLM/工具/handoff 记 span · 回归集 · 预算护栏 · RBAC/审计       │
└──────────────────────────────────────────────────────────────────────┘
        横切：安全与治理（最小权限工具、审计日志、PII、合规）
```

**关键设计要点**：

- **⑥编排 与 ⑤Agent 解耦**：编排层只管"谁在什么条件下做什么"，agent 只管"在给定上下文里干一件事"。这让拓扑可从 Supervisor 平滑升级到 Hierarchical/Pipeline 而不动 agent 实现。
- **④记忆层做成中间件**：夹在 Agent 与工具/存储之间，agent 通过"记忆工具"主动读写（MemGPT 范式），不侵入编排。每角色**执行前召回、执行后写入**。
- **③工具层统一在 MCP 之上**：一个工具四路复用（LLM/HTTP/UI/其他 agent），一套 preflight、一套 trace。
- **②模型层可插拔**：用 Model Gateway（或 LiteLLM）抽象，支持"lead 强模型 + worker 性价比模型"，天然支持私有化/多模型（政企场景刚需）。
- **①可观测与 Eval 是地基不是补丁**：从第一行代码就打 span、建回归集。

---

## 九、0→1 落地路线图与选型决策

### 9.1 推荐技术栈（厂商中立、可私有化）

| 层 | 首选 | 备选 / 说明 |
|---|---|---|
| 编排/状态 | **LangGraph**（状态图 + 检查点 + HITL） | .NET → MS Agent Framework；Google Cloud → ADK 2.0 |
| 工具接入 | **MCP**（统一工具协议） | 直接复用现成 MCP server 生态 |
| Agent 协作（可选） | **A2A**（仅当需跨团队/框架协作） | 早期可不引入 |
| 模型网关 | **LiteLLM / 自建 Gateway** | 支持多模型、私有化、成本核算 |
| 记忆 | 向量库(pgvector/Milvus) + 图(可选) + Mem0 范式 | 先工作记忆，再语义/情景/过程 |
| 可观测 | **OpenTelemetry + LangSmith** | 或 Future AGI / Orq.ai / Langfuse |
| 评估 | 自建回归集 + LLM-as-Judge | 从第一天搭最小集 |

### 9.2 分阶段路线图

```
里程碑 0（第 1–2 周）｜地基先行，别急着多 agent
  · 搭 单 agent + MCP 工具层 + OpenTelemetry tracing + 最小 eval 集(5–10 用例)
  · 把上下文工程做扎实（compaction / 结构化笔记）
  · 产出：一个可观测、可评估的单 agent 基线（作为一切对照的 baseline）

里程碑 1（第 3–5 周）｜引入 Supervisor + 少量专职 worker
  · LangGraph 搭 Supervisor：1 主管 + 2–3 专职 worker（如 检索/分析/写作）
  · 每个 worker 严格委派契约四要素；worker 只回传蒸馏摘要
  · 加终止条件(步数/墙钟/stall) + 反振荡 + 检查点
  · 产出：能跑通"广度优先"任务，且比 baseline 有可量化提升

里程碑 2（第 6–8 周）｜可靠性与校验
  · 加【独立校验 agent】（引用核验/事实校验/格式校验）
  · 工具层补齐 preflight 校验/纠错/幂等/原子批量
  · Eval 扩到 30–50 用例，跑"开/关某层防线"A/B，量化成功率/成本/延迟
  · 产出：失败率、单任务成本、延迟三条曲线可监控

里程碑 3（第 9–12 周）｜记忆与规模化
  · 上记忆中间件：先工作记忆持久化 + 情景(轨迹)记忆，再语义召回(相关+新近+重要+rerank)
  · 视规模决定是否升级 Hierarchical（agent > 5–8 或主管上下文超限时）
  · 视需要引入 A2A（跨团队/跨框架协作）
  · 产出：跨会话记忆 + 可按需扩展的拓扑

贯穿全程：成本预算护栏、安全最小权限、审计日志、灰度发布
```

### 9.3 一页选型决策总表

| 决策点 | 结论 |
|---|---|
| 要不要多 agent | 先单 agent + 上下文工程；仅"可并行/超单窗口/清晰分工"才拆 |
| 起步拓扑 | **Supervisor**；固定流程用 Pipeline；>5–8 agent 升 Hierarchical；Swarm 只做实验 |
| 编排框架 | **LangGraph**（.NET→MS Agent Framework；GCP→ADK；Claude 生态→Claude Agent SDK） |
| 工具协议 | **MCP**（第一优先）；A2A 按需后加 |
| 模型策略 | lead 强模型 + worker 性价比模型；网关抽象、可私有化 |
| 最该投入 | 规格/委派契约 + 上下文传递 + 可观测 + Eval（79% 失败在这，不在模型） |
| 最该避免 | 无脑堆 agent、缺终止条件、handoff 丢上下文、无 eval 靠感觉、什么都 A2A |

---

## 十、参考资料

> 均为 2025–2026 一手工程博客 / 规范 / 论文，按主题归类。访问日期：2026-07。

**架构模式**
- metacto, *AI Agent Orchestration Patterns: A Production Guide* — https://www.metacto.com/blogs/ai-agent-orchestration-patterns
- usetransactional, *Multi-Agent AI Orchestration: Architecture Patterns for Production Systems (2026)* — https://usetransactional.com/research/multi-agent-orchestration-production-2026
- atlan, *How to Orchestrate Multi-Agent AI Systems at Scale in 2026* — https://atlan.com/know/multi-agent-system-orchestration/
- Rost Glukhov, *Multi-Agent Orchestration Patterns: A Practical Guide* — https://www.glukhov.org/ai-systems/architecture/multi-agent-orchestration-patterns/

**框架对比（2026）**
- RaftLabs, *AI Agent Frameworks: LangGraph, crewAI, ADK Compared* — https://www.raftlabs.com/blog/ai-agent-framework-comparison
- noderguru, *AI Agent Frameworks Compared in 2026 (DSPy/Claude/OpenAI/CrewAI/AutoGen/LangGraph/ADK)* — https://noderguru.dev/en/blog/ai-agent-frameworks-comparison-2026-en
- Effloow, *AI Agent Frameworks Compared 2026* — https://effloow.com/articles/ai-agent-frameworks-compared-2026
- Medium (Suresh Kumar), *OpenAI Agents SDK vs Google ADK vs Claude Agent SDK vs LangGraph vs CrewAI* — https://medium.com/system-design-mastery-series/openai-agents-sdk-vs-google-adk-vs-claude-agent-sdk-vs-langgraph-vs-crewai-i-compared-all-five-so-60ad1d4a161e

**通信协议**
- InventiveHQ, *AI Agent Protocols Explained: MCP vs A2A vs ACP* — https://inventivehq.com/blog/ai-agent-protocols-mcp-a2a-acp
- Tyk, *Agent Protocols: A Complete Guide to MCP, A2A and ACP* — https://tyk.io/learning-center/agent-protocols-a-complete-guide-to-mcp-a2a-and-acp/
- niteagent, *Building with the 2026 Agent Protocol Stack: MCP, A2A* — https://niteagent.com/blog/2026-06-07-agent-protocol-stack-mcp-a2a-production/
- Chanl, *Build the MCP + A2A agent protocol stack from scratch* — https://www.channel.tel/blog/a2a-mcp-agent-protocol-stack-build-from-scratch

**工程实践 / 两派观点**
- Anthropic, *How we built our multi-agent research system* — https://www.anthropic.com/engineering/multi-agent-research-system
- Anthropic, *Effective context engineering for AI agents* — https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents
- Cognition, *Don't Build Multi-Agents* — https://cognition.com/blog/dont-build-multi-agents
- Jason Liu, *Why Cognition does not use multi-agent systems* — https://jxnl.co/writing/2025/09/11/why-cognition-does-not-use-multi-agent-systems/

**失败模式 / 可观测**
- *Why Do Multi-Agent LLM Systems Fail?*（MAST 分类学） — https://arxiv.org/pdf/2503.13657
- FutureAGI, *Why do multi agent LLM systems fail (2026 Guide)* — https://futureagi.substack.com/p/why-do-multi-agent-llm-systems-fail
- *When Errors Become Narratives: Silent Failures in a Production LLM Agent Runtime* — https://arxiv.org/html/2606.14589v1
- *LumiMAS: Real-Time Monitoring and Observability in Multi-Agent Systems* — https://arxiv.org/html/2508.12412

---

> 说明：本报告结论综合了上述一手材料与通用工程判断。涉及"占比/倍数/失败率"等数字均来自具体来源并标注时间，属**趋势性参考**；不同来源统计口径不同，落地前建议结合自身场景做小规模 A/B 验证。
