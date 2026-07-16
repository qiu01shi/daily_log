<#
.SYNOPSIS
    自动建模 Agent 最小评测脚本（对照 pipeline vs single）。

.DESCRIPTION
    针对每个任务，调用后端 /agent/chat（可强制 mode），解析返回的 trace，
    再单独 POST /run 做客观“模型是否真能跑起来”的检查，汇总成指标表。

    指标（全部来自真实接口，不含臆造）：
      - run_ok           : chat 完后单独 /run 成功（客观任务成功信号，最硬）
      - llm_success      : trace.success（LLM 是否正常收尾，非“模型能跑”）
      - tool_calls       : trace 中 kind==tool_call 的步数
      - tool_fail        : kind==tool_result 且 result.ok==false 的步数（无效调用）
      - antithrash       : tool_result 带 antiThrash 教练提示的次数（反振荡命中）
      - noop             : tool_result 带 noop==true 的次数（幂等命中）
      - builder_skipped  : trace 文本里检测到 “Phase 1 … skip”（确定性执行器跳过 builder，启发式）
      - latency_ms       : 客户端测的一次 chat 墙钟耗时

    无法测量（诚实）：
      - token 用量：trace 里没有该字段，接口拿不到。
      - 逐层防线开关（PortHints/反振荡/CapabilityProbe/PlanValidator）：无环境变量，硬编码常开，
        要 A/B 需在代码里加 feature flag。本脚本只能 A/B: pipeline vs single（逐请求切 mode），
        以及 reviewer/replan（需重启后端并设 AGENT_REVIEWER_ENABLED / AGENT_REPLAN_ON_FAILURE）。

.PARAMETER BaseUrl
    后端地址，默认 http://localhost:7777

.PARAMETER Mode
    pipeline | single | router | both（both = 同一批任务分别用 pipeline 和 single 各跑一遍做对照）

.PARAMETER Repeat
    每个任务重复次数（LLM 有随机性，建议 >=3 取均值）

.PARAMETER TasksFile
    任务集 JSON，默认同目录 tasks.json

.PARAMETER OutDir
    结果输出目录，默认同目录 results/

.EXAMPLE
    .\Run-AgentEval.ps1 -Mode both -Repeat 3
#>

param(
    [string]$BaseUrl = "http://localhost:7777",
    [ValidateSet("pipeline", "single", "router", "both")]
    [string]$Mode = "both",
    [int]$Repeat = 3,
    [string]$TasksFile = "$PSScriptRoot\tasks.json",
    [string]$OutDir = "$PSScriptRoot\results",
    [int]$TimeoutSec = 600
)

$ErrorActionPreference = "Stop"

function Get-Prop {
    param($Obj, [string]$Name, $Default = $null)
    if ($null -ne $Obj -and $Obj.PSObject.Properties.Name -contains $Name) {
        return $Obj.$Name
    }
    return $Default
}

