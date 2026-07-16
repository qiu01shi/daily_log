# MultiAgent / Agent 记忆系统岗位 面试指南

> 面向"企业级 MultiAgent 架构 + Agent 记忆系统"方向岗位（政企、安全、云运维场景）。
> 全部内容已对照真实代码（`qiu01shi/ptII` 分支 `cursor/agent-pipeline-and-anti-thrash`，
> `org/ptolemy/agent` 包 53 个 Java 源文件）与两篇一作论文核对，标注了"能说 / 要降级 / 不能说"。

---

## 目录

1. [核心策略与总览](#1-核心策略与总览)
2. [三个必须先校准的认知](#2-三个必须先校准的认知)
3. [B 平台真实画像（诚实版）](#3-b-平台真实画像诚实版)
4. [项目 → JD 五条职责映射](#4-项目--jd-五条职责映射)
5. [B 平台深挖追问 30 问 + 参考答案](#5-b-平台深挖追问-30-问--参考答案)
6. [Ptolemy II（项目2）追问与迁移话术](#6-ptolemy-ii项目2追问与迁移话术)
7. [Agent 记忆系统（JD 第2条 重点补强）](#7-agent-记忆系统jd-第2条-重点补强)
8. [两篇论文：追问与到 Agent 的迁移](#8-两篇论文追问与到-agent-的迁移)
9. [需要补强的不足 + 具体补法](#9-需要补强的不足--具体补法)
10. [诚实边界清单（能说 / 不能说）](#10-诚实边界清单能说--不能说)
11. [面试前动作清单](#11-面试前动作清单)
12. [附录 A：记忆系统一页速记](#附录-a记忆系统一页速记)
13. [附录 B：B 平台 + 记忆系统落地设计（架构图 + 伪代码）](#附录-bb-平台--记忆系统落地设计架构图--伪代码)

---

## 1. 核心策略与总览

**一句话定位**：以 B 平台（Ptolemy II 自动建模 Agent）为主线，证明"企业级多智能体架构 0→1 落地"能力；用 Ptolemy II 框架研究证明"系统拆解与架构设计"能力；用两篇论文证明"前沿跟进 + 结构化知识/一致性建模"能力。

**契合度判断**：背景与岗位高度契合，但契合点需要"翻译"。B 平台基本就是 JD 第 1、4 条的实战版本；论文撑起 JD 第 3、5 条与加分项 2；最大短板是 JD 第 2 条"记忆系统"与加分项里的"评测体系 / RAG 调优 / 上下文压缩"——已在第 7、9 节补齐理论与话术。

**开场自我介绍主线**：B 平台（0→1 企业级 Agent 平台，命中加分项1）→ Ptolemy II 架构抽象能力 → 论文的前沿与 RAG/上下文实战。

---

## 2. 三个必须先校准的认知

> 不校准会被问穿。

### 2.1 简历的 "single/pipeline/mega 三种路由" 与代码对不上

代码里 `AgentRouter` 只有 `CHAT / SINGLE / PIPELINE`。MEGA（`GoalDecomposer` + `IterativePipeline` + `CheckpointStore` + `SubGoal`）是做过、实测更差后**整体删除**的（Phase 7 大回退，删了 7 个 Java 源）。

- **不要**让面试官以为 mega 是现役功能，否则追问实现细节必露馅。
- **要**主动讲成"回退故事"——这是你**最强的工程判断力名片**（见 Q6）。

### 2.2 你在低估自己最亮的两个点

- **`PlanExecutor` 确定性执行器（Phase 0.5）**：planner 出严格 JSON plan，Java 零 token 把 add_entity/connect_many/validate/run 做完，简单/中等模型**整轮跳过 builder LLM**。这是整个架构最有含金量的设计，简历却只字未提——务必补进主线叙事。
- **"复杂度有惯性但不一定有回报"的完整复盘**（双模型 + MEGA → 回退单 flash）。命中高级岗要的"架构判断 + 迭代思维"。

### 2.3 两个词要诚实降级，别踩雷

- "RAG 检索" → 实为 **词法/词元检索 + 手工领域关键词映射 + 兜底类 + 通用陷阱注入**（`CapabilityProbe`），**不是向量/embedding RAG**。口径："词法检索增强规划（lexical retrieval + 领域先验注入），embedding RAG 是下一步。"
- "批量事务回滚" 是真的（`connect_many` 单 MoML `<group>` 原子提交 + 全 reject），但**没有分布式事务**，别往分布式方向吹。

---

## 3. B 平台真实画像（诚实版）

### 3.1 真正强、可以大胆讲的（有代码支撑）

| 能力 | 真实实现（类/机制） | 讲的时候强调 |
|---|---|---|
| 四阶段流水线 | `AgentPipeline`：Phase0 planner(LLM,无tool) → Phase0.5 `PlanValidator`+`PlanExecutor`(确定性Java) → Phase1 builder(`AgentLoop`,全工具) → Phase2 refactor(仅group工具) → Phase2.5 reviewer(LLM,≤8 safe action) | 每个角色只看自己该看的上下文，出错只在自己工序内 |
| **确定性执行器**（最亮点） | `PlanExecutor` 拿干净 plan 走 `ToolRegistry.dispatch`，全成功则 `Outcome.fullyAutonomous()`=true，**整轮跳过 builder LLM**；失败比例超阈值触发一次 replan | 把 LLM 从"机械执行"解放，只在需要判断处用 |
| 启发式路由 | `AgentRouter.classify()` 纯规则、中英双语、零 LLM 调用、`{"mode":...}` 可覆盖 | 路由不该再花一次 LLM round-trip |
| Tool Calling 可靠性 5 层防线 | Tier1 `PortHints`(Levenshtein) / Tier2 `ConnectManyTool`(原子批量) / Tier3 `AgentLoop`反振荡+幂等 / Tier4 `PlanValidator`+`PlanExecutor` / Tier5 `CapabilityProbe`+`classFailures` | 每层可单独 disable 仍能跑，叠起来才工业级 |
| 反振荡（branch 同名核心） | `AgentLoop`：最近8次调用滑动窗口 + `_detectThrash`（delete→add / add→delete / 同工具同实体≥3次）注入 coaching；相同思想3次硬停；相同(tool+args)3次硬停；stall 8轮硬停；步数+墙钟双上限 | LLM 会陷入 delete-add 振荡烧光 token，用滑动窗口识别并硬终止 |
| 同一 ToolRegistry 四路复用 | `add_entity` 无论 LLM 调 / `PlanExecutor` 调 / HTTP 直调 / 前端拖拽，走同一段代码、同一 preflight、同一 trace | JD 第4条"可复用组件"的直接证据 |
| SSE 流式 reasoning | `LLMClient.chatStreaming()` default 降级；`OpenAIClient` 解析 `data:` 行、150ms 节流；前端 `agentLiveThought` live slot 就地替换不 append | 5秒看到第一帧，消除30-60秒黑屏 |
| 内核零侵入 | 全走 `MoMLParser`/`MoMLChangeRequest`/`Manager`/`ExecutionListener` 公共 API，agent 产物 Vergil 能直接打开 | 对宿主系统边界的克制 |

### 3.2 简历措辞需要校准的

- **"Session / Runtime State / Tool Registry / Event Stream 四层"** → 真实对应：`session/`（`PtolemySession`=独立 Workspace+MoMLParser+CompositeActor+Manager；`ModelContext`=喂给 LLM 的紧凑模型文本视图 = Runtime State）、`tools/ToolRegistry`、`agent/AgentTrace`+`AgentTraceListener`（step 流 = Event Stream）。抽象站得住，但要能当场把四层映射到真实类，别只背名词。
- **"single/pipeline/mega"** → 改口径为 "CHAT/SINGLE/PIPELINE + 我回退掉的 mega 实验"。

### 3.3 目前的空白（诚实承认，或现在补）

- **没有跨会话长期记忆 / 向量记忆**。最接近的是 `PtolemySession.classFailures`（按"实际归咎的类"计失败次数，≥1 次时 `ModelContext` 注入"建议换 alternative"）——**任务级失败记忆/过程记忆雏形**，作为桥接点。
- **没有 embedding RAG**（见 2.3）。
- **没有量化评测体系**：只有 5 个 smoke test + 3 个 demo（RC 低通 / PID 整定 / 修复坏 SDF 链）+ 定性"实测"。**不要报具体百分比**，除非现在测出来（见第 9 节）。
- **单模型**（DeepSeek v4-flash，OpenAI 兼容），**没有微调/RL/多模态**。

---

## 4. 项目 → JD 五条职责映射

| JD 职责 | 用什么答 | 诚实强度 |
|---|---|---|
| 1. Multi-Agent 架构设计与落地 | `AgentPipeline` 五工序 + `AgentRouter` + 结构化上下文在角色间传递 | 强，0→1 命中加分项1 |
| 2. Agent 记忆系统 | `classFailures`(失败记忆) + `ModelContext`(工作记忆外置) + `AgentTrace`(情景/可观测) + 会话隔离；理论见第7节；诚实承认缺跨会话语义记忆 | 中，需理论撑 |
| 3. 全链路优化（Prompt/FC/RAG/规划/多轮） | `PromptTemplates`(角色专属prompt) + 14工具+`ToolCallValidator` + `CapabilityProbe`(词法检索) + Plan→Validate→Execute + `AgentLoop`多轮 | 强 |
| 4. 平台能力沉淀复用 | `ToolRegistry` 一套 API 四路复用；五层防线可插拔；`AutoLayout` 子进程隔离 | 中强（单领域，别吹多业务线） |
| 5. 前沿预研落地 | 跟踪 pi/Claude Code/LangGraph/MCP；双模型+MEGA 实验与回退；两篇论文 | 强 |

---

## 5. B 平台深挖追问 30 问 + 参考答案

### A. 架构与编排

**Q1. 四阶段流水线为什么这么切？**
把建模拆成"理解意图(planner) / 机械执行(deterministic executor) / 修补(builder) / 结构优化(refactor) / 复审(reviewer)"。核心原则：**让 LLM 只做需要判断的部分，机械操作交给确定性代码**。

**Q2. Phase 0.5 确定性执行器解决了什么？没有它会怎样？**
旧版是一个大 ReAct 循环几十轮 tool、每轮都可能幻觉出错。改成 planner 出严格 JSON plan、`PlanExecutor` 用 Java 一次性 dispatch，简单/中等模型**零 token 建好并跑通**，builder 整轮跳过。这是本分支最大效率提升。

**Q3. planner 和 builder 之间传什么？**
传 `AgentPlan`（`{director, actors, wires}` 严格 JSON）+ `PlanExecutor.Outcome`（已完成/失败步骤的结构化报告 `toReport()`），**不传原始对话历史**。builder 只拿失败步骤修补。

**Q4. reviewer 打回怎么办？迭代几轮？防死循环？**
reviewer 是"读最终模型 + 推荐 ≤8 个 safe action（白名单工具 + 硬上限）"，不是无限回环。真正的反馈环在 Phase 0.5：失败比例超阈值触发**一次** replan。硬边界：`AGENT_MAX_STEPS`(默认200) + `AGENT_MAX_TURN_MS`(默认300s) + stall 8 轮。

**Q5. AgentRouter 为什么用启发式而不是让 LLM 分类？**
分类本身不该再花一次 LLM round-trip（延迟+成本）。规则覆盖 build/tweak/refactor/optimize/conversational 意图 + 空模型判断，`{"mode":...}` 可强制覆盖调试。代价：规则有边界，靠 `emptyModel` + 意图关键词兜底。

**Q6.（校准题）你简历写的 mega 呢？—— 讲回退故事**
"我实现过 MEGA（`GoalDecomposer` 把大目标拆 4-20 个 sub-goal 逐个 deterministic build + `CheckpointStore` 快照回滚）和双模型（v4-pro plan + v4-flash build）。实测两个都让质量**下降**：
1. pro 设计的理想 actor 到 flash 去建时 disambiguate 错，**心智模型不一致**放大错误；
2. MEGA 拆解多一次 LLM，**错误率 × 拆解数**被放大；
3. catalog 模式拼 47-actor 模型看不懂也跑不动。
我把它整体删回单 flash + 四阶段。教训：**先把单 LLM 路径榨干，再上多 LLM。**"

### B. Tool Calling 可靠性与防幻觉

**Q7. didYouMean 具体算法？**
`PortHints`：大小写不敏感 Levenshtein（两行 DP），候选按**分桶排序**（0 精确 / 1 前后缀 / 2 子串 / 3 纯编辑距离），bucket≥3 且距离>3 才丢弃，取 top-3；方向感知（要 input 不会推 output）；边界端口做 input/output 语义翻转。

**Q8. 方向检测（REVERSED_DIRECTION）怎么判定？**
校验时对比端口实际方向与期望连线方向，接反单独识别，返回 `actualDirection` 字段。

**Q9. 为什么把建议嵌进 message 而不只放结构化字段？**
即使 LLM 不解析 `didYouMean` 结构字段，也能从对话文本"看到"提示，双保险降低再开一轮的概率。

**Q10. connect_many 的原子性怎么保证？**
全 preflight，任一条错 → 整批 reject 并返回 `rejected[]`(带 didYouMean) + `accepted[].status="would-apply"`；全过 → 拼一条 MoML `<group>` 一次提交，撤销栈/监听器看到的是**单次原子操作**；MoML apply 若被 Ptolemy 拒则整批不落地。

**Q11. 幂等怎么做的？**
`AddEntityTool`/`SetParameterTool` 同名同类/同值再调返回 `ok=true, noop=true`，不报错。避免重复调用污染。

**Q12. 反振荡三种模式？为什么硬停而不只提示？**
Pattern A `delete X→add X`、B `add X→delete X`、C 同工具同实体≥3次 → 注入 `antiThrash` coaching；但**相同思想3次 / 相同(tool+args)3次 → 直接硬终止**，因为实测"coaching alone does not break this LLM failure mode"（光提示止不住）。

**Q13. CapabilityProbe 是 RAG 吗？（诚实降级）**
"是检索增强规划，但**词法检索**——把目标分词去停用词，加一组领域关键词映射（lstm/pid/rc/fir/ode… 扩成 canonical 原语），在 `LibraryIndex` 查真实 actor，过滤 GUI/headless 不友好类，兜底类补 Sigmoid 这种库里没索引的，再注入 3 条通用陷阱（Expression 的 PortParameter 坑 / 用 Recorder 替代 GUI sink / SDF 反馈环要 SampleDelay）。全部是**软先验不是禁令**，LLM 保留 agency。embedding 检索是下一步。"

**Q14. classFailures 是什么？和记忆什么关系？**
每次失败按"data.issues 实际归咎的类"计数（只记 Expression 不记 Ramp，避免错杀），≥1 次 `ModelContext` 注入"建议换 alternative"。**这是任务级失败记忆的雏形**——自然过渡到 JD 第 2 条记忆系统讨论。

### C. 工程 / 全栈 / 踩坑

**Q15. 前端为什么会卡死，怎么修的？**
MEGA 跑 32 sub-goal，每个 add_entity 发 3 条 NDJSON（thought+call+result），单 turn 2000+ 事件，zustand set + React rerender 撑死。修复：后端 `AGENT_ITER_QUIET` 默认只发 milestone + `AgentTrace.truncateToLastN(300)`；前端 `MAX_CHAT_ENTRIES=800`。教训：**流式协议必须在协议层做细节折叠，后端不卡 ≠ 前端扛得住**。

**Q16. SSE 流式为什么值得做？**
阻塞 LLM 调用即使成功，30-60 秒黑屏 = 用户认为卡了。SSE 后端 ~200 行 Java、前端一个 live slot + 几行渲染，投入产出极高。

**Q17. 会话隔离怎么做的？**
一个 sid 一个 `PtolemySession`（独立 Workspace+MoMLParser+CompositeActor+Manager + 私有注入的 Recorder），互不干扰。

**Q18. AutoLayout 为什么放子进程？**
GUI/layout 代码可能污染或挂掉主 backend JVM，`AutoLayoutWorkerMain` 独立子进程跑，自适应超时回退 lightweight，坐标有限值校验规避 `JSON non-finite`。

**Q19. 没做 git 管理吃了什么亏？**
整轮没 commit，回退 MEGA 时不能 `git reset`，只能逐文件外科手术删。教训：每阶段完成立即 commit。（体现你会复盘流程，不只复盘代码。）

### D. 判断力 / 取舍（高级岗最看重）

**Q20. 为什么不直接用 LangGraph / AutoGen？**
"这是嵌在 Ptolemy II（Java）里的领域系统，需要贴 MoML/Manager 的执行语义、内核零侵入、同一 Tool API 服务 LLM/HTTP/UI 四方，用现成 Python 框架反而要架桥。但架构上借鉴了它们：`AgentTrace` ≈ LangGraph 的 state+checkpoint 思想，多角色 ≈ AutoGen group。生产选型我会评估 LangGraph 的 checkpointer 做持久化。"

**Q21. 如果重做，最想改什么？**
(1) 一开始就做 eval 集而不是靠"实测感觉"；(2) 先榨干单 LLM 再上多 agent；(3) 记忆做成跨会话（现在只有 session 内 classFailures）；(4) reviewer/builder 中间思考也流式。

**Q22. 怎么证明五层防线有效？（诚实）**
"目前是定性——错误从死胡同变成可行动、反振荡防住烧 token。我**没有**量化 benchmark，这是我想补的（拿 3 个 demo + 变体做一次成功率 A/B）。"（别编数字。）

### E. 快问快答（各一句话）

- **Phase2 refactor 跳过条件**：顶层 atom < `AGENT_REFACTOR_THRESHOLD`(默认4)。
- **NullLLMClient 作用**：无 key 离线兜底 / 测试。
- **reviewer 为什么无 tool 只出 action**：防它乱改，白名单 + 硬上限 ≤8。
- **ModelContext 喂给 LLM 的是什么**：紧凑模型文本视图，不是完整 MoML。
- **SignalCollector**：跑完注入 Recorder 收数据、NaN→null。
- **GraphSerializer**：CompositeActor → 前端 JSON。
- **stall 阈值为什么是 8**：容忍瞬时 connect/parse 失败。
- **工具 scope 解析**：`ToolScopeResolver` 统一 nested composite scope。

---

## 6. Ptolemy II（项目2）追问与迁移话术

**诚实定位**：你在自己 fork 的 ptII 里写了 `org/ptolemy/agent` 整个包 —— "学习框架"和"造 Agent"是同一个仓库，深度可信。面试官会问"这框架跟 Agent 有什么关系"，主动架桥：

- **Actor/Director 解耦 → Tool 执行 / 编排调度解耦**：Ptolemy 里 Actor 封装计算、Director 是可插拔调度（MoC）；我把工具执行逻辑和路由/编排（`AgentRouter`+`AgentPipeline`）分开，思路同构。
- **MoC 可插拔 → 路由策略可插拔**：CHAT/SINGLE/PIPELINE 就像不同 Director。
- **prefire→fire→postfire 三段式 → 工具 preflight→dispatch→trace 提交**：横切关注点（校验/幂等/防振荡）在阶段间统一施加，不改工具本身。
- **编译期类型解析 → plan 静态校验**：`PlanValidator` 在动手前查 className 能否解析、wire 是否引用已声明 actor，把错误挡在"执行前"而非运行时——和 Ptolemy 的 TypeResolver 在设计期拦截类型冲突同哲学。
- **确定性调度（SDF 编译期算执行次数）→ 确定性执行器**：`PlanExecutor` 零 token 机械执行，也是"能静态确定的就别留给运行时/LLM"。

**一句话总结**："Ptolemy II 教会我'把计算和调度分开、把能静态确定的提前确定'，这直接塑造了我 Agent 平台的分层和确定性执行器设计。"

---

## 7. Agent 记忆系统（JD 第2条 重点补强）

### 7.1 理论骨架（能徒手画出分层图）

- **短期 / 工作记忆**：对话窗口、scratchpad、任务状态。易失，受 context window 限制。
- **长期记忆**三类：
  - **语义记忆 Semantic**：事实/知识/用户画像 → 向量库 + 图。
  - **情景记忆 Episodic**：发生过的事件/交互轨迹 → DB。
  - **过程记忆 Procedural**：学到的技能/工具用法/成功模板 → 模板库。

### 7.2 生命周期四动作（= JD 原话）

| 动作 | 关键问题 | 主流手段 |
|---|---|---|
| **写入** | 什么值得记？粒度/结构？ | 重要性打分 + 抽取结构化事实（不存原始对话） |
| **召回** | 检索最相关且新鲜的记忆 | `score = α·相关性 + β·新近性(时间衰减) + γ·重要性` → rerank |
| **压缩** | 塞不下时怎么缩 | 递归/层次摘要 + MemGPT 分页换出 + 结构化替代原文 |
| **更新/遗忘** | 新旧冲突？何时删？ | Mem0 四操作 ADD/UPDATE/DELETE/NOOP + 冲突消解 |

### 7.3 四个代表系统（一句话定位 + 可迁移点）

- **MemGPT / Letta**：OS 虚拟内存思想，主内存 ↔ 外部存储分页，记忆即 tool 调用。→ 记忆管理本身也是工具调用，Agent 自主读写（和 B 平台"工具调用上下文持久化"同范式）。
- **Generative Agents（斯坦福小镇）**：召回三因子 = 相关性 + 新近性 + 重要性 + Reflection 反思归纳。→ 生产级召回不能只用向量相似度。
- **Mem0**：抽取结构化事实 + ADD/UPDATE/DELETE/NOOP 增量更新与冲突消解。→ 记忆更新不是简单 append。
- **A-Mem**：Zettelkasten 式记忆互联、动态演化、多跳召回。→ 记忆是网络/图，可顺关联扩展。

### 7.4 四大技术难题 → 解法（JD 原文点名，秒答）

| 难题 | 成因 | 解法组合 |
|---|---|---|
| 上下文损耗（lost in middle） | 中间位置信息利用率低 | rerank 放首尾 + 只注入相关片段 + 关键信息前置 |
| 信息遗忘 | 窗口滑出 / 跨会话无持久 | 长期持久化 + 召回重注入 + 结构化 state 替代对话历史 |
| 上下文冗余 | 重复/无关塞太多 | 去重 + 压缩(LLMLingua/摘要) + 按需检索 + 阈值过滤 top-k |
| 任务一致性 | 长任务目标漂移 / 多 agent 不一致 | 外置任务态 + 每轮 goal 重注入 + reviewer 校验 + 冲突消解 |

### 7.5 桥接话术（把"没做过记忆系统"讲成"做过任务态记忆基础版"）

| B 平台已有 | 记忆系统术语 | 面试怎么说 |
|---|---|---|
| 工具调用上下文与结果持久化 | 过程记忆/情景记忆持久化 | 记录 Agent 做过什么、结果如何，支撑复现 |
| 任务状态机 / `ModelContext` | 工作记忆结构化外置 | 把任务态从对话历史剥离，抗遗忘和漂移 |
| `AgentTrace` 全链路追踪/回放 | 情景记忆 + 记忆可观测性 | trace/replay 也是记忆评测底座 |
| 角色间结构化上下文传递 | 短期记忆结构化压缩 | 不传全量对话，传结构化上下文 |
| `classFailures` 失败画像 | 任务级失败记忆雏形 | session 内已有，扩展方向是跨会话 |
| reviewer 角色 | 一致性校验 | 对齐输出，对应记忆/任务一致性治理 |

**自我陈述模板（背）**："在 B 平台我做的是**任务态记忆**这一层：会话隔离 + `ModelContext` + 工具调用结果持久化 + `classFailures` 失败画像，本质是把工作记忆和过程记忆结构化外置，解决长任务里的信息遗忘和目标漂移。我**还没做**跨会话语义长期记忆和自动召回/冲突消解——如果做，会引入 Mem0 式事实抽取 + ADD/UPDATE/DELETE、Generative Agents 式相关性+新近性+重要性召回、MemGPT 式分页压缩。这正是我想在贵司深入的方向。"

### 7.6 杀手锏判断题

**"窗口够大（百万 token）还要记忆吗？" → 要**：①成本随 token 线性涨 ②lost-in-middle 长上下文利用率降 ③跨会话仍需持久化 ④全塞引噪声降准确率。记忆 = 按需注入最小相关上下文，是效果 + 成本联合优化。

---

## 8. 两篇论文：追问与到 Agent 的迁移

### ICASSP 2025 · CCF-B · 一作 —《Dual-level AMR Injection for Prompt-based Event Argument Extraction》

- **电梯陈述（背）**："文档级事件论元抽取里，论元和触发词常跨句、距离远。我把 AMR（抽象语义表示，把句子解析成谓词-论元语义图的结构）在两个层次注入 prompt-based 抽取模型，用显式语义结构对抗长距离信息损耗，效果在文档级数据集上提升。"
- **预判追问**：注入哪两层？为什么 AMR 比原文好？baseline 是什么？
- **迁移到 JD**：这是**结构化知识注入对抗上下文损耗** —— 和 Agent 上下文工程"注入结构化事实对抗遗忘"同源；对应 `CapabilityProbe` 注入结构化 recipe、planner 输出结构化 JSON plan。

### CIKM 2025 · CCF-B · 一作 —《Hyperspherical Dynamic Multi-Prototype with Argument Dependencies and Role Consistency》

- **电梯陈述（背）**："同一角色的论元语义分布是多模态的，单原型不够，我用超球面上的动态多原型表示每个角色，并联合建模论元间依赖与角色一致性约束。"
- **预判追问**：为什么用超球面？多原型解决什么？怎么联合建模依赖与一致性？
- **迁移到 JD**：**一致性约束建模** → 对应多 agent 输出一致性、记忆冲突消解、reviewer 一致性校验。

**统一话术**："我的学术工作核心是'用结构和约束提升抽取的准确与一致'，落到 Agent 就是'用结构化上下文和一致性校验提升任务完成率与稳定性'——这也是我 B 平台在做的。"

---

## 9. 需要补强的不足 + 具体补法

1. **记忆系统（JD 第2条，最该补）**：理论见第 7 节。桥接点用 `classFailures` → 扩展到跨会话过程/语义记忆。
2. **评测体系 + 真实指标（加分项2，把最大短板变亮点）**：现在就搭最小 eval——拿 RC/PID/Repair 3 个 demo + 变体 prompt，跑"开/关某层防线"A/B，量出：一次成功率、平均 tool 调用数、无效重试次数、builder 跳过率、平均 token。有了数字，Q22 从"定性"升级"定量"。
3. **RAG（加分项2/JD3）**：口径降级"词法检索增强规划"；补一段升级设计（actor 描述向量化 + 混合检索 BM25+dense + rerank），证明懂完整 RAG。
4. **框架对比（加分项4）**：LangGraph（StateGraph+checkpointer+条件边）/ AutoGen（对话式 group）/ LlamaIndex（RAG 数据框架）三者定位，并把 `AgentTrace`/`ToolRegistry`/`AgentPipeline` 一一对标。
5. **微调/RL/多模态（加分项5）**：诚实"没实操过，了解 SFT/DPO/PPO 和多模态 agent 大致范式"，不硬凹。

---

## 10. 诚实边界清单（能说 / 不能说）

- **能说（有代码）**：五层防线、确定性执行器、反振荡、原子批量、四阶段、SSE 流式、内核零侵入、MEGA 回退复盘、`classFailures` 失败记忆雏形、`ToolRegistry` 四路复用。
- **不能说 / 要降级**：
  - 具体百分比指标（没测过就别报）。
  - "向量 RAG"（实为词法检索）。
  - "分布式事务"（实为单进程 MoML group）。
  - "mega 是现役功能"（已删）。
  - 跨会话长期记忆（没做）。
  - 微调/RL/多模态实操（没做）。

---

## 11. 面试前动作清单

- [ ] 手画 `AgentPipeline` 五工序图，标注每个 Phase 的类名、LLM/确定性、工具子集。
- [ ] 背熟 MEGA 回退故事（3 个失败原因 + 1 句教训）—— 判断力名片。
- [ ] 过一遍第 5 节 30 问，尤其 A、B 两组。
- [ ]（强烈建议）搭 eval 拿真实数字，把 Q22 从"定性"变"定量"。
- [ ] 记忆系统架构图（附录 B）+ 两篇论文电梯陈述各背一遍。
- [ ] 准备成长意愿："我在编排和工具可靠性上做得深，记忆系统和评测体系是我想在贵司补强的方向。"

---

## 附录 A：记忆系统一页速记

**分类树**
```
记忆
├─ 短期/工作记忆：上下文窗口、scratchpad、任务状态（易失）
└─ 长期记忆
   ├─ 语义 Semantic：事实/知识/画像 → 向量库+图
   ├─ 情景 Episodic：事件/轨迹 → DB
   └─ 过程 Procedural：技能/工具用法/模板 → 模板库
```

**生命周期四动作**：写入(重要性打分+抽取事实) → 召回(相关+新近+重要，再rerank) → 压缩(摘要+分页+结构化替代) → 更新(ADD/UPDATE/DELETE/NOOP+冲突消解)

**四大难题**：lost-in-middle(rerank放首尾) / 遗忘(持久化+重注入) / 冗余(去重+压缩+按需) / 一致性(外置任务态+goal重注入+reviewer)

**四系统**：MemGPT(虚拟内存分页) · Generative Agents(三因子召回) · Mem0(四操作冲突消解) · A-Mem(记忆互联)

**判断题**："窗口够大还要记忆吗？"→ 要：成本/lost-in-middle/跨会话/噪声 四理由。

---

## 附录 B：B 平台 + 记忆系统落地设计（架构图 + 伪代码）

被追问"你会怎么在建模平台里加记忆"时照着讲。

### 架构图（在原四层 Harness 上叠一层 Memory）

```
┌───────────────────────────────────────────────────────────────┐
│                     Multi-Agent Pipeline                          │
│         planner → builder → refactor → reviewer                   │
└───────┬───────────────────────────────────────────────┬─────────┘
        │ 召回(recall) 注入相关记忆                          │ 写入(write) 轨迹/事实
        ▼                                                   ▼
┌───────────────────────────────────────────────────────────────┐
│                    Memory Manager (新增层)                        │
│   Recall(相关+新近+重要) · Compress(摘要/分页) ·                  │
│   Update(ADD/UPD/DEL) · Importance Scorer                         │
└───────┬───────────────┬────────────────┬──────────────┬─────────┘
        ▼               ▼                ▼              ▼
  语义记忆(向量库+图)  情景记忆(轨迹DB)   过程记忆(模板库)   工作记忆(状态机)
  领域实体/schema     trace/replay(已有) 高频工具序列      会话隔离(已有)
  └── 复用 didYouMean/实体校验做写入&召回时的实体规整 ──┘
```

一句话：记忆层不侵入 Harness，作为 Session 与 Tool Registry 之间的中间件；Agent 通过 memory tools 主动读写（MemGPT 范式），原有状态机/持久化/实体校验直接复用为工作记忆和写入规整。

### 核心伪代码

**1. 写入 + 冲突消解（Mem0 范式）**
```python
def write_memory(raw_events, task_id):
    facts = llm_extract_facts(raw_events)            # 抽取结构化事实，非原样存
    for fact in facts:
        fact.entities = entity_validator.normalize(fact.entities)  # 复用 didYouMean/实体校验
        fact.importance = llm_score_importance(fact)               # 1-10
        similar = vector_store.search(fact.embedding, top_k=3)
        op = decide_op(fact, similar)   # ADD / UPDATE / DELETE / NOOP
        apply(op, fact, similar)        # UPDATE 冲突消解：新覆盖旧 or LLM 裁决
```

**2. 召回（Generative Agents 三因子 + rerank）**
```python
def recall(query, task_id, k=5):
    cands = vector_store.search(embed(query), top_k=30, filter={"task_id": task_id})
    now = time.time()
    for m in cands:
        relevance  = cosine(embed(query), m.embedding)
        recency    = exp(-DECAY * (now - m.last_access))
        importance = m.importance / 10
        m.score    = A*relevance + B*recency + C*importance
    top = rerank(sorted(cands, key=score, reverse=True)[:k])  # 缓解 lost-in-middle
    for m in top: m.last_access, m.access_count = now, m.access_count + 1
    return top
```

**3. 压缩（超预算时触发，MemGPT 分页 + 递归摘要 + goal 重注入）**
```python
def build_context(role, recalled, working_state, budget_tokens):
    ctx  = [goal_reinjection(task_id)]       # 每轮重注入目标 → 防漂移
    ctx += [working_state.summary()]         # 工作记忆用结构化 state
    ctx += dedup(recalled)                   # 去冗余
    while count_tokens(ctx) > budget_tokens:
        oldest = pop_lowest_priority(ctx)
        archive.write(recursive_summarize(oldest))  # 冷记忆摘要后换出
    return ctx
```

**4. Pipeline 集成（每角色前召回、后写入）**
```python
def run_agent(role, task):
    recalled = memory.recall(task.query, task.id)
    ctx      = build_context(role, recalled, task.state, budget=role.budget)
    result   = role.execute(ctx, tools=tool_registry)   # 原有 Harness
    memory.write_memory(result.trace, task.id)          # 轨迹→过程/情景记忆
    if role == "reviewer":
        memory.check_consistency(task.id)               # 一致性校验+冲突消解
    return result
```

### 落地设计如何命中 JD

- **JD 第2条**：召回/压缩/更新四动作全覆盖，四大难题各有对应解法。
- **JD 第4条**：过程记忆库 = 可复用工具序列模板（"记忆模板"）；Memory Manager 独立中间件可跨业务线复用。
- **JD 第3条**：goal 重注入 + 去冗余 + rerank 提升完成率/准确率/稳定性。
- **复用已有资产**：状态机→工作记忆、trace/replay→情景记忆+评测、didYouMean/实体校验→写入规整。

### 评测叙事（被问"怎么证明有效"）

用已有 trace/replay 做固定回归集，对比"加记忆 vs 不加"：端到端看任务完成率/准确率，组件级看召回命中率/MRR、注入 token 量（成本）、有无召回矛盾事实（一致性）。先做 A/B 再灰度到业务线。
