#requires -Version 7.0

[CmdletBinding()]
param(
    [ValidateRange(1024, 65535)]
    [int]$Port = 5180,

    [ValidatePattern('^[A-Za-z0-9_-]+$')]
    [string]$Session = 'truman-review',

    [ValidateRange(0, 2)]
    [int]$OpeningIndex = 1,

    [string]$InjectedEvent = '暴雨突然来临，咖啡馆成为临时避雨点。',

    [string]$ResidentId = 'alice',

    [ValidateRange(30, 900)]
    [int]$TimeoutSeconds = 300,

    [string]$OutputDir = '',

    [string]$MockLlmFixture = '',

    [switch]$SkipDoctor,

    [switch]$KeepHarness,

    [switch]$KeepBrowser
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$RunStamp = Get-Date -Format 'yyyyMMdd-HHmmss'
if (-not $OutputDir) {
    $OutputDir = Join-Path (Split-Path $ProjectRoot -Parent) "review\opencli-smoke-$RunStamp"
}
$OutputDir = [System.IO.Path]::GetFullPath($OutputDir)
$StdoutLog = Join-Path $OutputDir 'harness.stdout.log'
$StderrLog = Join-Path $OutputDir 'harness.stderr.log'
$ResultPath = Join-Path $OutputDir 'result.json'
$HarnessProcess = $null
$BrowserOpened = $false
$Succeeded = $false

function Write-Step {
    param([string]$Message)
    Write-Host "`n==> $Message" -ForegroundColor Cyan
}

function Require-Command {
    param([string]$Name)
    $command = Get-Command $Name -ErrorAction SilentlyContinue
    if (-not $command) {
        throw "Required command '$Name' was not found in PATH."
    }
    return $command
}

function Test-LocalPort {
    param([int]$TargetPort)
    $client = [System.Net.Sockets.TcpClient]::new()
    try {
        $task = $client.ConnectAsync('127.0.0.1', $TargetPort)
        return $task.Wait(400) -and $client.Connected
    }
    catch {
        return $false
    }
    finally {
        $client.Dispose()
    }
}

function Invoke-OpenCli {
    param(
        [Parameter(Mandatory)]
        [string[]]$Arguments,
        [switch]$Quiet
    )

    # Keep stderr separate: OpenCLI prints version/update notices there, and
    # merging them into stdout corrupts JSON returned by browser eval.
    $stderrPath = [System.IO.Path]::GetTempFileName()
    try {
        $output = & opencli @Arguments 2> $stderrPath | Out-String
        $exitCode = $LASTEXITCODE
        $stderr = if (Test-Path $stderrPath) { Get-Content -Raw $stderrPath } else { '' }
        if ($exitCode -ne 0) {
            throw "opencli $($Arguments -join ' ') failed:`n$output`n$stderr"
        }
        if (-not $Quiet) {
            if ($output.Trim()) { Write-Host $output.TrimEnd() }
            if ($stderr.Trim()) { Write-Host $stderr.TrimEnd() -ForegroundColor DarkGray }
        }
        return $output
    }
    finally {
        Remove-Item -LiteralPath $stderrPath -Force -ErrorAction SilentlyContinue
    }
}

function ConvertFrom-OpenCliJson {
    param([string]$Text)

    # OpenCLI may print an update notice after the JSON envelope. Every eval in
    # this script returns one object, so trim from the first to the last brace.
    $start = $Text.IndexOf('{')
    $end = $Text.LastIndexOf('}')
    if ($start -lt 0 -or $end -le $start) {
        throw "OpenCLI output did not contain a JSON object:`n$Text"
    }
    return $Text.Substring($start, $end - $start + 1) | ConvertFrom-Json
}

function Invoke-BrowserEval {
    param([Parameter(Mandatory)][string]$JavaScript)
    $raw = Invoke-OpenCli -Arguments @('browser', $Session, 'eval', $JavaScript) -Quiet
    return ConvertFrom-OpenCliJson $raw
}

function Get-AppState {
    return Invoke-BrowserEval @'
(() => {
  const frame = document.querySelector("#app");
  const doc = frame?.contentDocument;
  const app = frame?.contentWindow;
  const timecode = doc?.querySelector("#timecode")?.textContent?.trim() || "";
  const match = /t(\d+)/.exec(timecode);
  const harnessLog = document.querySelector("#log")?.innerText || "";
  return {
    ready: Boolean(app?.__truman && doc),
    lang: app?.__truman?.lang || null,
    timecode,
    tick: match ? Number(match[1]) : -1,
    tickDisabled: doc?.querySelector("#btn-tick")?.disabled ?? true,
    injectDisabled: doc?.querySelector("#btn-inject")?.disabled ?? true,
    status: doc?.querySelector("#status")?.textContent?.trim() || "",
    openings: [...(doc?.querySelectorAll("#openings .chapter") || [])].map((node) => ({
      id: node.dataset.openingId,
      text: node.innerText.trim(),
    })),
    openingVisible: doc ? !doc.querySelector("#openings")?.hidden : false,
    modalVisible: doc ? !doc.querySelector("#agent-modal")?.hidden : false,
    modalText: doc?.querySelector("#agent-modal")?.innerText?.trim() || "",
    panelText: doc?.querySelector("aside.panel")?.innerText?.trim() || "",
    residents: [...(doc?.querySelectorAll(".dot") || [])].map((node) => ({
      id: node.dataset.agentId,
      label: node.getAttribute("aria-label"),
      className: node.className,
    })),
    rpcErrors: (harnessLog.match(/(?:error|failed|\u2717).*$/gim) || []).slice(-20),
  };
})()
'@
}

function Wait-AppState {
    param(
        [scriptblock]$Predicate = { param($s) $s.ready },
        [Parameter(Mandatory)][string]$Description,
        [int]$Seconds = $TimeoutSeconds
    )

    $deadline = [DateTime]::UtcNow.AddSeconds($Seconds)
    $last = $null
    while ([DateTime]::UtcNow -lt $deadline) {
        $last = Get-AppState
        if (& $Predicate $last) {
            return $last
        }
        Start-Sleep -Seconds 2
    }
    $snapshot = if ($null -eq $last) { '<no state>' } else { $last | ConvertTo-Json -Depth 8 }
    throw "Timed out waiting for $Description after $Seconds seconds.`nLast state:`n$snapshot"
}

function Save-Screenshot {
    param(
        [Parameter(Mandatory)][string]$Name,
        [switch]$FullPage,
        [switch]$Clean
    )
    $path = Join-Path $OutputDir $Name
    $args = @('browser', $Session, 'screenshot', $path)
    if ($FullPage) {
        $args += '--full-page'
    }
    if ($Clean) {
        $args += @('--width', '960', '--height', '880')
    }
    Invoke-OpenCli -Arguments $args -Quiet | Out-Null
    Write-Host "Saved $path"
    return $path
}

function Set-CleanHarnessLayout {
    Invoke-BrowserEval @'
(() => {
  const header = document.querySelector("body > header");
  const aside = document.querySelector("body > aside");
  const main = document.querySelector("body > main");
  const frame = document.querySelector("#frame");
  const meta = frame?.querySelector(":scope > div");
  const app = document.querySelector("#app");
  if (!frame || !app) throw new Error("harness frame not found");
  if (header) header.style.display = "none";
  if (aside) aside.style.display = "none";
  if (meta) meta.style.display = "none";
  Object.assign(document.documentElement.style, { margin: "0", padding: "0" });
  Object.assign(document.body.style, { margin: "0", padding: "0", overflow: "hidden" });
  if (main) Object.assign(main.style, { display: "block", margin: "0", padding: "0" });
  Object.assign(frame.style, {
    position: "fixed", top: "0", left: "0", zIndex: "99999",
    width: "960px", height: "880px", margin: "0", padding: "0",
    border: "0", borderRadius: "0", boxShadow: "none",
  });
  Object.assign(app.style, {
    display: "block", width: "960px", height: "880px",
    margin: "0", padding: "0", border: "0",
  });
  return { ok: true, top: frame.getBoundingClientRect().top, left: frame.getBoundingClientRect().left };
})()
'@ | Out-Null
}

try {
    Write-Step 'Preflight'
    New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
    # On Windows, `Get-Command pnpm` resolves pnpm.ps1 first. Start-Process
    # cannot execute that shim directly, so use the native cmd launcher.
    $PnpmCommand = Require-Command 'pnpm.cmd'
    Require-Command 'opencli' | Out-Null
    if (Test-LocalPort $Port) {
        throw "Port $Port is already in use. Stop the existing harness or pass -Port with a free port."
    }
    if (-not $SkipDoctor) {
        Invoke-OpenCli -Arguments @('doctor') | Out-Null
    }

    Write-Step "Start Anna developer harness on port $Port"
    # `pnpm dev` is the single project entrypoint. scripts/dev.mjs injects a
    # UTF-8 Python environment for the anna-app bridge before it spawns.
    $harnessArgs = @('run', 'dev', '--', '--port', "$Port")
    if ($MockLlmFixture) {
        $fixturePath = if ([System.IO.Path]::IsPathRooted($MockLlmFixture)) {
            [System.IO.Path]::GetFullPath($MockLlmFixture)
        }
        else {
            [System.IO.Path]::GetFullPath((Join-Path $ProjectRoot $MockLlmFixture))
        }
        if (-not (Test-Path $fixturePath -PathType Leaf)) {
            throw "Mock LLM fixture not found: $fixturePath"
        }
        $harnessArgs += @('--mock-llm', $fixturePath)
    }
    $HarnessProcess = Start-Process `
        -FilePath $PnpmCommand.Source `
        -ArgumentList $harnessArgs `
        -WorkingDirectory $ProjectRoot `
        -RedirectStandardOutput $StdoutLog `
        -RedirectStandardError $StderrLog `
        -WindowStyle Hidden `
        -PassThru

    $deadline = [DateTime]::UtcNow.AddSeconds(60)
    while (-not (Test-LocalPort $Port)) {
        if ($HarnessProcess.HasExited) {
            $stdout = if (Test-Path $StdoutLog) { Get-Content -Raw $StdoutLog } else { '' }
            $stderr = if (Test-Path $StderrLog) { Get-Content -Raw $StderrLog } else { '' }
            throw "Harness exited early with code $($HarnessProcess.ExitCode).`nSTDOUT:`n$stdout`nSTDERR:`n$stderr"
        }
        if ([DateTime]::UtcNow -ge $deadline) {
            throw "Harness did not listen on port $Port within 60 seconds."
        }
        Start-Sleep -Milliseconds 500
    }

    Write-Step 'Open harness with OpenCLI'
    Invoke-OpenCli -Arguments @('browser', $Session, 'open', "http://localhost:$Port/") | Out-Null
    $BrowserOpened = $true
    $state = Wait-AppState -Description 'window.__truman and the App iframe'

    # Keep screenshots deterministic even if a previous browser session stored EN.
    if ($state.lang -ne 'zh') {
        Invoke-BrowserEval @'
(async () => {
  const app = document.querySelector("#app")?.contentWindow;
  await app.__truman.toggleLang();
  return { ok: true, lang: app.__truman.lang };
})()
'@ | Out-Null
        $state = Wait-AppState -Description 'Chinese UI' -Predicate { param($s) $s.lang -eq 'zh' }
    }

    Write-Step 'Initialize the town'
    Invoke-BrowserEval @'
(async () => {
  const app = document.querySelector("#app")?.contentWindow;
  if (!app?.__truman) throw new Error("window.__truman is unavailable");
  await app.__truman.onStart();
  return { ok: true };
})()
'@ | Out-Null
    $state = Wait-AppState -Description 'initialized town and opening cards' -Predicate {
        param($s) $s.tick -eq 0 -and -not $s.tickDisabled -and $s.openings.Count -ge 3
    }

    $OpeningId = $state.openings[$OpeningIndex].id
    $OpeningText = $state.openings[$OpeningIndex].text
    $OpeningIdJson = $OpeningId | ConvertTo-Json -Compress
    Write-Step "Run opening '$OpeningId' (three real LLM ticks)"
    Invoke-BrowserEval @"
(() => {
  const app = document.querySelector("#app")?.contentWindow;
  app.__truman.pickOpening($OpeningIdJson);
  return { started: true, openingId: $OpeningIdJson };
})()
"@ | Out-Null
    $state = Wait-AppState -Description 'opening sequence through tick 3' -Predicate {
        param($s) $s.tick -ge 3 -and -not $s.tickDisabled
    }
    $FirstActEvidence = Save-Screenshot -Name '01-first-act-evidence.png' -FullPage

    Write-Step "Inject director event: $InjectedEvent"
    $EventJson = $InjectedEvent | ConvertTo-Json -Compress
    Invoke-BrowserEval @"
(() => {
  const doc = document.querySelector("#app")?.contentDocument;
  const input = doc.querySelector("#inject-input");
  input.value = $EventJson;
  input.dispatchEvent(new Event("input", { bubbles: true }));
  doc.querySelector("#btn-inject").click();
  return { queued: true };
})()
"@ | Out-Null
    $BeforeInjectedTick = $state.tick
    Wait-AppState -Description 'director injection acknowledgement' -Predicate {
        param($s) $s.status -match "t$($BeforeInjectedTick + 1)" -and -not $s.injectDisabled
    } | Out-Null

    Write-Step "Advance tick $($BeforeInjectedTick + 1)"
    Invoke-BrowserEval @'
(() => {
  const app = document.querySelector("#app")?.contentWindow;
  app.__truman.onTick(1);
  return { started: true };
})()
'@ | Out-Null
    $state = Wait-AppState -Description 'post-injection tick' -Predicate {
        param($s) $s.tick -ge ($BeforeInjectedTick + 1) -and -not $s.tickDisabled
    }
    if ($state.panelText -notlike "*$InjectedEvent*") {
        throw 'The injected event was not rendered in the subtitle panel.'
    }
    $InjectionEvidence = Save-Screenshot -Name '02-injection-evidence.png' -FullPage

    Write-Step 'Create clean review screenshots'
    Set-CleanHarnessLayout
    $CleanInjection = Save-Screenshot -Name '03-clean-injection.png' -Clean

    $ResidentJson = $ResidentId | ConvertTo-Json -Compress
    Invoke-BrowserEval @"
(() => {
  const doc = document.querySelector("#app")?.contentDocument;
  const dot = doc.querySelector(``.dot[data-agent-id=$ResidentJson]``);
  if (!dot) throw new Error("resident dot not found: " + $ResidentJson);
  dot.click();
  return { clicked: true };
})()
"@ | Out-Null
    $state = Wait-AppState -Description "resident dossier for $ResidentId" -Predicate {
        param($s) $s.modalVisible -and $s.modalText.Length -gt 20
    }
    $CleanDossier = Save-Screenshot -Name '04-clean-dossier.png' -Clean

    Invoke-BrowserEval @'
(async () => {
  const frame = document.querySelector("#app");
  const doc = frame.contentDocument;
  const app = frame.contentWindow;
  doc.querySelector("#agent-close").click();
  if (app.__truman.lang !== "en") await app.__truman.toggleLang();
  return { ok: true, lang: app.__truman.lang };
})()
'@ | Out-Null
    $state = Wait-AppState -Description 'English UI' -Predicate { param($s) $s.lang -eq 'en' }
    if ($state.timecode -notmatch '^Day ') {
        throw "English timecode did not render: $($state.timecode)"
    }
    $CleanEnglish = Save-Screenshot -Name '05-clean-english.png' -Clean

    if ($state.rpcErrors.Count -gt 0) {
        throw "Harness RPC log contains errors:`n$($state.rpcErrors -join "`n")"
    }

    $Result = [ordered]@{
        ok = $true
        run_at = (Get-Date).ToString('o')
        project_root = $ProjectRoot
        harness_url = "http://localhost:$Port/"
        session = $Session
        llm_mode = if ($MockLlmFixture) { 'mock' } else { 'real' }
        opening = [ordered]@{ index = $OpeningIndex; id = $OpeningId; text = $OpeningText }
        injected_event = $InjectedEvent
        resident_id = $ResidentId
        final_state = $state
        screenshots = @(
            $FirstActEvidence,
            $InjectionEvidence,
            $CleanInjection,
            $CleanDossier,
            $CleanEnglish
        )
        logs = @($StdoutLog, $StderrLog)
    }
    $Result | ConvertTo-Json -Depth 12 | Set-Content -Path $ResultPath -Encoding utf8
    $Succeeded = $true

    Write-Step 'PASS'
    Write-Host "Result: $ResultPath" -ForegroundColor Green
    Write-Host "Screenshots: $OutputDir" -ForegroundColor Green
}
catch {
    Write-Host "`nSmoke test failed: $($_.Exception.Message)" -ForegroundColor Red
    foreach ($log in @($StdoutLog, $StderrLog)) {
        if (Test-Path $log) {
            Write-Host "`n--- $(Split-Path $log -Leaf) (tail) ---" -ForegroundColor Yellow
            Get-Content $log -Tail 80
        }
    }
    throw
}
finally {
    if ($BrowserOpened -and -not $KeepBrowser) {
        try {
            Invoke-OpenCli -Arguments @('browser', $Session, 'close') -Quiet | Out-Null
        }
        catch {
            Write-Warning "Could not close OpenCLI session '$Session': $($_.Exception.Message)"
        }
    }

    if ($HarnessProcess -and -not $HarnessProcess.HasExited -and -not $KeepHarness) {
        # Kill the exact process tree created by this script; anna-app dev owns
        # a Node bridge plus its Python Executa child.
        & taskkill.exe /PID $HarnessProcess.Id /T /F 2>$null | Out-Null
    }
    elseif ($HarnessProcess -and -not $HarnessProcess.HasExited -and $KeepHarness) {
        Write-Host "Harness left running (PID $($HarnessProcess.Id), port $Port)." -ForegroundColor Yellow
    }

    if ($Succeeded) {
        Write-Host 'Cleanup complete.' -ForegroundColor DarkGray
    }
}
