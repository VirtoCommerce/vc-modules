<#
Shared loader for release.config.json (PowerShell side).

Dot-source it, then call Get-ReleaseConfig to get a normalized object with the
per-release values + resolved local paths. Keeps release_module.ps1 / migrate_ict.ps1 /
update-to-stable.ps1 free of hardcoded version/branch/path constants.

    . "$PSScriptRoot\release-config.ps1"
    $cfg = Get-ReleaseConfig
    $cfg.PlatformVersion ; $cfg.Branch ; $cfg.MonorepoRoot ; $cfg.LocalNugetPath ; $cfg.ArtifactStagingPath
#>

function Get-ReleaseConfig {
    param(
        # Explicit path; otherwise search: caller dir, then src.
        [string]$ConfigPath
    )

    if (-not $ConfigPath) {
        $candidates = @(
            (Join-Path $PSScriptRoot 'release.config.json'),                 # src (this helper's dir)
            (Join-Path (Get-Location) 'release.config.json'),
            (Join-Path $PSScriptRoot '..\src\release.config.json')           # e.g. when called from bundles/v{n}
        )
        $ConfigPath = $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
    }
    if (-not $ConfigPath -or -not (Test-Path $ConfigPath)) {
        throw "release.config.json not found (looked in src, current dir). Pass -ConfigPath."
    }

    $c = Get-Content $ConfigPath -Raw | ConvertFrom-Json
    $jira = $c.jiraTicket
    $branch = if ($c.branch) { $c.branch } else { "feat/$jira-stable-$($c.version)" }
    $localNuget = if ($c.localNugetPath) { $c.localNugetPath } else { Join-Path $c.monorepoRoot 'local-nuget' }
    $sandbox = $c.sandboxRoot
    $healthUrl = if ($c.healthUrl) { $c.healthUrl } else { 'https://localhost:5001/health' }

    [pscustomobject]@{
        Version             = [int]$c.version
        PrevVersion         = [int]$c.prevVersion
        PlatformVersion     = $c.platformVersion
        ThemeVersion        = $c.themeVersion
        JiraTicket          = $jira
        Branch              = $branch
        MonorepoRoot        = $c.monorepoRoot
        LocalNugetPath      = $localNuget
        ArtifactStagingPath = $c.artifactStagingPath
        SandboxRoot         = $sandbox
        SrcPath             = if ($sandbox) { Join-Path $sandbox 'src' } else { $null }
        RuntimePath         = if ($sandbox) { Join-Path $sandbox 'runtime' } else { $null }
        HealthUrl           = $healthUrl
        ConfigPath          = $ConfigPath
    }
}
