<#
Stable-15 per-module release orchestrator (LOCAL-FIRST, no pushes).

Runs the mechanical per-module flow for ONE module repo:
  1. checkout dev, pull, branch feat/VCST-5163-stable-15
  2. write a LOCAL-ONLY nuget.config mapping every VirtoCommerce.* package already present
     in local-nuget (Platform + earlier waves) to the local feed; rest from nuget.org
  3. bump platform PackageReference + module.manifest <platformVersion> to -PlatformVersion
  4. bump inter-module dependency versions (manifest + csproj) per -Deps map
  5. dotnet restore --force + build (verify compile against local-nuget)
  6. npm audit fix on each *.Web project that has a package-lock.json
  7. vc-build Compress -skip Test  -> artifacts\<Id>_<ver>.zip
  8. dotnet pack -o local-nuget    -> publish module packages for downstream waves

Obsolete-code removal is NOT done here (module-specific, see obsolete_removal_audit.md);
run this only for modules whose removals are already applied or that have none.

Usage:
  pwsh release_module.ps1 -Repo vc-module-assets -PlatformVersion 3.1039.0
  pwsh release_module.ps1 -Repo vc-module-x-cart -PlatformVersion 3.1039.0 -Deps @{ 'VirtoCommerce.Cart'='3.1006.0' }
#>
param(
  [Parameter(Mandatory = $true)][string]$Repo,
  [string]$PlatformVersion,
  [hashtable]$Deps = @{},
  [string]$Branch,
  [switch]$SkipCompress
)
$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\release-config.ps1"
$cfg = Get-ReleaseConfig                                   # defaults from release.config.json
if (-not $PlatformVersion) { $PlatformVersion = $cfg.PlatformVersion }
if (-not $Branch) { $Branch = $cfg.Branch }
$root = $cfg.MonorepoRoot
$feed = $cfg.LocalNugetPath
$path = Join-Path $root $Repo
function Step($m) { Write-Host "`n=== [$Repo] $m ===" -ForegroundColor Cyan }

if (-not (Test-Path $path)) { throw "Repo not found: $path" }
Set-Location $path

Step 'git: dev + branch'
$cur = (git rev-parse --abbrev-ref HEAD).Trim()
if ($cur -eq $Branch) {
  Write-Host "already on $Branch — preserving working tree (no reset)"
}
else {
  git checkout dev 2>&1 | Out-Null
  git pull --ff-only 2>&1 | Out-Null
  git checkout -B $Branch 2>&1 | Out-Null
}
Write-Host ("branch = " + (git rev-parse --abbrev-ref HEAD))

