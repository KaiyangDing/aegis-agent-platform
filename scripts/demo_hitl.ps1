# demo_hitl.ps1 —— M3.9 HITL 业务闭环真实链路演示（六段，plans §4.9 验收面）
# 编码警示：本文件必须保存为 UTF-8 with BOM——Windows PowerShell 5.1 对无 BOM 源文件
# 按 ANSI 代码页（中文系统=GBK）解析，中文注释会撕碎字符串终结符（06 §4 家族新变体）。
#
# 段A 挂起：退款 300 > 阈值 200 必挂审批（approval_pending 提示可见）
# 段B 对抗④：B 租户坐席批 A 单 → 403（单据零翻转）
# 段C 批准：decide CAS → #8 前置校验重跑通过 → 执行 → 自动续跑（重复决策 409）
# 段D TOCTOU：批准落锤前订单在别处被退 → 前置校验否决 → 不执行（#8 的存在理由）
# 段E 超时：时钟注入 + 生产对账任务体 → EXPIRED + 终止 + 会话准入恢复
# 段F 撤回：用户显式取消 → CANCELLED 终止
#
# 前置（各开一窗，均在仓库根）：
#   docker compose -f deploy/docker-compose.yml up -d
#   uv run alembic upgrade head
#   uv run python scripts/seed_demo.py
#   uv run uvicorn aegis.api.main:create_app --factory        # API 窗口，跑完不关
# 真实调用：约 8–12 次百炼调用（四次挂起 run + 两次批准续跑），预算 < ¥0.05。
# 本脚本用 curl.exe（PS 别名 curl=Invoke-WebRequest，参数不兼容——§4.9 陷阱 4）。

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()   # 06 §4 第 3 坑：两端钉 UTF-8
$env:PYTHONUTF8 = "1"

$Base = "http://127.0.0.1:8000"
$run = Get-Random -Minimum 10000 -Maximum 99999                 # 会话随机后缀（M2.11 教训：残留×固定 id）

function Invoke-Api {
    param($Method, $Path, $Token, $Body = $null)
    $out = New-TemporaryFile
    $curlArgs = @("-s", "-o", $out.FullName, "-w", "%{http_code}", "-X", $Method, "$Base$Path",
                  "-H", "Authorization: Bearer $Token")
    if ($null -ne $Body) {
        $tmp = New-TemporaryFile   # 中文经文件走 UTF-8 无 BOM，绕开控制台代码页（06 §4）
        [System.IO.File]::WriteAllText($tmp.FullName, ($Body | ConvertTo-Json -Depth 5),
                                       [System.Text.UTF8Encoding]::new($false))
        $curlArgs += @("-H", "Content-Type: application/json", "-d", "@$($tmp.FullName)")
    }
    $code = & curl.exe @curlArgs
    $text = Get-Content $out.FullName -Raw -Encoding UTF8
    [pscustomobject]@{ Code = [int]$code; Json = $(if ($text) { $text | ConvertFrom-Json } else { $null }) }
}

function Assert-True { param($Cond, $Label)
    if ($Cond) { Write-Host "  PASS  $Label" -ForegroundColor Green }
    else       { Write-Host "  FAIL  $Label" -ForegroundColor Red; exit 1 }
}

function Get-HelperStatus { param($Sid)
    $lines = uv run python scripts/demo_hitl_helper.py status $Sid | Out-String
    Write-Host $lines
    return $lines
}

function New-Suspension { param($Sid, $Token)
    $msg = "请直接为订单 HITL-DEMO-0001 提交 300 元退款申请，不需要与我确认。"
    $resp = Invoke-Api POST "/v1/chat" $Token @{ session_id = $Sid; message = $msg }
    Assert-True ($resp.Code -eq 200 -and $resp.Json.status -eq "awaiting_approval") "挂起：$Sid 进入 awaiting_approval"
    Assert-True ($null -ne $resp.Json.approval_id) "approval_pending 提示可见（单号 $($resp.Json.approval_id)）"
    return $resp.Json.approval_id
}

Write-Host "`n=== 准备：发 token + 演示订单就绪 ===" -ForegroundColor Cyan
$UserTok = (uv run python scripts/mint_token.py u-a1  | Select-Object -Last 1).ToString().Trim()
$OpATok  = (uv run python scripts/mint_token.py op-a1 | Select-Object -Last 1).ToString().Trim()
$OpBTok  = (uv run python scripts/mint_token.py op-b1 | Select-Object -Last 1).ToString().Trim()
uv run python scripts/demo_hitl_helper.py seed

Write-Host "`n=== 段A 挂起：退款 300 > 阈值 200 必挂审批 ===" -ForegroundColor Cyan
$sidA = "hitl-approve-$run"
$aid1 = New-Suspension $sidA $UserTok

