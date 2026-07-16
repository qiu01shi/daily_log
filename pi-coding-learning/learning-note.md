# Pi 编码 Agent 学习笔记

> 项目路径：`C:\projects\pi`
> 学习阶段：[30 分钟快速理解] —— 打通「pi 输入一句话」的控制流
> 对应代码版本：`0.80.3`

---

## 1. 项目概览

`pi` 是一个 **AI 编码 Agent 的 monorepo**，核心产品是一个可自我扩展的交互式编码 CLI（类似 Claude Code / Codex CLI）。采用 npm workspaces，拆成多个可独立发布的包：

| 包 | 作用 |
|----|------|
| `@earendil-works/pi-coding-agent` | 面向用户的编码 Agent CLI（就是 `pi` 命令） |
| `@earendil-works/pi-agent-core` | 通用 Agent 运行时（agent loop、工具调用、状态/会话管理） |
| `@earendil-works/pi-ai` | 统一多 provider 的 LLM API（OpenAI / Anthropic / Google / Bedrock…） |
| `@earendil-works/pi-tui` | 终端 UI 库（差分渲染） |
| `@earendil-works/pi-orchestrator` | 实验性：编排/管理多个 pi 实例 |

依赖方向：`coding-agent` → `agent-core` → `ai`；`coding-agent` 还依赖 `tui`。

技术栈：TypeScript（ESM，相对导入用 `.ts` 扩展名）、Node ≥ 22.19、tsgo 编译、Biome 规范、Vitest 测试。

---

## 2. 启动方式

安装后运行：

```bash
pi                 # 在项目目录里启动交互模式
```

从源码运行（开发）：

```bash
./pi-test.sh       # 从源码启动 pi，可在任意目录执行
```

四种运行模式（由 `main.ts` 的 `resolveAppMode()` 决定）：

- `interactive`：TUI 交互（默认，stdin 是 TTY 时）
- `print`：一次性输出（`--print` 或有管道输入）
- `json`：结构化事件流（`--mode json`）
- `rpc`：stdin/stdout JSONL 协议（`--mode rpc`，orchestrator 用它控制子进程）

---

## 3. 目录结构（聚焦本次关注的部分）

```
packages/
  coding-agent/          # CLI + 交互模式（体量最大）
    src/
      cli.ts             # [核心入口] pi 命令的真正起点
      main.ts            # [核心入口] 参数解析 + 装配 + 模式分派
      config.ts          # [配置] 路径 / APP_NAME / agentDir
      core/
        sdk.ts           # createAgentSession() 装配
        agent-session.ts # [核心业务] 所有模式共用的巨型编排类(3000+行)
        tools/           # [核心业务] 内置工具 read/bash/edit/write/grep/find/ls
        session-manager.ts   # [数据层] 会话 JSONL 落盘、fork、continue
        messages.ts      # [数据层] convertToLlm：内部消息 <-> LLM 消息
        settings-manager.ts / model-registry.ts   # [配置]
      modes/
        interactive/interactive-mode.ts  # [核心入口] 事件 -> TUI
        print-mode.ts / rpc/rpc-mode.ts
  agent/                 # Agent 运行时
    src/
      agent-loop.ts      # [核心业务] Agent 主循环（本次重点）
      agent.ts           # Agent 状态封装（队列、abort）
      types.ts           # AgentLoopConfig / AgentEvent / StreamFn 等契约
      harness/           # AgentHarness 编排层 + session + compaction
  ai/                    # 统一 LLM API
    src/
      stream.ts          # [核心业务] stream / streamSimple 统一入口
      api/               # 各 provider 的 API 实现 + .lazy.ts 懒加载
      types.ts           # [数据层] Message / Context / AssistantMessage / Model
      auth/              # 凭据 / OAuth
```

---

## 4. 核心流程：输入一句话之后发生了什么

### 三个入口文件逐个拆解

#### (1) `cli.ts` —— 进程引导（约 20 行）

只做「开机准备」，然后交棒给 `main`：

```
process.title = APP_NAME
process.env.PI_CODING_AGENT = "true"
process.emitWarning = noop           # 屏蔽 Node 警告
configureHttpDispatcher()            # 配置 undici 全局 dispatcher（关掉超时，
                                     # 防止本地 LLM 长时间 buffer 时 SSE 流被中断）
main(process.argv.slice(2))          # 把命令行参数丢给 main
```

要点：`cli.ts` 不含业务逻辑，纯粹是「设置进程环境 + 调 main」。

