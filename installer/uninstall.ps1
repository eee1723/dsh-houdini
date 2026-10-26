[CmdletBinding()]
param(
    [string]$Root = (Join-Path $env:LOCALAPPDATA 'DSH-Houdini'),
    [string[]]$PackagesDir,
    [switch]$MigrationPreview,
    [string]$RollbackMigration,
    [switch]$PrintOnly
)
$OutputEncoding = New-Object Text.UTF8Encoding($false)
[Console]::OutputEncoding = $OutputEncoding
$ErrorActionPreference = 'Stop'
$env:PSModulePath = (Join-Path $PSHOME 'Modules') + [IO.Path]::PathSeparator + $env:PSModulePath
$installRoot = [IO.Path]::GetFullPath($Root).TrimEnd('\', '/')
if ($installRoot -eq [IO.Path]::GetPathRoot($installRoot).TrimEnd('\') -or
    $installRoot -eq $env:USERPROFILE.TrimEnd('\')) { throw 'Choose a dedicated installation directory.' }
. (Join-Path $PSScriptRoot 'legacy-migration.ps1')
if ($RollbackMigration) {
    if ($PrintOnly -or $MigrationPreview) { Undo-DshMigration $installRoot $RollbackMigration -Preview | ConvertTo-Json -Depth 8; return }
    $lock = [IO.File]::Open((Join-Path $installRoot 'helper-install.lock'), [IO.FileMode]::OpenOrCreate, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
    try { Undo-DshMigration $installRoot $RollbackMigration } finally { $lock.Dispose() }
    return
}

$directories = @($PackagesDir)
$registrationPath = Join-Path $installRoot 'registrations.json'
if (Test-Path -LiteralPath $registrationPath -PathType Leaf) {
    try {
        $record = [IO.File]::ReadAllText($registrationPath) | ConvertFrom-Json
        foreach ($target in @($record.packages)) {
            if ([IO.Path]::GetFileName($target) -ine 'dsh-houdini.json') { throw 'Invalid recorded package filename.' }
            $directories += Split-Path -Parent $target
        }
    } catch { throw "Cannot read recorded custom preferences; no entries were removed: $registrationPath. $($_.Exception.Message)" }
}
# Explicit/recorded preferences suffice. Only installations predating the
# registration list need standard or HOUDINI_USER_PREF_DIR discovery.
if (-not $directories.Count) {
    $directories = @(Get-DshEnvironmentPackageDirectories)
}
if (-not $directories.Count) {
    foreach ($version in @('21.0','22.0')) {
        if ($env:HOUDINI_USER_PREF_DIR) {
            $directories += Join-Path ($env:HOUDINI_USER_PREF_DIR.Replace('__HVER__',$version)) 'packages'
        } else {
            $directories += Join-Path (Join-Path ([Environment]::GetFolderPath('MyDocuments')) "houdini$version") 'packages'
        }
    }
}
$directories = @($directories | Where-Object { $_ } | ForEach-Object { Get-DshFullPath $_ } | Sort-Object -Unique)
$migration = New-DshMigrationPlan $installRoot $directories '' -Uninstall
if ($PrintOnly -or $MigrationPreview) {
    @{root=$installRoot; migration=$migration; preserve='All helper/runtime files, credentials, sessions, projects, unknown entries and official Desktop'} | ConvertTo-Json -Depth 12
    return
}
New-Item -ItemType Directory -Path $installRoot -Force | Out-Null
$lock = [IO.File]::Open((Join-Path $installRoot 'helper-install.lock'), [IO.FileMode]::OpenOrCreate, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
try { $report = Invoke-DshMigration $migration } finally { $lock.Dispose() }
if ($report) { Write-Output "Reversible unregister report: $report" }
foreach ($entry in $migration.preserved) { Write-Output ("Preserved custom entry: "+$entry.path+". "+$entry.reason) }
Write-Output 'DSH-Houdini has been unregistered. Save and restart affected Houdini to remove its menu.'
Write-Output "All helper files and earlier installation data were retained at: $installRoot"
Write-Output 'No Houdini process was stopped. Projects and official DSH Desktop were not changed. Manage the Desktop plugin in its own plugin settings.'
