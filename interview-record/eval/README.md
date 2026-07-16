# 自动建模 Agent 最小评测（eval）

目的：把面试里唯一的硬短板——"没有量化指标"——补掉。用一个零依赖的 PowerShell 脚本，
对你的 Ptolemy 建模 Agent 后端跑一组 canonical 任务，产出**真实、可复算**的对照数字。

> 定位要诚实：这是一个**小规模内部 smoke-eval**，不是发表级 benchmark。因为样本小 + LLM 有随机性，
> 结论只能当**方向性证据**。面试就这么说，反而显得你懂评测边界。

---

## 一、前置条件

1. 后端已编译并启动（默认 `http://localhost:7777`）：
   ```powershell
   .\agent-output\start-agent-flash.ps1 -Dev
   # 或只起后端后用 -CheckOnly 验证 /agent/status
   ```
2. **配好 LLM**（否则会降级到 NullLLMClient，全跑失败）：设好 `DEEPSEEK_API_KEY`（或 `OPENAI_API_KEY`）。
   脚本启动时会打印 `strategy` 和 smoke probe，probe 非 ok 会告警。

## 二、运行

```powershell
cd C:\projects\daily_log\interview-record\eval

# 默认：pipeline vs single 对照，每任务重复 3 次
.\Run-AgentEval.ps1

# 只测 pipeline，重复 5 次
.\Run-AgentEval.ps1 -Mode pipeline -Repeat 5

# 指向别的后端
.\Run-AgentEval.ps1 -BaseUrl http://localhost:7777 -Mode both -Repeat 3
```

输出在 `results/`：
- `runs-<时间>.csv`：逐次明细（可再自己算统计）。
- `summary-<时间>.md`：模式对照汇总表（直接可截图/贴进面试材料）。

## 三、能测什么（都来自真实接口）

| 指标 | 含义 | 来源 |
|---|---|---|
| **run_ok 成功率** | chat 完后单独 `POST /run`，模型真能跑起来 | 最硬的客观任务成功信号 |
| llm_success 率 | `trace.success`，LLM 正常收尾（≠模型能跑） | trace |
| builder 跳过率 | 检测到 "Phase 1 … skip"，即确定性执行器把 builder 整轮跳过 | trace 文本（启发式） |
| 平均工具调用数 | kind==tool_call 步数 | trace |
| 平均失败调用数 | tool_result 里 ok==false 的步数（无效调用） | trace |
| 平均反振荡命中 | tool_result 带 antiThrash 教练提示的次数 | trace |
| 平均幂等 noop | tool_result 带 noop==true 的次数 | trace |
| 平均时延 ms | 一次 chat 墙钟耗时 | 客户端测 |

## 四、测不了什么（诚实边界，别踩）

- **token 用量**：`AgentTrace` 里没有 token 字段，接口拿不到。要测得改后端把 usage 塞进 trace。
- **逐层防线开关 A/B**（PortHints / 反振荡 / CapabilityProbe / PlanValidator）：**没有环境变量，硬编码常开**。
  想 A/B 这些，得在代码里加 feature flag（每个约几行）。本脚本**做不到**这种对照，别声称做过。
- 能做的 A/B 只有：
  - **pipeline vs single**（逐请求切 `mode`，本脚本 `-Mode both` 就是）——最能证明"pipeline + 确定性执行器"价值。
  - reviewer / replan 开关：需重启后端并设 `AGENT_REVIEWER_ENABLED` / `AGENT_REPLAN_ON_FAILURE`，再各跑一轮对比。

## 五、怎么在面试里讲这些数字（诚实口径）

- 对的说法：**"我在一组 N 个 canonical 建模任务上做了 pipeline vs single 的对照 smoke-eval：pipeline 模式的可运行模型率 X/N，单循环 Y/N；pipeline 平均失败调用数低 Z，且 W% 的任务 builder 被确定性执行器整轮跳过（零 token）。样本小、LLM 有随机性，是方向性结论。"**
- 别说：❌ 具体到小数点的"准确率提升 37.2%"（样本不够）；❌ "逐层消融实验"（没有 flag，做不了）；❌ token 降低多少（测不了）。
- 加分收尾：**"要做成严格 benchmark，我会：扩任务集、给每层防线加 feature flag 做消融、把 token usage 落进 trace、固定 temperature 提升可复现性。"** —— 体现你知道怎么把它做正规。

## 六、文件

- `tasks.json`：6 个任务（sine/rc/fir/ode/sdf-feedback/pid），覆盖 CapabilityProbe 已知领域。可自行加变体扩样本。
- `Run-AgentEval.ps1`：评测主脚本。
- `results/`：运行产物（首次运行自动创建）。
