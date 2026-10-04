<#
Migrate a module off the obsolete platform ICancellationToken (VC0014) to System.Threading.CancellationToken.

Platform 3.1039.0 marks ICancellationToken [Obsolete VC0014]; with TreatWarningsAsErrors any
USE of it fails to build. The platform's IExportSupport/IImportSupport and Hangfire job patterns
now expose a modern CancellationToken overload, so the fix is to use CancellationToken.

Safe blind replacement: only run for modules that do NOT keep an intentional [Obsolete VC0014]
ICancellationToken *shim* overload (verify with: grep VC0014 + ICancellationToken first).

Replaces the identifier ICancellationToken -> CancellationToken in src/**/*.cs and ensures
`using System.Threading;` is present. Does not touch git (caller branches first).

Usage: pwsh migrate_ict.ps1 -Repo vc-module-bulk-actions
#>
param([Parameter(Mandatory = $true)][string]$Repo)
$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\release-config.ps1"
$path = Join-Path (Get-ReleaseConfig).MonorepoRoot $Repo
$changed = 0
# scan both src and tests (test projects are built by the solution too)
Get-ChildItem $path -Recurse -Filter *.cs |
  Where-Object { $_.FullName -notmatch '\\(bin|obj|node_modules)\\' } |
  ForEach-Object {
    $t = Get-Content $_.FullName -Raw
    if ($t -match 'ICancellationToken') {
      # Skip dual-overload shim files: ICancellationToken appears only in [Obsolete VC0014] shim
      # overloads that already have a CancellationToken twin. Converting them creates duplicate
      # signatures (CS0111). They compile as-is (ICancellationToken is kept in the platform).
      if ($t -match 'VC0014' -and $t -match '\[\s*Obsolete') {
        Write-Host "  SKIP (VC0014 shim, compiles as-is): $($_.FullName.Substring($path.Length+1))"
        return
      }
      $t = $t -replace 'ICancellationToken', 'CancellationToken'
      # struct CancellationToken can't use null-conditional; the old interface could
      $t = $t -replace '\?\.ThrowIfCancellationRequested\(\)', '.ThrowIfCancellationRequested()'
      if ($t -notmatch '(?m)^\s*using System\.Threading;\s*$') {
        if ($t -match '(?m)^using System;\s*$') {
          $t = [regex]::Replace($t, '(?m)^(using System;\s*)$', "`$1`r`nusing System.Threading;", 1)
        }
        else {
          $t = "using System.Threading;`r`n" + $t
        }
      }
      Set-Content -Path $_.FullName -Value $t -NoNewline
      $changed++
      Write-Host "  migrated: $($_.FullName.Substring($path.Length+1))"
    }
  }
Write-Host "ICT migration: $changed file(s) in $Repo" -ForegroundColor Green
