<#
.SYNOPSIS
    Create the isolated release sandbox: <sandboxRoot>/src (fresh clones the release modifies) and
    <sandboxRoot>/runtime (a platform deployed from the PREVIOUS stable for per-wave health probing).

.DESCRIPTION
    Source isolation — the release never touches your day-to-day clones:
      1. Clone vc-platform + every vc-module-* (that exists under the current monorepoRoot) into
         <sandboxRoot>/src, then repoint release.config.json `monorepoRoot`/`localNugetPath` there, so
         ALL tooling (release_module.ps1, audit_obsolete.py, finalize_bundle.py, …) operates on the
         sandbox automatically.
      2. Deploy the previous stable bundle into <sandboxRoot>/runtime and pause for you to edit the
         runtime env file (DB connection string, etc.).

    After this, verify the baseline with `probe-runtime.ps1` (start → /health → stop), then run the
    waves; after each wave `probe-runtime.ps1 -Deploy` re-verifies the runtime.

.PARAMETER Reclone        Re-clone repos even if already present in the sandbox.
.PARAMETER SkipClone      Skip the source clone step (just (re)point config / do runtime).
.PARAMETER SkipRuntime    Skip the runtime deploy step.
.PARAMETER Shallow        Shallow clone (--depth 1) for speed (no history).
.PARAMETER InstallRuntime Attempt the vc-build install of the previous bundle into the runtime
                          (environment-specific; off by default — prints the commands otherwise).
#>
[CmdletBinding()]
param(
    [switch]$Reclone,
    [switch]$SkipClone,
    [switch]$SkipRuntime,
    [switch]$Shallow,
    [switch]$InstallRuntime
)
$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\release-config.ps1"
$cfg = Get-ReleaseConfig
if (-not $cfg.SandboxRoot) { throw "Set 'sandboxRoot' in release.config.json first." }

$srcRoot   = $cfg.SrcPath
$runtime   = $cfg.RuntimePath
$feed      = Join-Path $srcRoot 'local-nuget'
$origRoot  = $cfg.MonorepoRoot                 # the existing working clones (source of repo list + remotes)
function Step($m) { Write-Host "`n=== [sandbox] $m ===" -ForegroundColor Cyan }

New-Item -ItemType Directory -Force -Path $srcRoot, $runtime, $feed | Out-Null
Step "sandbox = $($cfg.SandboxRoot)  (src + runtime)"

if (-not $SkipClone) {
    Step "clone source repos -> $srcRoot  (from $origRoot)"
    if ($srcRoot -ieq $origRoot) { throw "monorepoRoot already points at the sandbox src — nothing to clone from. (Restore it to your working clones first.)" }
    $repos = @(Get-Item (Join-Path $origRoot 'vc-platform') -ErrorAction SilentlyContinue) +
             @(Get-ChildItem $origRoot -Directory -Filter 'vc-module-*' -ErrorAction SilentlyContinue)
    foreach ($repo in ($repos | Where-Object { $_ })) {
        $dest = Join-Path $srcRoot $repo.Name
        if ((Test-Path $dest) -and -not $Reclone) { Write-Host "  skip (exists): $($repo.Name)"; continue }
        if (Test-Path $dest) { Remove-Item $dest -Recurse -Force }
        $url = (git -C $repo.FullName config --get remote.origin.url).Trim()
        if (-not $url) { Write-Host "  ! no origin for $($repo.Name) — skipped"; continue }
        $depth = if ($Shallow) { @('--depth', '1') } else { @() }
        Write-Host "  cloning $($repo.Name) (dev) ..."
        git clone @depth --branch dev $url $dest 2>&1 | Select-Object -Last 1
    }
}

Step "repoint release.config.json -> sandbox src"
$cfgPath = $cfg.ConfigPath
$json = Get-Content $cfgPath -Raw | ConvertFrom-Json
if ($json.monorepoRoot -ine $srcRoot) {
    Copy-Item $cfgPath "$cfgPath.bak" -Force
    Write-Host "  monorepoRoot : $($json.monorepoRoot)  ->  $srcRoot"
    Write-Host "  localNugetPath: $($json.localNugetPath)  ->  $feed"
    $json.monorepoRoot = $srcRoot
    $json.localNugetPath = $feed
    ($json | ConvertTo-Json -Depth 10) | Set-Content -Path $cfgPath -Encoding UTF8
    Write-Host "  (backup: $cfgPath.bak — restore it to return to non-isolated mode)"
} else {
    Write-Host "  already pointed at sandbox src."
}

if (-not $SkipRuntime) {
    Step "runtime baseline = PREVIOUS stable (v$($cfg.PrevVersion))"
    $prevPlatform = $null; $prevUrl = $null
    try {
        $prevPkg = Get-Content (Join-Path $PSScriptRoot "..\bundles\v$($cfg.PrevVersion)\package.json") -Raw | ConvertFrom-Json
        $prevPlatform = $prevPkg.PlatformVersion
        $prevUrl = (Get-Content (Join-Path $PSScriptRoot "..\bundles\stable.json") -Raw | ConvertFrom-Json)."$($cfg.PrevVersion)"
    } catch { }
    Write-Host "  previous platform version : $prevPlatform"
    Write-Host "  previous bundle url       : $prevUrl"

    if ($InstallRuntime -and $prevPlatform) {
        Write-Host "  installing into $runtime (vc-build) ..."
        Push-Location $runtime
        try {
            vc-build InstallPlatform -PlatformVersion $prevPlatform
            vc-build InstallModules
        } catch {
            Write-Host "  ! vc-build install failed: $_" -ForegroundColor Yellow
            Write-Host "    Deploy the previous platform $prevPlatform + the modules from $prevUrl into $runtime manually."
        } finally { Pop-Location }
    } else {
        Write-Host "  (install skipped) Deploy platform $prevPlatform + modules from the bundle into:" -ForegroundColor Yellow
        Write-Host "    $runtime"
        Write-Host "    e.g. (from $runtime):  vc-build InstallPlatform -PlatformVersion $prevPlatform ; vc-build InstallModules"
        Write-Host "    or extract the platform zip + the bundle's module zips. Re-run with -InstallRuntime to attempt it."
    }

    $env = Get-ChildItem $runtime -Recurse -Filter 'appsettings*.json' -ErrorAction SilentlyContinue |
        Where-Object { $_.FullName -notmatch '[\\/]modules[\\/]' } | Select-Object -First 1
    Write-Host "`n  >>> ACTION REQUIRED: edit the runtime env/config (DB connection string, etc.):" -ForegroundColor Magenta
    Write-Host ("      " + ($(if ($env) { $env.FullName } else { "$runtime\appsettings.json (after install)" })))
}

Write-Host "`nNext: edit the runtime env file, then verify the baseline:" -ForegroundColor Green
Write-Host "  pwsh -File src/probe-runtime.ps1            # start -> /health -> stop"
Write-Host "Then run the waves; after each wave: pwsh -File src/probe-runtime.ps1 -Deploy -Modules <names>"
