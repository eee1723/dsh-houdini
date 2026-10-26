[CmdletBinding()]
param(
    [string]$Root = (Join-Path $env:LOCALAPPDATA 'DSH-Houdini'),
    [string[]]$PackagesDir,
    [string[]]$Versions = @('21.0', '22.0'),
    [string]$SelectHelper,
    [switch]$ListHelpers,
    [switch]$MigrationPreview,
    [string]$RollbackMigration,
    [switch]$PrintOnly
)
$OutputEncoding = New-Object Text.UTF8Encoding($false)
[Console]::OutputEncoding = $OutputEncoding
$ErrorActionPreference = 'Stop'
$env:PSModulePath = (Join-Path $PSHOME 'Modules') + [IO.Path]::PathSeparator + $env:PSModulePath
$sourceRoot = Split-Path -Parent $PSScriptRoot
$installRoot = [IO.Path]::GetFullPath($Root)
if ($installRoot.TrimEnd('\') -eq [IO.Path]::GetPathRoot($installRoot).TrimEnd('\') -or
    $installRoot.TrimEnd('\') -eq $env:USERPROFILE.TrimEnd('\')) { throw 'Choose a dedicated helper installation directory.' }
. (Join-Path $PSScriptRoot 'legacy-migration.ps1')
if ($RollbackMigration) {
    if ($PrintOnly -or $MigrationPreview) { Undo-DshMigration $installRoot $RollbackMigration -Preview | ConvertTo-Json -Depth 8; return }
    $lock = [IO.File]::Open((Join-Path $installRoot 'helper-install.lock'), [IO.FileMode]::OpenOrCreate, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
    try { Undo-DshMigration $installRoot $RollbackMigration } finally { $lock.Dispose() }
    return
}

function Get-HelperFiles([string]$Directory) {
    $items = @{'package.json' = (Join-Path $Directory 'package.json')}
    $houdini = Join-Path $Directory 'houdini'
    foreach ($file in Get-ChildItem -LiteralPath $houdini -File -Recurse) {
        $relative = $file.FullName.Substring($houdini.Length + 1).Replace('\', '/')
        if ($relative -notmatch '(^|/)__pycache__/|\.pyc$') { $items['houdini/' + $relative] = $file.FullName }
    }
    foreach ($relative in @('installer/install.ps1', 'installer/uninstall.ps1', 'installer/legacy-migration.ps1')) {
        $file = Join-Path $Directory $relative
        if (Test-Path -LiteralPath $file -PathType Leaf) { $items[$relative] = $file }
    }
    return $items
}

function Get-HelperIdentity([hashtable]$Items) {
    $parts = @($Items.Keys | Sort-Object | ForEach-Object { $_ + ':' + (Get-FileHash -LiteralPath $Items[$_] -Algorithm SHA256).Hash })
    $sha = [Security.Cryptography.SHA256]::Create()
    try { return ([BitConverter]::ToString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes(($parts -join "`n"))))).Replace('-', '').Substring(0, 16).ToLowerInvariant() }
    finally { $sha.Dispose() }
}

if ($ListHelpers) {
    $rows = @()
    $helperRoot = Join-Path $installRoot 'helpers'
    if (Test-Path -LiteralPath $helperRoot -PathType Container) {
        foreach ($directory in Get-ChildItem -LiteralPath $helperRoot -Directory | Sort-Object LastWriteTime -Descending) {
            if ($directory.Name -notmatch '^[0-9a-f]{16}$') { continue }
            try {
                $identity = Get-HelperIdentity (Get-HelperFiles $directory.FullName)
                $manifest = Get-Content -LiteralPath (Join-Path $directory.FullName 'package.json') -Raw -Encoding UTF8 | ConvertFrom-Json
                $rows += @{id=$directory.Name; version=[string]$manifest.version; path=$directory.FullName; valid=($identity -eq $directory.Name)}
            } catch { $rows += @{id=$directory.Name; path=$directory.FullName; valid=$false; error=$_.Exception.Message} }
        }
    }
    ConvertTo-Json -InputObject @($rows) -Depth 5
    return
}
if ($SelectHelper -and $SelectHelper -notmatch '^[0-9a-f]{16}$') { throw 'SelectHelper must name an installed helper identity from -ListHelpers.' }
if ($SelectHelper -and -not $PackagesDir) {
    $registrations = Join-Path $installRoot 'registrations.json'
    if (-not (Test-Path -LiteralPath $registrations -PathType Leaf)) { throw 'No registered helper targets. Pass -PackagesDir explicitly.' }
    $targets = @((Get-Content -LiteralPath $registrations -Raw -Encoding UTF8 | ConvertFrom-Json).packages)
    if (@($targets | Where-Object { [IO.Path]::GetFileName($_) -ne 'dsh-houdini.json' }).Count) { throw 'The helper registration list is invalid.' }
    $PackagesDir = @($targets | ForEach-Object { Split-Path -Parent $_ } | Select-Object -Unique)
    if (-not $PackagesDir.Count) { throw 'No registered helper targets. Pass -PackagesDir explicitly.' }
}
if (-not $PackagesDir) {
    # Desktop may not inherit the environment of an existing Houdini process.
    # An upgrade must retain custom preferences recorded by the old installer.
    $registrations = Join-Path $installRoot 'registrations.json'
    if (Test-Path -LiteralPath $registrations -PathType Leaf) {
        try {
            $targets = @((Get-Content -LiteralPath $registrations -Raw -Encoding UTF8 | ConvertFrom-Json).packages)
            if (@($targets | Where-Object { [IO.Path]::GetFileName($_) -ine 'dsh-houdini.json' }).Count) { throw 'Invalid recorded package filename.' }
            $PackagesDir = @($targets | ForEach-Object { Split-Path -Parent $_ } | Select-Object -Unique)
        } catch { throw "Cannot read recorded custom preferences; preserved: $registrations. $($_.Exception.Message)" }
    }
}
if (-not $PackagesDir) {
    $PackagesDir = @(Get-DshEnvironmentPackageDirectories)
}
if (-not $PackagesDir) {
    $documents = [Environment]::GetFolderPath('MyDocuments')
    $PackagesDir = @($Versions | ForEach-Object {
        if ($_ -notin @('21.0', '22.0')) { throw "Unsupported Houdini version: $_" }
        if ($env:HOUDINI_USER_PREF_DIR) {
            Join-Path ($env:HOUDINI_USER_PREF_DIR.Replace('__HVER__', $_)) 'packages'
        } else { Join-Path (Join-Path $documents "houdini$_") 'packages' }
    } | Select-Object -Unique)
}
# Only the Houdini package is installed here. Official Desktop owns its own
# plugin package, Node runtime, profiles, Sessions, models, and application UI.
$selectedDirectory = if ($SelectHelper) { Join-Path $installRoot "helpers/$SelectHelper" } else { $sourceRoot }
$files = Get-HelperFiles $selectedDirectory
foreach ($file in $files.Values) {
    if (-not (Test-Path -LiteralPath $file -PathType Leaf)) { throw "Helper file missing: $file" }
}
$helperId = Get-HelperIdentity $files
if ($SelectHelper -and $helperId -ne $SelectHelper) { throw 'Selected helper content differs from its installed identity. Files were preserved; select another version or reinstall it.' }
$helper = Join-Path $installRoot "helpers/$helperId"
$package = @{
    env = @(
        @{DSH_HOUDINI_INSTALL_ROOT=$installRoot.Replace('\','/')},
        @{DSH_HOUDINI_PATH=($helper.Replace('\','/')+'/houdini')},
        @{PYTHONPATH=($helper.Replace('\','/')+'/houdini/python3.11libs;$PYTHONPATH')}
    )
    path = '$DSH_HOUDINI_PATH'
}
$migration = New-DshMigrationPlan $installRoot $PackagesDir ($package | ConvertTo-Json -Depth 6)
if ($SelectHelper) {
    foreach ($directory in $PackagesDir) {
        $target = Join-Path $directory 'dsh-houdini.json'
        if (Test-Path -LiteralPath $target -PathType Leaf) {
            $owner = Get-DshPackageOwner $target
            if ($owner.kind -ne 'unknown' -and -not (Test-DshPathEqual $owner.root $installRoot)) {
                $migration.conflicts += @{path=$target; reason='Version selection cannot replace a registration belonging to another installation.'}
            }
        }
    }
}
if ($PrintOnly -or $MigrationPreview) {
    @{root=$installRoot; helper=$helper; targets=$PackagesDir; package=$package; migration=$migration; desktop='Official DSH Desktop plugin must be installed separately'} | ConvertTo-Json -Depth 12
    return
}
New-Item -ItemType Directory -Path $installRoot -Force | Out-Null
$lock = [IO.File]::Open((Join-Path $installRoot 'helper-install.lock'), [IO.FileMode]::OpenOrCreate, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
try {
    # Unknown entries are rejected before helper copies or preference changes.
    # Invoke writes a concrete report even for a blocked plan.
    if ($migration.conflicts.Count) { Invoke-DshMigration $migration | Out-Null }
    foreach ($relative in $files.Keys) {
        $destination = Join-Path $helper $relative
        if (Test-Path -LiteralPath $destination -PathType Leaf) {
            if ((Get-FileHash -LiteralPath $destination).Hash -ne (Get-FileHash -LiteralPath $files[$relative]).Hash) {
                throw 'An existing helper differs from its content identity. Preserve it and inspect the installation.'
            }
        } else {
            New-Item -ItemType Directory -Path (Split-Path -Parent $destination) -Force | Out-Null
            Copy-Item -LiteralPath $files[$relative] -Destination $destination
        }
    }
    # Match the version picker's complete runtime snapshot, including unknown
    # files in the Houdini tree. Preserve them rather than activating a helper
    # whose name no longer describes the content Houdini would actually load.
    if ((Get-HelperIdentity (Get-HelperFiles $helper)) -ne $helperId) {
        throw "Helper content differs from its immutable identity. Unknown files were preserved; no Package or registrations were changed: $helper"
    }
    $record = Join-Path $installRoot 'registrations.json'
    $registered = @()
    if (Test-Path -LiteralPath $record -PathType Leaf) { $registered = @((Get-Content -LiteralPath $record -Raw -Encoding UTF8 | ConvertFrom-Json).packages) }
    $migrationReport = Invoke-DshMigration $migration
    foreach ($directory in $PackagesDir) {
        $target = Join-Path ([IO.Path]::GetFullPath($directory)) 'dsh-houdini.json'
        $registered = @(@($registered) + $target | Sort-Object -Unique)
        Write-Output "Registered Houdini helper: $target"
    }
    Write-DshAtomicBytes $record ([Text.Encoding]::UTF8.GetBytes((@{packages=@($registered)} | ConvertTo-Json -Depth 4)))
} finally { $lock.Dispose() }
if ($migrationReport) { Write-Output "Reversible entry migration report: $migrationReport" }
foreach ($entry in $migration.preserved) { Write-Output ("Preserved custom entry: "+$entry.path+". "+$entry.reason) }
Write-Output 'Houdini helpers are installed. Restart the affected Houdini to load this version.'
Write-Output 'Save and reopen any Houdini already running the old version. No running Houdini was stopped and no loaded Python modules were replaced.'
Write-Output 'Install and update dsh-houdini through official DSH Desktop. This installer did not change its application, profiles, Sessions, credentials, or dependencies.'
$disabledCount = @($migration.actions | Where-Object { $_.operation -eq 'disable' -or $_.retiredLegacy }).Count
$reviewCount = @($migration.preserved).Count
$message = 'Houdini 组件已安装。请保存并重新打开需要加载新菜单的 Houdini。'
if ($disabledCount) { $message = 'Houdini 组件已安装，旧版入口已停用并保留可恢复备份。请保存并重新打开旧版 Houdini 窗口。' }
if ($reviewCount) { $message += ' 自定义入口保持原样，请查看安装详情。' }
$result = @{ok=$true; helperId=$helperId; helperRoot=$helper; requiresRestart=$true;
    migration=@{reportPath=$migrationReport; disabledCount=$disabledCount; reviewCount=$reviewCount}; message=$message}
Write-Output ('DSH_HOUDINI_INSTALL_RESULT='+($result | ConvertTo-Json -Depth 6 -Compress))
