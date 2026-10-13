<#
.SYNOPSIS
    Update a Virto Commerce solution or custom module to a target Stable bundle.
    Platform version defaults from src/release.config.json (maintainer) or the value
    pinned below, and is overridable with -PlatformVersion.

.DESCRIPTION
    Performs the MECHANICAL, idempotent version bumps required to move to Stable 16:

      * VirtoCommerce.Platform.*  PackageReference  -> -PlatformVersion (default 3.1076.0)
      * VirtoCommerce.Platform.Hangfire             -> NOT bumped (retired; no 3.1076.0). Reported as "REMOVE" so
                                                       you migrate to the Platform.Core job API - see update_path.md
      * Other VirtoCommerce.*     PackageReference  -> the Stable 16 version of that package
                                                       (from -ModuleVersions, else latest stable on the feed)
      * module.manifest  <platformVersion>          -> -PlatformVersion
      * module.manifest  <dependency version=...>   -> the Stable 16 bundle version of that module
                                                       (package.json next to this script, or -BundleUrl)
      * module.manifest  <version>                  -> bumped (only with -BumpManifestVersion, for module authors)
      * <TargetFramework>                           -> net10.0 (only with -UpdateTargetFramework, i.e. coming from < .NET 10)

    It does NOT modify your C#. The code-level breaking changes (the Hangfire -> Platform.Core job API
    migration, the expired obsoletes removed in VCST-5901, the new VC0015 IIndexingJobService async
    methods) are listed in update_path.md and breaking_changes.md and must be applied by hand, then
    verified with a build.

    Improvements over the original vc-net10-update.ps1:
      - Per-module (non-uniform) target versions instead of one hardcoded VersionPrefix.
      - -DryRun preview that writes nothing.
      - Handles BOTH attribute (Version="..") and child-element (<Version>..</Version>) PackageReferences.
      - Scans src AND tests; preserves original XML formatting/whitespace.
      - Pins Platform.* independently from module packages; never forces a framework change.
      - Resolved-version cache + end-of-run change summary.

.PARAMETER Path
    Root folder to scan (recurses *.csproj and module.manifest). Default: current directory.

.PARAMETER PlatformVersion
    Target platform version applied to all VirtoCommerce.Platform.* references and <platformVersion>.
    Default: 3.1076.0.

.PARAMETER ModuleVersions
    Optional hashtable of explicit id -> version overrides (authoritative; wins over the bundle and the feed).
    Keys are NuGet package ids (VirtoCommerce.CatalogModule.Core) and/or module ids (VirtoCommerce.Catalog).

.PARAMETER BundleUrl
    Stable 16 bundle used for module.manifest <dependency> versions when package.json is not next to this
    script. Pass an empty string to skip the bundle and resolve module ids from the feed.

.PARAMETER NuGetSource
    Feed used to resolve module package versions when not in -ModuleVersions. Default: nuget.org (v2).

.PARAMETER BumpManifestVersion
    Also bump <module><version> in module.manifest. For MODULE AUTHORS cutting their own release; a
    solution-only consumer should leave this off.

.PARAMETER ManifestVersion
    The version to write with -BumpManifestVersion. If omitted, the manifest <version> is left as-is.

.PARAMETER UpdateTargetFramework
    Set <TargetFramework> to -TargetFramework. Only needed when migrating from a pre-.NET 10 line; if
    you are already on .NET 10 (platform >= 3.1000) leave this off.

.PARAMETER TargetFramework
    Framework moniker for -UpdateTargetFramework. Default: net10.0.

.PARAMETER DryRun
    Preview every change without writing any file.

.EXAMPLE
    # Preview, resolving module versions from nuget.org
    ./update-to-stable.ps1 -Path C:\src\my-solution -DryRun

.EXAMPLE
    # Apply with explicit Stable versions (recommended - deterministic)
    $v = @{ 'VirtoCommerce.CatalogModule.Core'='3.1048.0'; 'VirtoCommerce.CatalogModule.Data'='3.1048.0' }
    ./update-to-stable.ps1 -Path . -ModuleVersions $v
#>
[CmdletBinding()]
param(
    [string]   $Path = ".",
    [string]   $PlatformVersion = "",
    [hashtable]$ModuleVersions = @{},
    [string]   $BundleUrl = "https://raw.githubusercontent.com/VirtoCommerce/vc-modules/master/bundles/v16/package.json",
    [string]   $NuGetSource = "https://www.nuget.org/api/v2",
    [switch]   $BumpManifestVersion,
    [string]   $ManifestVersion,
    [switch]   $UpdateTargetFramework,
    [string]   $TargetFramework = "net10.0",
    [switch]   $DryRun
)