#### (2) `main.ts` —— 装配与分派（约 850 行，主函数 `main()`）

这是整个 CLI 的「大脑」。主线（省略分支）：

```
main(args):
  1. 处理 --offline / Windows 自更新清理
  2. 建 bootstrap SettingsManager，应用 http 代理设置
  3. 拦截 package / config 子命令（pi update、pi config ... 直接返回）
  4. parseArgs(args)                       # 解析所有 flag
  5. 处理 --version / --export 等一次性命令
  6. resolveAppMode()                       # 决定 interactive/print/json/rpc
  7. runMigrations()                        # 迁移旧配置
  8. createSessionManager()                 # [数据层] 新建 / 打开 / fork / 续接会话
  9. createAgentSessionRuntime(createRuntime)
       └─ createAgentSessionServices()      # 建 settings/modelRegistry/resourceLoader
       └─ buildSessionOptions()             # 解析模型、thinking level、工具白名单
       └─ createAgentSessionFromServices()  # 真正造出 AgentSession（含模型/工具/扩展）
  10. 读取管道 stdin、准备 initialMessage/initialImages、initTheme
  11. 按 appMode 分派：
        rpc         -> runRpcMode(runtime)
        interactive -> new InteractiveMode(runtime).run()
        print/json  -> runPrintMode(runtime, ...)
```

关键理解：**`main.ts` 只负责「把一切组装好」并选一个模式驱动器**。真正的「对话循环」在 `agent-core` 里，由模式驱动器（如 `InteractiveMode` / `runPrintMode`）通过 `AgentSession` 间接调用。

#### (3) `agent-loop.ts` —— Agent 主循环（`packages/agent/src/agent-loop.ts`）

这是「一次对话」的心脏。对外暴露两个入口：

- `agentLoop(prompts, context, config, signal, streamFn)`：带新用户消息启动一轮
- `agentLoopContinue(context, ...)`：不加新消息，从当前上下文继续（用于重试）

两者都返回一个 `EventStream<AgentEvent, AgentMessage[]>`，内部委托给 `runLoop()`。

`runLoop()` 的双层循环（最重要）：

```
外层 while(true)         # 处理「agent 本要停下，但又来了 follow-up 消息」
  内层 while(有工具调用 || 有待注入消息)
    - 注入 pendingMessages（用户在等待时插话的 steering 消息）
    - streamAssistantResponse()   # ★ 调 LLM，流式产出 assistant 消息
        · transformContext()      # 可选：改写上下文
        · convertToLlm()          # AgentMessage[] -> LLM Message[]（唯一转换点）
        · streamSimple(model, ctx, opts)   # 进入 pi-ai
        · 边收 start/text_delta/thinking/toolcall 事件边 emit message_update
    - 若 stopReason 是 error/aborted -> 收尾 agent_end 返回
    - 从 assistant 消息里过滤出 toolCall
    - 有工具调用 -> executeToolCalls()   # 并行或顺序执行
        · prepareToolCall（校验参数 + beforeToolCall 钩子，可 block）
        · tool.execute()（支持流式 partialResult）
        · afterToolCall 钩子（可改写结果）
        · 把 ToolResultMessage 回填进 context.messages 和 newMessages
    - hasMoreToolCalls = !terminate  # 有工具结果就再问一轮 LLM
    - emit turn_end
    - prepareNextTurn()   # save point：可换模型/thinking level/上下文
    - shouldStopAfterTurn() -> 提前结束
  内层结束后：getFollowUpMessages()，有则设为 pending 继续外层
  没有 -> break
emit agent_end
```

一句话总结：**LLM 回复 → 有没有工具调用？有就执行工具并把结果喂回去再问一轮，没有就结束**。这是所有编码 Agent 的通用骨架。

### 端到端控制流（文字时序）

```
用户输入 "帮我改个 bug"
  -> cli.ts (设置进程环境) 
  -> main.ts (parseArgs -> 建 session -> 建 AgentSession runtime -> 选 interactive 模式)
  -> InteractiveMode.run() 接收输入，调用 AgentSession.prompt(...)
  -> AgentSession 组织 context/tools/config，调用 agentLoop()
  -> agent-loop.runLoop():
        streamAssistantResponse -> pi-ai streamSimple -> provider(如 Anthropic) 返回流
        assistant 说要 read 文件 -> executeToolCalls 执行 read 工具 -> 结果回填
        再问 LLM -> assistant 说要 edit -> 执行 edit -> 回填
        再问 LLM -> assistant 给出最终回答，无工具调用 -> agent_end
  -> 循环期间 emit 的事件被 InteractiveMode 渲染成 TUI；消息由 SessionManager 落盘 JSONL
```