Step 'nuget.config (local-only) from local-nuget contents'
# every VirtoCommerce.* id present in local-nuget -> resolve from local feed
$ids = Get-ChildItem $feed -Filter '*.nupkg' | ForEach-Object {
  ($_.BaseName -replace '\.\d+\.\d+\.\d+.*$', '')
} | Sort-Object -Unique | Where-Object { $_ -like 'VirtoCommerce.*' }
$patterns = ($ids | ForEach-Object { "      <package pattern=`"$_`" />" }) -join "`n"
@"
<?xml version="1.0" encoding="utf-8"?>
<configuration>
  <packageSources>
    <clear />
    <add key="local-platform" value="..\local-nuget" />
    <add key="nuget.org" value="https://api.nuget.org/v3/index.json" />
  </packageSources>
  <packageSourceMapping>
    <packageSource key="local-platform">
$patterns
    </packageSource>
    <packageSource key="nuget.org">
      <package pattern="*" />
    </packageSource>
  </packageSourceMapping>
</configuration>
"@ | Set-Content -Encoding UTF8 (Join-Path $path 'nuget.config')
$ex = Join-Path $path '.git\info\exclude'
if (-not (Select-String -Path $ex -Pattern '^nuget\.config$' -Quiet -ErrorAction SilentlyContinue)) {
  Add-Content $ex 'nuget.config'
}

Step "bump platform + inter-module deps (csproj from local-nuget; manifest from -Deps)"
# packageId -> max STABLE version available in local-nuget (the versions we are releasing)
$pkgVer = @{}
Get-ChildItem $feed -Filter '*.nupkg' | ForEach-Object {
  if ($_.BaseName -match '^(VirtoCommerce\..+?)\.(\d+\.\d+\.\d+)(-.*)?$') {
    $id = $Matches[1]; $ver = $Matches[2]; $pre = $Matches[3]
    if (-not $pre) {
      if (-not $pkgVer.ContainsKey($id) -or [version]$ver -gt [version]$pkgVer[$id]) { $pkgVer[$id] = $ver }
    }
  }
}
# scan src AND tests for csproj package refs (MatchVersions checks test projects too)
$csprojs = Get-ChildItem $path -Recurse -Filter *.csproj | Where-Object { $_.FullName -notmatch '\\(bin|obj)\\' }
$manifests = Get-ChildItem (Join-Path $path 'src') -Recurse -Filter module.manifest
$evaluator = {
  param($m)
  $id = $m.Groups[2].Value
  if ($pkgVer.ContainsKey($id)) { $m.Groups[1].Value + $pkgVer[$id] + $m.Groups[3].Value } else { $m.Value }
}
foreach ($f in $csprojs) {
  $t = Get-Content $f.FullName -Raw
  # bump any VirtoCommerce.* PackageReference whose package exists in local-nuget (platform + earlier waves)
  $t = [regex]::Replace($t, '(<PackageReference\s+Include="(VirtoCommerce\.[A-Za-z0-9.]+)"\s+Version=")[^"]+(")', $evaluator)
  Set-Content -Path $f.FullName -Value $t -NoNewline
}
foreach ($f in $manifests) {
  $t = Get-Content $f.FullName -Raw
  $t = [regex]::Replace($t, '<platformVersion>[^<]+</platformVersion>', "<platformVersion>$PlatformVersion</platformVersion>")
  foreach ($k in $Deps.Keys) {
    $t = [regex]::Replace($t, "(<dependency id=`"$([regex]::Escape($k))`" version=`")[^`"]+(`")", "`${1}$($Deps[$k])`$2")
  }
  Set-Content -Path $f.FullName -Value $t -NoNewline
}

Step 'restore + build'
$sln = (Get-ChildItem $path -Filter *.sln | Select-Object -First 1).FullName
dotnet restore $sln --force 2>&1 | Select-Object -Last 2
dotnet build $sln -c Debug --no-restore -clp:ErrorsOnly 2>&1 | Tee-Object -Variable buildOut | Select-Object -Last 15
if ($LASTEXITCODE -ne 0) { throw "BUILD FAILED for $Repo" }

Step 'npm audit fix (Web projects with lockfile)'
Get-ChildItem (Join-Path $path 'src') -Recurse -Filter package-lock.json |
  Where-Object { $_.DirectoryName -notmatch 'node_modules|\\bin\\|\\obj\\' } |
  ForEach-Object {
    Write-Host "  audit fix: $($_.DirectoryName)"
    Push-Location $_.DirectoryName
    npm audit fix 2>&1 | Select-Object -Last 3
    Pop-Location
  }

if (-not $SkipCompress) {
  Step 'vc-build Compress -skip Test'
  vc-build Compress -skip Test 2>&1 | Select-String -Pattern 'Succeeded|Failed|Build succeeded|error|\.zip' | Select-Object -Last 20
  if ($LASTEXITCODE -ne 0) { throw "COMPRESS FAILED for $Repo" }
}

Step 'pack -> local-nuget'
# NOTE: no --no-build — vc-build Compress runs Clean and would starve a --no-build pack.
dotnet pack $sln -c Debug -o $feed -p:NuGetAudit=false --nologo 2>&1 |
  Select-String -Pattern 'Successfully created|error' | Select-Object -Last 12

$ver = (Select-String -Path (Join-Path $path 'Directory.Build.props') -Pattern '<VersionPrefix>([^<]+)' | Select-Object -First 1).Matches.Groups[1].Value
$zip = Get-ChildItem (Join-Path $path 'artifacts') -Filter '*.zip' -ErrorAction SilentlyContinue | Sort-Object LastWriteTime | Select-Object -Last 1

# Stage the artifact in the demo folder for local testing (one copy per module).
$demo = $cfg.ArtifactStagingPath
if ($zip -and (Test-Path $demo)) {
  Copy-Item $zip.FullName $demo -Force
  Write-Host "staged -> $demo\$($zip.Name)"
}

Write-Host "`nDONE $Repo  version=$ver  artifact=$($zip.Name)" -ForegroundColor Green
