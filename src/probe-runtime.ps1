<#
.SYNOPSIS
    Automated per-wave runtime verification: (optionally deploy freshly built artifacts into the
    sandbox runtime), start the platform, poll its /health endpoint until Healthy (or timeout),
    then stop it. Returns exit 0 = healthy, non-zero = unhealthy/timeout.

.DESCRIPTION
    Used after each wave: drop the wave's new module zips (and/or the new platform) into the
    runtime, boot the platform, confirm health probes pass, shut down. This catches runtime/EF
    migration breakage that a compile-only check misses — without touching your real environment.

    Reliable parts (start / poll / stop) work on any platform install. The deploy step extracts
    VirtoCommerce module zips into <runtime>/modules/<ModuleName>; the platform itself (Wave 0) is
    updated by re-installing it into the runtime (see setup-sandbox.ps1 / RELEASE_PROCEDURE.md).

.PARAMETER RuntimePath  Platform runtime folder. Default: <sandboxRoot>/runtime from release.config.json.
.PARAMETER HealthUrl    Health endpoint. Default: healthUrl from release.config.json.
.PARAMETER Deploy       Extract staged module zips into <RuntimePath>/modules before starting.
.PARAMETER ArtifactPath Folder of staged module *.zip to deploy. Default: artifactStagingPath.
.PARAMETER Modules      Optional list of module zip name filters to deploy (default: all in ArtifactPath).
.PARAMETER TimeoutSec   Max seconds to wait for Healthy. Default 240.
.PARAMETER KeepRunning  Leave the platform running after a healthy probe (for the final E2E run).

.EXAMPLE
    ./probe-runtime.ps1 -Deploy -Modules Catalog,Core      # deploy + verify a wave
.EXAMPLE
    ./probe-runtime.ps1 -KeepRunning                       # boot the final solution for the E2E suite
#>
[CmdletBinding()]
param(
    [string]   $RuntimePath,
    [string]   $HealthUrl,
    [switch]   $Deploy,
    [string]   $ArtifactPath,
    [string[]] $Modules,
    [int]      $TimeoutSec = 240,
    [int]      $PollSec = 5,
    [switch]   $KeepRunning
)
$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\release-config.ps1"
$cfg = Get-ReleaseConfig
if (-not $RuntimePath)  { $RuntimePath  = $cfg.RuntimePath }
if (-not $HealthUrl)    { $HealthUrl    = $cfg.HealthUrl }
if (-not $ArtifactPath) { $ArtifactPath = $cfg.ArtifactStagingPath }
if (-not $RuntimePath)  { throw "No RuntimePath (set sandboxRoot in release.config.json or pass -RuntimePath)." }
if (-not (Test-Path $RuntimePath)) { throw "Runtime not found: $RuntimePath (run setup-sandbox.ps1 first)." }

function Step($m) { Write-Host "`n=== [probe] $m ===" -ForegroundColor Cyan }

if ($Deploy) {
    Step "deploy module artifacts -> $RuntimePath\modules"
    $modulesDir = Join-Path $RuntimePath 'modules'
    New-Item -ItemType Directory -Force -Path $modulesDir | Out-Null
    $zips = Get-ChildItem $ArtifactPath -Filter '*.zip' -ErrorAction Stop
    if ($Modules) {
        $zips = $zips | Where-Object { $n = $_.Name; ($Modules | Where-Object { $n -match $_ }) }
    }
    foreach ($z in $zips) {
        # VirtoCommerce module zip name: VirtoCommerce.<Module>_<version>.zip -> folder VirtoCommerce.<Module>
        $name = ($z.BaseName -replace '_\d+\.\d+\.\d+.*$', '')
        $dest = Join-Path $modulesDir $name
        if (Test-Path $dest) { Remove-Item $dest -Recurse -Force }
        Expand-Archive -Path $z.FullName -DestinationPath $dest -Force
        Write-Host "  deployed $($z.Name) -> modules\$name"
    }
}

Step "locate platform"
$dll = Get-ChildItem $RuntimePath -Recurse -Filter 'VirtoCommerce.Platform.Web.dll' -ErrorAction SilentlyContinue |
    Where-Object { $_.FullName -notmatch '[\\/](modules|node_modules)[\\/]' } | Select-Object -First 1
if (-not $dll) { throw "VirtoCommerce.Platform.Web.dll not found under $RuntimePath." }

$u = [Uri]$HealthUrl
$env:ASPNETCORE_URLS = "$($u.Scheme)://$($u.Host):$($u.Port)"
$env:ASPNETCORE_ENVIRONMENT = 'Development'
$log = Join-Path $RuntimePath 'probe.out.log'

Step "start platform ($($dll.Name)) on $env:ASPNETCORE_URLS"
$proc = Start-Process dotnet -ArgumentList "`"$($dll.FullName)`"" -WorkingDirectory $dll.DirectoryName `
    -PassThru -RedirectStandardOutput $log -RedirectStandardError "$log.err"

$healthy = $false; $status = ''
$deadline = (Get-Date).AddSeconds($TimeoutSec)
Step "poll $HealthUrl (timeout ${TimeoutSec}s)"
while ((Get-Date) -lt $deadline) {
    if ($proc.HasExited) { Write-Host "  platform process exited early (code $($proc.ExitCode)) — see $log.err"; break }
    try {
        $r = Invoke-WebRequest -Uri $HealthUrl -SkipCertificateCheck -TimeoutSec 10 -UseBasicParsing
        if ($r.StatusCode -eq 200) { $healthy = $true; $status = ($r.Content | Out-String).Trim(); break }
    } catch { }
    Start-Sleep -Seconds $PollSec
}

if ($healthy -and $KeepRunning) {
    Write-Host "`nHEALTHY: $status  (PID $($proc.Id) left running for the E2E run; stop it with: Stop-Process -Id $($proc.Id))" -ForegroundColor Green
    exit 0
}

Step "stop platform"
if (-not $proc.HasExited) { Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue }

if ($healthy) {
    Write-Host "`nHEALTHY: $status" -ForegroundColor Green
    exit 0
} else {
    Write-Host "`nUNHEALTHY / timeout. Tail of $log.err:" -ForegroundColor Red
    if (Test-Path "$log.err") { Get-Content "$log.err" -Tail 25 }
    exit 1
}
