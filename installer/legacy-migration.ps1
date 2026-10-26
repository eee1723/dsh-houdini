# Shared by installation and removal. This file never starts Houdini or DSH.
# Ownership is the complete registration/stub emitted by released installers,
# not a filename or a substring in a user's script.
function Get-DshFullPath([string]$Path) { return [IO.Path]::GetFullPath($Path).TrimEnd('\', '/') }
function Get-DshEnvironmentPackageDirectories {
    if (-not $env:HOUDINI_PACKAGE_DIR) { return }
    $directories = @()
    foreach ($part in $env:HOUDINI_PACKAGE_DIR.Split([IO.Path]::PathSeparator)) {
        $path = $part.Trim()
        if (-not $path) { continue }
        # IsPathRooted also accepts C:relative and \drive-relative on Windows.
        # Public package search paths must be fully absolute instead.
        if ($path -notmatch '^([a-zA-Z]:[\\/]|\\\\[^\\/]+[\\/][^\\/]+([\\/]|$))') {
            throw "HOUDINI_PACKAGE_DIR entries must be absolute directories; preserved without installation: $path"
        }
        $directories += Get-DshFullPath $path
    }
    if (-not $directories.Count) { throw 'HOUDINI_PACKAGE_DIR contains no absolute directories. No installation was changed.' }
    return @($directories | Select-Object -Unique)
}
function Test-DshPathEqual([string]$Left, [string]$Right) {
    return [string]::Equals((Get-DshFullPath $Left), (Get-DshFullPath $Right), [StringComparison]::OrdinalIgnoreCase)
}
function Get-DshBytesHash([byte[]]$Bytes) {
    $sha = [Security.Cryptography.SHA256]::Create()
    try { return ([BitConverter]::ToString($sha.ComputeHash($Bytes))).Replace('-', '').ToLowerInvariant() }
    finally { $sha.Dispose() }
}
function Get-DshFileHash([string]$Path) { return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant() }
function Test-DshRegularFile([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return $false }
    return -not ((Get-Item -LiteralPath $Path -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)
}
function Get-DshNormalizedText([string]$Path) {
    return [IO.File]::ReadAllText($Path).Replace("`r`n", "`n").TrimEnd("`n")
}
function Get-DshPackageOwner([string]$Path) {
    $unknown = @{kind='unknown'; root=$null; reason='The file differs from a generated DSH-Houdini registration.'; relevant=([IO.Path]::GetFileName($Path) -ieq 'dsh-houdini.json')}
    if (-not (Test-DshRegularFile $Path)) { $unknown.reason='Linked or nonregular files are preserved.'; return $unknown }
    try {
        $package = [IO.File]::ReadAllText($Path) | ConvertFrom-Json
        $values = @{}
        foreach ($row in @($package.env)) {
            foreach ($property in $row.PSObject.Properties) {
                if ($property.Name -in @('DSH_HOUDINI_INSTALL_ROOT','DSH_HOUDINI_PATH')) { $unknown.relevant=$true }
                if ($row.PSObject.Properties.Name.Count -ne 1 -or $values.ContainsKey($property.Name) -or $property.Value -isnot [string]) { return $unknown }
                $values[$property.Name]=$property.Value
            }
        }
        if (@($package.PSObject.Properties.Name | Where-Object { $_ -notin @('env','path') }).Count -or $package.path -isnot [string]) { return $unknown }
        if ($values.Count -eq 2 -and $values.ContainsKey('DSH_HOUDINI_INSTALL_ROOT') -and $values.ContainsKey('PYTHONPATH')) {
            $owner = Get-DshFullPath $values.DSH_HOUDINI_INSTALL_ROOT
            $bootstrap = Get-DshFullPath $package.path
            $relative = $bootstrap.Substring($owner.Length).Replace('\','/')
            if ($relative -match '^/bootstrap/[0-9a-f]{16}(-[0-9a-f]{8})?$' -and
                (Test-DshPathEqual $bootstrap (Join-Path $owner $relative.TrimStart('/'))) -and
                $values.PYTHONPATH.Replace('\','/') -ceq ($bootstrap.Replace('\','/')+'/python;$PYTHONPATH')) {
                return @{kind='legacy-managed'; root=$owner; relevant=$true; reason='Exact managed bootstrap registration used by 0.0.x installers.'}
            }
        }
        if ($package.path -cne '$DSH_HOUDINI_PATH' -or -not $values.ContainsKey('DSH_HOUDINI_PATH')) { return $unknown }
        $houdini = Get-DshFullPath $values.DSH_HOUDINI_PATH
        if ($values.Count -eq 2 -and $values.PYTHONPATH -ceq '$DSH_HOUDINI_PATH/python3.11libs;$PYTHONPATH' -and
            [IO.Path]::GetFileName($houdini) -ieq 'houdini') {
            return @{kind='source'; root=(Split-Path -Parent $houdini); relevant=$true; reason='Exact source-checkout registration emitted by houdini/install.py.'}
        }
        if ($values.Count -eq 3 -and $values.ContainsKey('DSH_HOUDINI_INSTALL_ROOT')) {
            $owner = Get-DshFullPath $values.DSH_HOUDINI_INSTALL_ROOT
            $relative = $houdini.Substring($owner.Length).Replace('\','/')
            if ($relative -match '^/helpers/[0-9a-f]{16}/houdini$' -and
                (Test-DshPathEqual $houdini (Join-Path $owner $relative.TrimStart('/'))) -and
                $values.PYTHONPATH.Replace('\','/') -ceq ($houdini.Replace('\','/')+'/python3.11libs;$PYTHONPATH')) {
                return @{kind='helper'; root=$owner; relevant=$true; reason='Exact immutable Houdini helper registration.'}
            }
        }
    } catch { $unknown.reason='Unreadable or unrecognized JSON; preserved without executing it.' }
    return $unknown
}

function Get-DshLegacyShortcut([string]$Path, [string]$Root) {
    if (-not ('DshHoudini.MigrationShortcut' -as [type])) {
        # The old writer used IShellLinkW to preserve Chinese paths. Read through
        # the same Unicode interface, without Resolve, shell execution or icons.
        Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
using System.Runtime.InteropServices.ComTypes;
using System.Text;
namespace DshHoudini {
 [ComImport, Guid("00021401-0000-0000-C000-000000000046")] class MigrationLink {}
 [ComImport, Guid("000214F9-0000-0000-C000-000000000046"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
 interface IMigrationLink {
  void GetPath([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder path,int count,IntPtr data,uint flags);
  void GetIDList(out IntPtr id); void SetIDList(IntPtr id);
  void GetDescription([Out,MarshalAs(UnmanagedType.LPWStr)] StringBuilder s,int n); void SetDescription([MarshalAs(UnmanagedType.LPWStr)] string s);
  void GetWorkingDirectory([Out,MarshalAs(UnmanagedType.LPWStr)] StringBuilder s,int n); void SetWorkingDirectory([MarshalAs(UnmanagedType.LPWStr)] string s);
  void GetArguments([Out,MarshalAs(UnmanagedType.LPWStr)] StringBuilder s,int n); void SetArguments([MarshalAs(UnmanagedType.LPWStr)] string s);
  void GetHotkey(out short key); void SetHotkey(short key); void GetShowCmd(out int cmd); void SetShowCmd(int cmd);
  void GetIconLocation([Out,MarshalAs(UnmanagedType.LPWStr)] StringBuilder s,int n,out int index); void SetIconLocation([MarshalAs(UnmanagedType.LPWStr)] string s,int index);
  void SetRelativePath([MarshalAs(UnmanagedType.LPWStr)] string s,uint reserved); void Resolve(IntPtr window,uint flags); void SetPath([MarshalAs(UnmanagedType.LPWStr)] string s);
 }
 public static class MigrationShortcut {
  public static string[] Read(string path) {
   object instance=new MigrationLink();
   try { ((IPersistFile)instance).Load(path,0); var link=(IMigrationLink)instance;
    var target=new StringBuilder(32768); var args=new StringBuilder(32768);
    link.GetPath(target,target.Capacity,IntPtr.Zero,4); link.GetArguments(args,args.Capacity);
    return new[]{target.ToString(),args.ToString()};
   } finally { Marshal.FinalReleaseComObject(instance); }
  }
 }
}
'@
    }
    $fields = [DshHoudini.MigrationShortcut]::Read($Path)
    $nativeTargets = @('System32/WindowsPowerShell/v1.0/powershell.exe','SysWOW64/WindowsPowerShell/v1.0/powershell.exe')
    if (-not @($nativeTargets | Where-Object { Test-DshPathEqual $fields[0] (Join-Path $env:SystemRoot $_) }).Count) { return $false }
    $pattern = '^-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "(?<script>[^"\r\n]+)" -Root "(?<root>[^"\r\n]+)"$'
    if ($fields[1] -notmatch $pattern -or -not (Test-DshPathEqual $Matches.root $Root)) { return $false }
    $scriptPath = Get-DshFullPath $Matches.script
    $prefix = (Get-DshFullPath $Root) + '\bootstrap\'
    return $scriptPath.StartsWith($prefix,[StringComparison]::OrdinalIgnoreCase) -and
        $scriptPath.Substring($prefix.Length) -match '^[0-9a-f]{16}(-[0-9a-f]{8})?\\open-workbench\.ps1$'
}

function New-DshDisableAction([string]$Path, [string]$Evidence) {
    return @{operation='disable'; path=(Get-DshFullPath $Path); beforeSha256=(Get-DshFileHash $Path); afterSha256=$null;
        disabledPath=($Path+'.dsh-disabled-'+[guid]::NewGuid().ToString('N')); evidence=$Evidence; state='pending'}
}
function New-DshMigrationPlan([string]$Root, [string[]]$PackagesDir, [string]$PackageJson, [switch]$Uninstall) {
    $rootPath = Get-DshFullPath $Root
    $plan = @{schemaVersion=1; root=$rootPath; purpose=$(if ($Uninstall) {'uninstall'} else {'install'});
        packagesDirs=@($PackagesDir | ForEach-Object { Get-DshFullPath $_ } | Sort-Object -Unique);
        actions=@(); conflicts=@(); preserved=@(); restartRequired=$true;
        note='Save and reopen affected Houdini processes. Loaded old modules cannot be changed safely in place. No running process or private/user data is removed.'}
    $legacyRoots = @($rootPath)
    foreach ($directory in $plan.packagesDirs) {
        $canonical = Join-Path $directory 'dsh-houdini.json'
        $canonicalExists = Test-Path -LiteralPath $canonical
        $canonicalOwned = $false
        $canonicalKind = $null
        if (Test-Path -LiteralPath $directory -PathType Container) {
            foreach ($file in Get-ChildItem -LiteralPath $directory -File -Filter '*.json' -Force) {
                $owner = Get-DshPackageOwner $file.FullName
                if ($owner.kind -eq 'unknown') {
                    if ($owner.relevant) { $plan.conflicts += @{path=$file.FullName; reason=$owner.reason} }
                    continue
                }
                if ($Uninstall -and -not (Test-DshPathEqual $owner.root $rootPath)) { continue }
                if ($owner.kind -eq 'legacy-managed') { $legacyRoots += $owner.root }
                if (-not $Uninstall -and (Test-DshPathEqual $file.FullName $canonical)) { $canonicalOwned=$true; $canonicalKind=$owner.kind; continue }
                $plan.actions += New-DshDisableAction $file.FullName $owner.reason
            }
        }
        if (-not $Uninstall) {
            if ($canonicalExists -and -not $canonicalOwned -and -not @($plan.conflicts | Where-Object { Test-DshPathEqual $_.path $canonical }).Count) {
                $plan.conflicts += @{path=$canonical; reason='The registration is not a regular generated DSH-Houdini file.'}
            }
            if (-not $canonicalExists -or $canonicalOwned) {
                $bytes = [Text.Encoding]::UTF8.GetBytes($PackageJson)
                $before = if ($canonicalExists) { Get-DshFileHash $canonical } else { $null }
                $after = Get-DshBytesHash $bytes
                if ($before -ne $after) {
                    $plan.actions += @{operation='replace'; path=$canonical; beforeSha256=$before; afterSha256=$after;
                        contentBase64=[Convert]::ToBase64String($bytes); retiredLegacy=($canonicalKind -in @('legacy-managed','source'));
                        evidence='Requested standard Houdini helper registration.'; state='pending'}
                }
            }
        }
        # No released installer wrote a Shelf into the user's preferences.
        # Only exact copied startup/menu stubs can be disabled automatically.
        if ($Uninstall) { continue }
        $pref = Split-Path -Parent $directory
        foreach ($relative in @('python3.11libs/pythonrc.py','python3.13libs/pythonrc.py','MainMenuCommon.xml')) {
            $path = Join-Path $pref $relative
            if (-not (Test-DshRegularFile $path)) { continue }
            $text = Get-DshNormalizedText $path
            $known = $text -ceq "# Only capture a small installation-state snapshot at process startup.`n# No hashing, network, process probes, Node or DSH on the GUI thread.`nimport dsh_bootstrap`ndsh_bootstrap.initialize()"
            if ($relative -eq 'MainMenuCommon.xml') {
                # Normalized exact templates from all v0.0.1..v0.0.15 tags.
                $known = (Get-DshBytesHash ([Text.Encoding]::UTF8.GetBytes($text))) -in @(
                    '3f4e679a09d1fee51023aeb0c959401b62b74d7da8c120f5667e75b93dfd8017',
                    '8a96b803f01cdc0a0986dfe984f0b754aad2d5b13fb8b51144b65ab1e7e2c15c')
            }
            if ($known) { $plan.actions += New-DshDisableAction $path 'Exact released private-bootstrap startup/menu stub.' }
            elseif ($text -match '\bdsh_(bootstrap|workbench|launcher)\b') { $plan.preserved += @{path=$path; reason='Custom or mixed startup/menu script; no code was removed.'} }
        }
        $toolbar = Join-Path $pref 'toolbar'
        if (Test-Path -LiteralPath $toolbar -PathType Container) {
            foreach ($file in Get-ChildItem -LiteralPath $toolbar -Filter '*.shelf' -File) {
                if ([IO.File]::ReadAllText($file.FullName) -match '\bdsh_(bootstrap|workbench|launcher)\b') {
                    $plan.preserved += @{path=$file.FullName; reason='User Shelf reference; no released installer owns this file. Preserved.'}
                }
            }
        }
    }
    foreach ($legacyRoot in @($legacyRoots | Sort-Object -Unique)) {
        $shortcut = Join-Path $legacyRoot 'DSH-Houdini.lnk'
        if (Test-DshRegularFile $shortcut) {
            try { $owned = Get-DshLegacyShortcut $shortcut $legacyRoot } catch { $owned=$false }
            if ($owned) { $plan.actions += New-DshDisableAction $shortcut 'Exact private-workbench shortcut target and arguments.' }
            else { $plan.preserved += @{path=$shortcut; reason='Unknown or edited shortcut target; preserved.'} }
        }
        $wrapper = Join-Path $legacyRoot 'Uninstall.cmd'
        if (Test-DshRegularFile $wrapper) {
            $text = Get-DshNormalizedText $wrapper
            if ($text -match '^@echo off\nsetlocal\npowershell\.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0bootstrap\\[0-9a-f]{16}(-[0-9a-f]{8})?\\uninstall\.ps1" -Root "%~dp0\." %\*\nif errorlevel 1 \(pause & exit /b 1\)\npause$') {
                $plan.actions += New-DshDisableAction $wrapper 'Exact released private-bootstrap uninstall wrapper.'
            } else { $plan.preserved += @{path=$wrapper; reason='Unknown or edited uninstall wrapper; preserved.'} }
        }
    }
    return $plan
}

function Write-DshAtomicBytes([string]$Path, [byte[]]$Bytes) {
    New-Item -ItemType Directory -Path (Split-Path -Parent $Path) -Force | Out-Null
    $temporary = $Path+'.'+[guid]::NewGuid().ToString('N')+'.tmp'
    try {
        [IO.File]::WriteAllBytes($temporary,$Bytes)
        if (Test-Path -LiteralPath $Path) { [IO.File]::Replace($temporary,$Path,[NullString]::Value) }
        else { [IO.File]::Move($temporary,$Path) }
    } finally { if (Test-Path -LiteralPath $temporary) { Remove-Item -LiteralPath $temporary } }
}
function Save-DshMigrationReport([hashtable]$Plan, [string]$Report) {
    Write-DshAtomicBytes $Report ([Text.Encoding]::UTF8.GetBytes(($Plan | ConvertTo-Json -Depth 12)))
}
function Assert-DshActionUnchanged($Action) {
    if ($Action.beforeSha256) {
        if (-not (Test-DshRegularFile $Action.path) -or (Get-DshFileHash $Action.path) -ne $Action.beforeSha256) { throw "File changed after preview; preserved: $($Action.path)" }
    } elseif (Test-Path -LiteralPath $Action.path) { throw "A file appeared after preview; preserved: $($Action.path)" }
    if ($Action.operation -eq 'disable' -and (Test-Path -LiteralPath $Action.disabledPath)) { throw "Disable destination already exists; preserved: $($Action.disabledPath)" }
}
function Invoke-DshMigration([hashtable]$Plan) {
    $folder = Join-Path $Plan.root ('migrations/'+[guid]::NewGuid().ToString('N'))
    $report = Join-Path $folder 'report.json'
    $Plan.createdUtc=[DateTime]::UtcNow.ToString('o')
    if ($Plan.conflicts.Count) {
        $Plan.status='blocked'; Save-DshMigrationReport $Plan $report
        throw ("Installation preserved conflicting entries. Review the report; do not delete folders blindly: $report`n" + (($Plan.conflicts | ForEach-Object { $_.path+': '+$_.reason }) -join "`n"))
    }
    if (-not $Plan.actions.Count) { return $null }
    # Check the entire snapshot before the first mutation. Backups are exact
    # bytes, not reserialized JSON, and remain even after rollback.
    foreach ($action in $Plan.actions) { Assert-DshActionUnchanged $action }
    New-Item -ItemType Directory -Path (Join-Path $folder 'files') -Force | Out-Null
    $index=0
    foreach ($action in $Plan.actions) {
        if ($action.beforeSha256) {
            $bytes=[IO.File]::ReadAllBytes($action.path)
            if ((Get-DshBytesHash $bytes) -ne $action.beforeSha256) { throw "File changed before backup; preserved: $($action.path)" }
            $action.backup=('files/'+$index+'.bin'); [IO.File]::WriteAllBytes((Join-Path $folder $action.backup),$bytes)
        }
        $index++
    }
    $Plan.status='applying'; Save-DshMigrationReport $Plan $report
    try {
        foreach ($action in $Plan.actions) {
            Assert-DshActionUnchanged $action
            if ($action.operation -eq 'disable') {
                [IO.File]::Move($action.path,$action.disabledPath)
                if ((Get-DshFileHash $action.disabledPath) -ne $action.beforeSha256) {
                    if (-not (Test-Path -LiteralPath $action.path)) { [IO.File]::Move($action.disabledPath,$action.path) }
                    throw "File changed during disable; retained without replacement: $($action.path)"
                }
            } else { Write-DshAtomicBytes $action.path ([Convert]::FromBase64String($action.contentBase64)) }
            $action.state='applied'; Save-DshMigrationReport $Plan $report
        }
        $Plan.status='applied'; Save-DshMigrationReport $Plan $report
    } catch {
        $Plan.status='incomplete'; $Plan.error=$_.Exception.Message; Save-DshMigrationReport $Plan $report
        throw "Migration stopped; all backups and completed actions are recorded at $report. $($_.Exception.Message)"
    }
    return $report
}

function Undo-DshMigration([string]$Root, [string]$Report, [switch]$Preview) {
    $reportPath=Get-DshFullPath $Report
    $migrationRoot=(Get-DshFullPath $Root)+'\migrations\'
    if (-not $reportPath.StartsWith($migrationRoot,[StringComparison]::OrdinalIgnoreCase) -or
        $reportPath.Substring($migrationRoot.Length) -notmatch '^[0-9a-f]{32}\\report\.json$') { throw 'Select a report created under this installation root/migrations.' }
    $plan=[IO.File]::ReadAllText($reportPath) | ConvertFrom-Json
    if ($plan.schemaVersion -ne 1 -or -not (Test-DshPathEqual $plan.root $Root)) { throw 'Migration report belongs to a different installation.' }
    if ($plan.status -eq 'rolled-back' -or $plan.status -eq 'blocked') { return 'No applied migration remains to restore.' }
    $restore=@()
    foreach ($action in $plan.actions) {
        if ($action.backup) {
            if ($action.backup -notmatch '^files/[0-9]+\.bin$') { throw 'Invalid backup location in report.' }
            $backup=Join-Path (Split-Path -Parent $reportPath) $action.backup
            if (-not (Test-DshRegularFile $backup) -or (Get-DshFileHash $backup) -ne $action.beforeSha256) { throw "Backup checksum differs; preserved: $backup" }
        }
        if ($action.operation -eq 'disable') {
            if (-not (Test-DshPathEqual (Split-Path -Parent $action.path) (Split-Path -Parent $action.disabledPath)) -or
                -not $action.disabledPath.StartsWith($action.path+'.dsh-disabled-',[StringComparison]::OrdinalIgnoreCase)) { throw 'Invalid disabled-file location in report.' }
            if (Test-Path -LiteralPath $action.disabledPath) {
                if ((Test-Path -LiteralPath $action.path) -or -not (Test-DshRegularFile $action.disabledPath) -or (Get-DshFileHash $action.disabledPath) -ne $action.beforeSha256) { throw "Entry changed after migration; rollback preserved it: $($action.path)" }
                $restore += $action
            } elseif (-not (Test-DshRegularFile $action.path) -or (Get-DshFileHash $action.path) -ne $action.beforeSha256) { throw "Entry changed after migration; rollback preserved it: $($action.path)" }
        } elseif ($action.operation -eq 'replace') {
            if ((Test-DshRegularFile $action.path) -and (Get-DshFileHash $action.path) -eq $action.afterSha256) { $restore += $action }
            elseif ($action.beforeSha256) {
                if (-not (Test-DshRegularFile $action.path) -or (Get-DshFileHash $action.path) -ne $action.beforeSha256) { throw "Registration changed after migration; rollback preserved it: $($action.path)" }
            } elseif (Test-Path -LiteralPath $action.path) { throw "Registration changed after migration; rollback preserved it: $($action.path)" }
        } else { throw 'Unknown action in migration report.' }
    }
    if ($Preview) { return @{report=$reportPath; restore=@($restore | Select-Object operation,path); restartRequired=$true} }
    # Preflight above prevents a later edited entry from causing partial rollback.
    for ($index=$restore.Count-1; $index -ge 0; $index--) {
        $action=$restore[$index]
        if ($action.operation -eq 'disable') {
            if ((Test-Path -LiteralPath $action.path) -or (Get-DshFileHash $action.disabledPath) -ne $action.beforeSha256) { throw "Entry changed during rollback; preserved: $($action.path)" }
            [IO.File]::Move($action.disabledPath,$action.path)
        } elseif ($action.beforeSha256) {
            if ((Get-DshFileHash $action.path) -ne $action.afterSha256) { throw "Entry changed during rollback; preserved: $($action.path)" }
            Write-DshAtomicBytes $action.path ([IO.File]::ReadAllBytes((Join-Path (Split-Path -Parent $reportPath) $action.backup)))
        } else {
            if ((Get-DshFileHash $action.path) -ne $action.afterSha256) { throw "Entry changed during rollback; preserved: $($action.path)" }
            [IO.File]::Move($action.path,($action.path+'.dsh-rollback-'+[guid]::NewGuid().ToString('N')))
        }
    }
    $plan.status='rolled-back'
    Write-DshAtomicBytes $reportPath ([Text.Encoding]::UTF8.GetBytes(($plan | ConvertTo-Json -Depth 12)))
    return "Migration restored exact previous entries. Restart affected Houdini. Backups retained: $reportPath"
}