$ErrorActionPreference = "Stop"

# Resolve the target platform version: -PlatformVersion wins; else the maintainer's
# src/release.config.json (when present); else the value pinned here for consumers
# who run this script standalone from a bundle folder.
if (-not $PlatformVersion) {
    $cfgPath = Join-Path $PSScriptRoot "..\..\src\release.config.json"
    if (Test-Path $cfgPath) {
        $PlatformVersion = (Get-Content $cfgPath -Raw | ConvertFrom-Json).platformVersion
    }
    if (-not $PlatformVersion) { $PlatformVersion = "3.1076.0" }   # pinned: Stable 16
}
$script:changes = New-Object System.Collections.Generic.List[object]
$script:resolved = @{}
$script:hangfireRefs = New-Object System.Collections.Generic.List[string]

# Module id -> Stable 16 version, for module.manifest <dependency> entries. The bundle's package.json ships next to
# this script; otherwise it is downloaded from -BundleUrl. -ModuleVersions still wins over it.
$script:bundleVersions = @{}
$bundleFile = Join-Path $PSScriptRoot "package.json"
try {
    $bundle = if (Test-Path $bundleFile) { Get-Content $bundleFile -Raw | ConvertFrom-Json }
              elseif ($BundleUrl) { Invoke-RestMethod $BundleUrl }
    if ($bundle) {
        ($bundle.Sources | Where-Object Name -eq 'GithubReleases').Modules |
            ForEach-Object { $script:bundleVersions[$_.Id] = $_.Version }
    }
} catch {
    Write-Host "  ! could not load the Stable 16 bundle ($($_.Exception.Message)) - manifest dependencies resolve from the feed" -ForegroundColor Yellow
}

function Load-Xml($filePath) {
    $doc = New-Object System.Xml.XmlDocument
    $doc.PreserveWhitespace = $true
    $doc.Load($filePath)
    return $doc
}

function Save-Xml($xml, $filePath) {
    if ($DryRun) { return }
    $settings = New-Object System.Xml.XmlWriterSettings
    $settings.Indent = $true
    $settings.Encoding = New-Object System.Text.UTF8Encoding($false)   # UTF-8, no BOM
    $settings.OmitXmlDeclaration = $filePath.EndsWith(".csproj")        # csproj has no XML declaration
    $writer = [System.Xml.XmlWriter]::Create($filePath, $settings)
    try { $xml.Save($writer) } finally { $writer.Close() }
}

function Record($file, $name, $old, $new) {
    if ($old -eq $new) { return }
    $script:changes.Add([pscustomobject]@{ File = (Split-Path $file -Leaf); Item = $name; From = $old; To = $new })
    Write-Host ("  {0,-45} {1,14}  ->  {2}" -f $name, $old, $new) -ForegroundColor Gray
}

# Resolve the Stable 16 version for a VirtoCommerce.* package id.
function Resolve-VcVersion($packageId) {
    if ($packageId -eq "VirtoCommerce.Platform.Hangfire") { return $null }   # retired: reported, never bumped
    if ($packageId -like "VirtoCommerce.Platform*") { return $PlatformVersion }
    if ($ModuleVersions.ContainsKey($packageId))    { return $ModuleVersions[$packageId] }
    if ($script:resolved.ContainsKey($packageId))   { return $script:resolved[$packageId] }

    $version = $null
    try {
        $pkg = Find-Package -Name $packageId -Source $NuGetSource -AllVersions -ErrorAction Stop |
               Where-Object { $_.Version -notmatch '-' } |                       # stable only
               Sort-Object { [version]($_.Version) } -Descending |
               Select-Object -First 1
        if ($pkg) { $version = $pkg.Version }
    } catch { }

    $script:resolved[$packageId] = $version
    if (-not $version) {
        Write-Host "  ! could not resolve $packageId from feed - left unchanged (add it to -ModuleVersions)" -ForegroundColor Yellow
    }
    return $version
}

# Read a PackageReference's version from either the attribute or the child element form.
function Get-PkgVersion($node) {
    if ($node.HasAttribute("Version")) { return @{ kind = "attr"; value = $node.GetAttribute("Version") } }
    $child = $node.SelectSingleNode("Version")
    if ($child) { return @{ kind = "elem"; value = $child.InnerText } }
    return $null   # CPM (Directory.Packages.props) - no inline version
}

function Set-PkgVersion($node, $info, $value) {
    if ($info.kind -eq "attr") { $node.SetAttribute("Version", $value) }
    else { $node.SelectSingleNode("Version").InnerText = $value }
}