Write-Host "`n=== 段B 对抗④：B 租户坐席批 A 单 -> 403 ===" -ForegroundColor Cyan
$adv = Invoke-Api POST "/v1/approvals/$aid1" $OpBTok @{ decision = "approve" }
Assert-True ($adv.Code -eq 403) "跨租户裁决被 403（$($adv.Json.detail)）"
$st = Get-HelperStatus $sidA
Assert-True ($st -match "status=pending") "单据零翻转（仍 pending）"

Write-Host "`n=== 段C 批准：decide CAS -> #8 重跑通过 -> 执行 -> 自动续跑 ===" -ForegroundColor Cyan
$ok = Invoke-Api POST "/v1/approvals/$aid1" $OpATok @{ decision = "approve" }
Assert-True ($ok.Code -eq 200 -and $ok.Json.status -eq "done") "批准后同步续跑到终止（reason=$($ok.Json.reason)）"
Write-Host "  模型答复：$($ok.Json.reply)"
$dup = Invoke-Api POST "/v1/approvals/$aid1" $OpATok @{ decision = "reject" }
Assert-True ($dup.Code -eq 409) "重复决策：CAS 输家 409 不覆盖赢家"
$st = Get-HelperStatus $sidA
Assert-True ($st -match "status=approved") "审批单 approved"
Assert-True ($st -notmatch "event_id=空") "审计链回填（event_id=执行的 write-ahead 事件 id）"
Assert-True ($st -match "order HITL-DEMO-0001 status=refunded") "退款真执行（mock 订单翻 refunded）"

Write-Host "`n=== 段D TOCTOU：批准落锤前订单在别处被退 -> #8 否决不执行 ===" -ForegroundColor Cyan
uv run python scripts/demo_hitl_helper.py seed            # 复位 paid，让新挂起成立
$sidD = "hitl-toctou-$run"
$aid2 = New-Suspension $sidD $UserTok
uv run python scripts/demo_hitl_helper.py mark-refunded   # 剧情：审批还挂着，订单先被退了
$veto = Invoke-Api POST "/v1/approvals/$aid2" $OpATok @{ decision = "approve" }
Assert-True ($veto.Code -eq 200 -and $veto.Json.status -eq "done") "批准落锤但续跑完成（否决原因回填模型）"
Write-Host "  模型答复：$($veto.Json.reply)"
$st = Get-HelperStatus $sidD
Assert-True ($st -match "status=approved") "单据 approved（坐席确实批了）"
Assert-True ($st -match "event_id=空") "但前置校验否决：未执行、无审计事件可挂（#8 TOCTOU 实证)"

Write-Host "`n=== 段E 超时：时钟注入 + 生产对账任务体 -> EXPIRED + 终止 ===" -ForegroundColor Cyan
uv run python scripts/demo_hitl_helper.py seed
$sidE = "hitl-expire-$run"
$aid3 = New-Suspension $sidE $UserTok
uv run python scripts/demo_hitl_helper.py expire $aid3
uv run python scripts/demo_hitl_helper.py sweep           # 即 beat 每 60s 调的 expire_approvals 本体
$late = Invoke-Api POST "/v1/approvals/$aid3" $OpATok @{ decision = "approve" }
Assert-True ($late.Code -eq 409) "过期后补批被 409（C7 fail-closed）"
$st = Get-HelperStatus $sidE
Assert-True ($st -match "status=expired") "审批单 expired"
Assert-True ($st -match "approval_expired,loop_terminated") "到期事件 + CANCELLED 终止落盘"
Assert-True ($st -match "run_state=idle") "run_state 复位 idle"
$again = Invoke-Api POST "/v1/chat" $UserTok @{ session_id = $sidE; message = "那先不退了，帮我看看订单状态。" }
Assert-True ($again.Code -eq 200 -and $again.Json.status -ne "awaiting_approval") "会话准入恢复（可继续对话）"

Write-Host "`n=== 段F 撤回：用户显式取消 -> CANCELLED 终止 ===" -ForegroundColor Cyan
uv run python scripts/demo_hitl_helper.py seed
$sidF = "hitl-cancel-$run"
$aid4 = New-Suspension $sidF $UserTok
$cxl = Invoke-Api POST "/v1/chat" $UserTok @{ session_id = $sidF; message = "取消"; cancel_pending_approval = $true }
Assert-True ($cxl.Code -eq 200 -and $cxl.Json.status -eq "cancelled") "显式取消生效（approval_id=$aid4）"
$st = Get-HelperStatus $sidF
Assert-True ($st -match "status=cancelled") "审批单 cancelled"
Assert-True ($st -match "approval_cancelled,loop_terminated") "撤回事件 + CANCELLED 终止落盘"

Write-Host "`n=== 全部六段 PASS ===" -ForegroundColor Green
Write-Host "覆盖：挂起提示 / 对抗④ 403 / 批准重跑执行续跑 / TOCTOU 否决 / 超时终止+准入恢复 / 撤回。"