---

## 5. 关键概念

- **AgentMessage vs LLM Message**：内部统一用 `AgentMessage`，只有在调 LLM 那一刻用 `convertToLlm()` 转成 provider 认识的 `Message[]`。转换只发生在 `streamAssistantResponse` 里一次。
- **EventStream / AgentEvent**：loop 通过事件（`agent_start` / `turn_start` / `message_start|update|end` / `tool_execution_*` / `turn_end` / `agent_end`）对外广播，UI 层订阅这些事件渲染。
- **Turn（一轮）**：一次「问 LLM + 执行其工具调用」为一个 turn。有工具调用就会继续下一轮，直到 LLM 不再调用工具。
- **Steering vs Follow-up 消息**：
  - steering：用户在 agent 忙时插话，在下一次 assistant 回复前注入（内层循环）。
  - follow-up：agent 本要停下时，队列里还有消息则继续（外层循环）。
- **工具执行钩子**：`beforeToolCall`（可拦截/阻止）、`afterToolCall`（可改写结果）、`terminate`（工具可要求结束整轮）。
- **并行 vs 顺序执行**：默认并行；若配置 sequential 或某工具标了 `executionMode: "sequential"` 则顺序执行。
- **save point / prepareNextTurn**：每轮结束后可安全地换模型、thinking level、上下文，不影响正在进行的请求。
- **AppMode**：interactive / print / json / rpc，由 `resolveAppMode()` 根据参数和 TTY 决定。
- **AgentSession**：coding-agent 里所有模式共用的编排类，封装 agent 状态、事件订阅+自动落盘、模型管理、compaction、bash、会话切换/分支。

---

## 6. 常用命令

```bash
# 开发
npm install --ignore-scripts   # 安装依赖
npm run build                  # 构建 tui/ai/agent/coding-agent/orchestrator
npm run check                  # Biome + 多项校验 + tsgo 类型检查
./test.sh                      # 跑非 LLM 测试（无需 API key）
./pi-test.sh                   # 从源码运行 pi

# 运行 pi
pi                             # 交互模式
pi --print "问题"              # 一次性输出
pi --mode rpc                  # RPC 模式
pi --model <provider>/<pattern>  # 指定模型
```

注意（来自 AGENTS.md）：默认不要跑 `npm run dev/build/test`；本机 shell 是 PowerShell，不支持 `&&` 串联。

---

## 7. 我已理解的内容

- [x] 项目是「可自扩展的编码 Agent CLI」+ 支撑它的 ai / agent-core / tui 等包。
- [x] `cli.ts` 只做进程引导（标题、环境变量、http dispatcher），然后调 `main`。
- [x] `main.ts` 负责参数解析 → 建 session → 装配 AgentSession runtime → 按 AppMode 选驱动器。
- [x] 真正的对话循环在 `agent-loop.ts` 的 `runLoop()`，是「问 LLM → 执行工具 → 回填 → 再问」的双层循环。
- [x] 内部消息与 LLM 消息通过 `convertToLlm()` 在调用边界转换。
- [x] loop 通过 `AgentEvent` 事件流对外广播，UI 订阅渲染，SessionManager 落盘。
- [x] steering / follow-up 两类插入消息分别对应内层/外层循环。
- [x] 五层调用链：`AgentSession.prompt` → `_runAgentPrompt` → `Agent.prompt` → `runPromptMessages` → `runAgentLoop`。
- [x] `AgentSession` 做预处理（扩展/skill/模板/鉴权/compaction），`Agent` 管状态和生命周期，`runLoop` 才是真正的循环。
- [x] `createContextSnapshot()` 用 `.slice()` 拍快照，循环改副本不污染原始 state。
- [x] 常见 TypeScript 语法（见附录）。

---

## 8. 待继续研究的内容