function Update-Csproj($file) {
    Write-Host ("`n{0}" -f $file) -ForegroundColor Cyan
    $xml = Load-Xml $file
    $dirty = $false

    if ($UpdateTargetFramework) {
        foreach ($pg in $xml.Project.PropertyGroup) {
            $tf = $pg.SelectSingleNode("TargetFramework")
            if ($tf -and $tf.InnerText -ne $TargetFramework) {
                Record $file "TargetFramework" $tf.InnerText $TargetFramework
                $tf.InnerText = $TargetFramework; $dirty = $true
            }
        }
    }

    foreach ($pr in $xml.SelectNodes("//PackageReference")) {
        $id = $pr.GetAttribute("Include"); if (-not $id) { $id = $pr.GetAttribute("Update") }
        if ($id -notlike "VirtoCommerce.*") { continue }
        if ($id -eq "VirtoCommerce.Platform.Hangfire") {
            $script:hangfireRefs.Add($file)
            Write-Host "  ! VirtoCommerce.Platform.Hangfire is retired in Stable 16 - REMOVE it and migrate (update_path.md)" -ForegroundColor Yellow
            continue
        }
        $info = Get-PkgVersion $pr; if (-not $info) { continue }   # version managed centrally
        $target = Resolve-VcVersion $id
        if ($target -and $info.value -ne $target) {
            Record $file $id $info.value $target
            Set-PkgVersion $pr $info $target; $dirty = $true
        }
    }

    if ($dirty) { Save-Xml $xml $file }
}

function Update-Manifest($file) {
    Write-Host ("`n{0}" -f $file) -ForegroundColor Cyan
    $xml = Load-Xml $file
    $m = $xml.module

    if ($m.platformVersion -and $m.platformVersion -ne $PlatformVersion) {
        Record $file "platformVersion" $m.platformVersion $PlatformVersion
        $m.platformVersion = $PlatformVersion
    }
    if ($BumpManifestVersion -and $ManifestVersion -and $m.version -ne $ManifestVersion) {
        Record $file "version" $m.version $ManifestVersion
        $m.version = $ManifestVersion
    }
    foreach ($dep in $xml.GetElementsByTagName("dependency")) {
        $depId = $dep.GetAttribute("id")
        # manifest dependency ids are module ids (VirtoCommerce.Catalog): -ModuleVersions, then the bundle, then the feed
        $target = if ($ModuleVersions.ContainsKey($depId)) { $ModuleVersions[$depId] }
                  elseif ($script:bundleVersions.ContainsKey($depId)) { $script:bundleVersions[$depId] }
                  else { Resolve-VcVersion $depId }
        if ($target -and $dep.GetAttribute("version") -ne $target) {
            Record $file ("dependency " + $depId) $dep.GetAttribute("version") $target
            $dep.SetAttribute("version", $target)
        }
    }
    Save-Xml $xml $file
}

# ---- main ----
$root = (Resolve-Path $Path).Path
Write-Host "Stable 16 update  (platform $PlatformVersion)$(if($DryRun){'  [DRY RUN]'})" -ForegroundColor Green
Write-Host "Root: $root"
Write-Host ("Bundle: {0} module version(s) loaded" -f $script:bundleVersions.Count)

Get-ChildItem -Path $root -Recurse -Filter *.csproj |
    Where-Object { $_.FullName -notmatch '[\\/](bin|obj|artifacts)[\\/]' } |
    ForEach-Object { Update-Csproj $_.FullName }

Get-ChildItem -Path $root -Recurse -Filter module.manifest |
    Where-Object { $_.FullName -notmatch '[\\/](bin|obj|artifacts)[\\/]' } |
    ForEach-Object { Update-Manifest $_.FullName }

Write-Host "`n================ SUMMARY ================" -ForegroundColor Green
if ($script:changes.Count -eq 0) {
    Write-Host "No changes (already on Stable 16, or nothing matched)."
} else {
    $script:changes | Format-Table -AutoSize
    Write-Host ("{0} change(s){1}." -f $script:changes.Count, $(if($DryRun){' would be applied (dry run)'}else{' applied'}))
}
if ($script:hangfireRefs.Count -gt 0) {
    Write-Host "`nVirtoCommerce.Platform.Hangfire is still referenced (retired in Stable 16, no 3.1076.0) - remove it and migrate:" -ForegroundColor Yellow
    $script:hangfireRefs | Sort-Object -Unique | ForEach-Object { Write-Host "  $_" -ForegroundColor Yellow }
}
Write-Host "`nNext: apply the code-level breaking changes in update_path.md, then rebuild and run the test suite." -ForegroundColor Green