function Invoke-Api {
    param(
        [string]$Method,
        [string]$Path,
        $Body = $null
    )
    $uri = "$BaseUrl$Path"
    try {
        if ($null -ne $Body) {
            $json = $Body | ConvertTo-Json -Depth 8 -Compress
            return Invoke-RestMethod -Method $Method -Uri $uri -Body $json `
                -ContentType "application/json" -TimeoutSec $TimeoutSec
        }
        return Invoke-RestMethod -Method $Method -Uri $uri -TimeoutSec $TimeoutSec
    }
    catch {
        return [pscustomobject]@{ __error = $_.Exception.Message }
    }
}

function Test-Backend {
    $status = Invoke-Api -Method GET -Path "/api/v1/agent/status"
    if ($null -ne (Get-Prop $status "__error")) {
        Write-Host "[FATAL] 无法连接后端 $BaseUrl : $($status.__error)" -ForegroundColor Red
        Write-Host "        先启动后端：.\agent-output\start-agent-flash.ps1 -Dev" -ForegroundColor Yellow
        exit 1
    }
    $strategy = Get-Prop $status "strategy" "unknown"
    Write-Host "[ok] 后端在线, strategy=$strategy" -ForegroundColor Green
    $probes = Get-Prop $status "smokeProbes"
    if ($null -ne $probes) {
        $flash = Get-Prop $probes "flash"
        if ($flash -and $flash -ne "ok") {
            Write-Host "[warn] LLM smoke probe 非 ok（flash=$flash）——可能没配 API key，结果会失真。" -ForegroundColor Yellow
        }
    }
}

function Measure-Trace {
    param($Trace)
    $steps = Get-Prop $Trace "steps" @()
    $toolCalls = 0; $toolFail = 0; $antithrash = 0; $noop = 0
    $builderSkipped = $false
    foreach ($s in $steps) {
        $kind = Get-Prop $s "kind" ""
        $text = Get-Prop $s "text" ""
        if ($kind -eq "tool_call") { $toolCalls++ }
        elseif ($kind -eq "tool_result") {
            $res = Get-Prop $s "arguments"
            $ok = Get-Prop $res "ok" $true
            if ($ok -eq $false) { $toolFail++ }
            # antiThrash 教练提示挂在 tool_result 顶层
            if ($null -ne (Get-Prop $res "antiThrash")) { $antithrash++ }
            # 幂等 noop 挂在 AgentResult 的 data 里（data.noop==true）
            $data = Get-Prop $res "data"
            if ((Get-Prop $data "noop" $false) -eq $true) { $noop++ }
        }
        # 启发式：检测确定性执行器跳过 builder 的阶段标记文本
        if ($text -match '(?i)phase\s*1' -and $text -match '(?i)skip') {
            $builderSkipped = $true
        }
    }
    return [pscustomobject]@{
        llm_success     = [bool](Get-Prop $Trace "success" $false)
        steps_total     = @($steps).Count
        tool_calls      = $toolCalls
        tool_fail       = $toolFail
        antithrash      = $antithrash
        noop            = $noop
        builder_skipped = $builderSkipped
    }
}

function Invoke-OneTask {
    param($Task, [string]$RunMode)

    $create = Invoke-Api -Method POST -Path "/api/v1/sessions"
    $sid = Get-Prop $create "id"
    if (-not $sid) {
        return [pscustomobject]@{ error = "session 创建失败: $(Get-Prop $create '__error')" }
    }

    $body = @{ message = $Task.prompt }
    if ($RunMode -ne "router") { $body.mode = $RunMode }

    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    $resp = Invoke-Api -Method POST -Path "/api/v1/sessions/$sid/agent/chat" -Body $body
    $sw.Stop()

    $err = Get-Prop $resp "__error"
    if ($null -ne $err) {
        Invoke-Api -Method DELETE -Path "/api/v1/sessions/$sid" | Out-Null
        return [pscustomobject]@{
            task = $Task.id; mode = $RunMode; error = $err
            run_ok = $false; llm_success = $false; latency_ms = $sw.ElapsedMilliseconds
        }
    }

    $routed = Get-Prop $resp "mode" $RunMode
    $m = Measure-Trace (Get-Prop $resp "trace")

    # 客观检查：单独跑一次仿真，看自动建出的模型能不能真跑起来
    $runRes = Invoke-Api -Method POST -Path "/api/v1/sessions/$sid/run"
    $runOk = [bool](Get-Prop $runRes "ok" $false)

    Invoke-Api -Method DELETE -Path "/api/v1/sessions/$sid" | Out-Null

    return [pscustomobject]@{
        task            = $Task.id
        mode            = $RunMode
        routed          = $routed
        run_ok          = $runOk
        llm_success     = $m.llm_success
        tool_calls      = $m.tool_calls
        tool_fail       = $m.tool_fail
        antithrash      = $m.antithrash
        noop            = $m.noop
        builder_skipped = $m.builder_skipped
        steps_total     = $m.steps_total
        latency_ms      = $sw.ElapsedMilliseconds
        error           = $null
    }
}

function Get-Aggregate {
    param([string]$RunMode, $Rows)
    $valid = @($Rows | Where-Object { $_.mode -eq $RunMode -and $null -eq $_.error })
    $n = $valid.Count
    if ($n -eq 0) {
        return [pscustomobject]@{ mode = $RunMode; runs = 0 }
    }
    $runOk = @($valid | Where-Object { $_.run_ok }).Count
    $llmOk = @($valid | Where-Object { $_.llm_success }).Count
    $skip  = @($valid | Where-Object { $_.builder_skipped }).Count
    function Avg($prop) {
        return [math]::Round((($valid | Measure-Object -Property $prop -Average).Average), 2)
    }
    return [pscustomobject]@{
        mode              = $RunMode
        runs              = $n
        run_ok_rate       = "$runOk/$n ($([math]::Round(100.0*$runOk/$n,1))%)"
        llm_success_rate  = "$llmOk/$n ($([math]::Round(100.0*$llmOk/$n,1))%)"
        builder_skip_rate = "$skip/$n ($([math]::Round(100.0*$skip/$n,1))%)"
        avg_tool_calls    = Avg "tool_calls"
        avg_tool_fail     = Avg "tool_fail"
        avg_antithrash    = Avg "antithrash"
        avg_noop          = Avg "noop"
        avg_latency_ms    = Avg "latency_ms"
    }
}

# ===== main =====

Test-Backend

if (-not (Test-Path $TasksFile)) {
    Write-Host "[FATAL] 找不到任务集: $TasksFile" -ForegroundColor Red
    exit 1
}
$taskSet = (Get-Content $TasksFile -Raw -Encoding UTF8 | ConvertFrom-Json).tasks
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

$modes = if ($Mode -eq "both") { @("pipeline", "single") } else { @($Mode) }

$rows = New-Object System.Collections.ArrayList
foreach ($rm in $modes) {
    foreach ($t in $taskSet) {
        for ($i = 1; $i -le $Repeat; $i++) {
            Write-Host ("[run] mode={0} task={1} rep={2}/{3} ..." -f $rm, $t.id, $i, $Repeat)
            $row = Invoke-OneTask -Task $t -RunMode $rm
            if ($row.error) {
                Write-Host ("       ERROR: {0}" -f $row.error) -ForegroundColor Red
            } else {
                Write-Host ("       run_ok={0} tool_calls={1} fail={2} antithrash={3} skip={4} {5}ms" -f `
                    $row.run_ok, $row.tool_calls, $row.tool_fail, $row.antithrash, $row.builder_skipped, $row.latency_ms)
            }
            [void]$rows.Add($row)
        }
    }
}

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$csvPath = Join-Path $OutDir "runs-$stamp.csv"
$rows | Export-Csv -Path $csvPath -NoTypeInformation -Encoding UTF8
Write-Host "`n[saved] 逐次明细: $csvPath" -ForegroundColor Green