- [x] `AgentSession.prompt()` 如何把输入接到 `agentLoop`（见「追踪记录 A」）。
- [ ] `main.ts` 里 `createAgentSessionServices` / `createAgentSessionFromServices` 的具体装配过程。
- [ ] `pi-ai` 的 `streamSimple` -> `api/*.lazy.ts` 懒加载 -> 具体 provider（如 `anthropic-messages.ts`）如何把 SSE 转成标准事件。
- [ ] 内置工具（`core/tools/read.ts`、`bash.ts`）的 schema + execute 实现范式。
- [ ] 会话数据模型：JSONL 条目格式、树/分支结构（`session-format.md`、`harness/session/`）。
- [ ] AgentHarness 编排层与 compaction（上下文压缩）机制。
- [ ] 交互模式 TUI 如何用差分渲染把事件画到终端。
- [ ] orchestrator 如何用 RPC 模式管理多个 pi 实例。

---

---

## 追踪记录 A：`prompt()` 如何走到 `agentLoop()`（2026-07-02）

从用户输入到主循环，一共 5 层。核心分工：**`AgentSession`（coding-agent）= 加工厂，做编码 Agent 特有的预处理；`Agent`（agent-core）= 发动机，管状态和生命周期；`runLoop` = 曲轴，真正一圈圈转。**

```
AgentSession.prompt()        core/agent-session.ts:1026  预处理
  └ _runAgentPrompt()        agent-session.ts:975        调底层 + 重试/续跑
      └ Agent.prompt()       agent/src/agent.ts:337      通用运行时入口
          └ runPromptMessages()  agent.ts:396
              └ runAgentLoop()   agent-loop.ts            主循环入口
                  └ runLoop()                             双层循环
```

### 各层职责

1. `AgentSession.prompt(text, options)`：斜杠命令 → 扩展 input 事件 → 展开 skill/模板 → 若正在 streaming 则 steer/followUp 排队 → 校验模型+鉴权 → 必要时 compaction → 构造 `{role:"user", content, timestamp}` 消息 → `before_agent_start` 事件（扩展可加消息/改系统提示）→ `await this._runAgentPrompt(messages)`。
2. `_runAgentPrompt()`：`await this.agent.prompt(messages)`，再用 `while (await this._handlePostAgentRun()) await this.agent.continue()` 处理重试/续跑，`finally` 收尾。
3. `Agent.prompt()`：检查 `activeRun` 是否忙 → `normalizePromptInput` 统一成 `AgentMessage[]` → `runPromptMessages`。
4. `runPromptMessages()`：`runWithLifecycle` 里调 `runAgentLoop(messages, 快照, config, 事件回调, signal, streamFn)`。
5. 三个关键参数：
   - `createContextSnapshot()`：用 `.slice()` 拷贝消息/工具/系统提示，循环改副本，不污染原始 state；
   - `createLoopConfig()`：打包 model、reasoning、beforeToolCall/afterToolCall、prepareNextTurn 等；
   - `(event) => this.processEvents(event)`：事件回调，循环 emit 的事件经此转发给 TUI 渲染 + SessionManager 落盘。

---

## 附录：TypeScript 语法速记（零基础）

阅读本项目时反复遇到的语法：

- `名字: 类型` —— **类型标注**，如 `text: string`。TS 相比 JS 就是多了类型。
- `参数?:` —— 参数**可选**，可以不传，如 `options?: PromptOptions`。
- `A | B` —— **联合类型**，"要么 A 要么 B"，如 `string | AgentMessage[]`。
- `类型[]` —— **数组**，如 `AgentMessage[]` 是消息数组。
- `?.` —— **可选链**，对象存在才访问/调用，如 `preflightResult?.(true)`。
- `??` —— **空值合并**，左边是 null/undefined 才用右边，如 `x ?? true`。
- `async` / `await` / `Promise<T>` —— 异步函数 / 等待完成 / "将来返回 T 的结果"。`Promise<void>` = 不返回值。
- `<T>` 尖括号 —— **泛型**，"装在盒子里的类型"，如 `EventStream<AgentEvent, AgentMessage[]>`。
- `private` —— 类内部成员，外部不能访问（编译期检查）。
- `this` —— 当前对象；`this.agent` 是它的属性。
- `(x) => f(x)` —— **箭头函数**，常作回调传入。
- `函数重载` —— 同名函数声明多种调用形状（如 `Agent.prompt` 的三行声明，最后一行才是实现）。
- `.slice()` —— 复制数组（做快照，避免改乱原数组）。
- `{ 字段?: 类型 } = {}` —— 对象形状类型 + 默认空对象。

---

*下一步计划：继续 [半天掌握主流程]，追 `runAgentLoop` 里的 `streamSimple` → `pi-ai` 的 `api/*.lazy.ts` 懒加载 → 具体 provider（如 `anthropic-messages.ts`）如何把 SSE 流转成标准事件。*