# 汇总
$aggs = foreach ($rm in $modes) { Get-Aggregate -RunMode $rm -Rows $rows }

$md = New-Object System.Text.StringBuilder
[void]$md.AppendLine("# 自动建模 Agent 评测结果 ($stamp)")
[void]$md.AppendLine("")
[void]$md.AppendLine("- 后端: $BaseUrl")
[void]$md.AppendLine("- 任务数: $($taskSet.Count) x 重复 $Repeat = 每模式 $($taskSet.Count * $Repeat) 次")
[void]$md.AppendLine("- 注意: 小样本 + LLM 随机性, 结果为**方向性证据**, 非统计严格 benchmark。token 无法从接口获取。")
[void]$md.AppendLine("")
[void]$md.AppendLine("| 指标 \ 模式 | " + (($aggs | ForEach-Object { $_.mode }) -join " | ") + " |")
[void]$md.AppendLine("|---|" + (($aggs | ForEach-Object { "---" }) -join "|") + "|")
$metricRows = @(
    @("样本数",           "runs"),
    @("run 成功率(客观)",  "run_ok_rate"),
    @("LLM 收尾率",        "llm_success_rate"),
    @("builder 跳过率",    "builder_skip_rate"),
    @("平均工具调用数",     "avg_tool_calls"),
    @("平均失败调用数",     "avg_tool_fail"),
    @("平均反振荡命中",     "avg_antithrash"),
    @("平均幂等 noop",     "avg_noop"),
    @("平均时延 ms",       "avg_latency_ms")
)
foreach ($mr in $metricRows) {
    $label = $mr[0]; $key = $mr[1]
    $cells = ($aggs | ForEach-Object { Get-Prop $_ $key "-" }) -join " | "
    [void]$md.AppendLine("| $label | $cells |")
}

$mdPath = Join-Path $OutDir "summary-$stamp.md"
[System.IO.File]::WriteAllText($mdPath, $md.ToString(), [System.Text.Encoding]::UTF8)
Write-Host "[saved] 汇总表: $mdPath`n" -ForegroundColor Green
Write-Host $md.ToString()
