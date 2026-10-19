[CmdletBinding()]
param(
    [string]$Root = (Join-Path $env:LOCALAPPDATA 'DSH-Houdini'),
    [string[]]$PackagesDir,
    [string[]]$Versions = @('21.0', '22.0'),
    [switch]$PrintOnly
)
$ErrorActionPreference = 'Stop'
# A parent PowerShell 7 / embedded Python can pass a module path that hides
# Windows PowerShell's own utility module. Change this child process only.
$env:PSModulePath = (Join-Path $PSHOME 'Modules') + [IO.Path]::PathSeparator + $env:PSModulePath
$sourceRoot = Split-Path -Parent $PSScriptRoot
$installRoot = [IO.Path]::GetFullPath($Root)
if ($installRoot.TrimEnd('\') -eq [IO.Path]::GetPathRoot($installRoot).TrimEnd('\') -or
    $installRoot.TrimEnd('\') -eq $env:USERPROFILE.TrimEnd('\')) { throw 'Choose a dedicated installation directory.' }
$documents = [Environment]::GetFolderPath('MyDocuments')
if (-not $PackagesDir) {
    if ($env:HOUDINI_USER_PREF_DIR) {
        if (-not $env:HOUDINI_USER_PREF_DIR.Contains('__HVER__')) { throw 'HOUDINI_USER_PREF_DIR must contain __HVER__; Houdini ignores it otherwise. Use -PackagesDir for an explicit target.' }
        $PackagesDir = @($Versions | ForEach-Object { Join-Path ($env:HOUDINI_USER_PREF_DIR.Replace('__HVER__', $_)) 'packages' } | Select-Object -Unique)
    } else {
        $PackagesDir = @($Versions | ForEach-Object {
            if ($_ -notin @('21.0', '22.0')) { throw "Unsupported Houdini version: $_" }
            Join-Path (Join-Path $documents "houdini$_") 'packages'
        })
    }
}
$files = @{
    'MainMenuCommon.xml' = (Join-Path $PSScriptRoot 'MainMenuCommon.xml')
    'python3.11libs/pythonrc.py' = (Join-Path $PSScriptRoot 'scripts/pythonrc.py')
    'python3.13libs/pythonrc.py' = (Join-Path $PSScriptRoot 'scripts/pythonrc.py')
    'release-trust.json' = (Join-Path $PSScriptRoot 'release-trust.json')
    'scripts/afterscenesave.py' = (Join-Path $sourceRoot 'houdini/scripts/afterscenesave.py')
    'uninstall.ps1' = (Join-Path $PSScriptRoot 'uninstall.ps1')
}
foreach ($name in @('dsh_bootstrap.py', 'dsh_install_ui.py', 'dsh_ui_style.py', 'dsh_deployment.py', 'dsh_release_policy.py', 'dsh_support_ui.py', 'dsh_support_report.py', 'dsh_workbench.py', 'dsh_houdini_installations.py', 'dsh_workbench_start.py')) {
    $files["python/$name"] = Join-Path $sourceRoot "houdini/python3.11libs/$name"
}
$files['open-workbench.ps1'] = Join-Path $PSScriptRoot 'open-workbench.ps1'
$files['dsh-houdini.ico'] = Join-Path $sourceRoot 'assets/dsh-houdini.ico'
foreach ($file in $files.Values) { if (-not (Test-Path -LiteralPath $file -PathType Leaf)) { throw "Installer file missing: $file" } }
$parts = @($files.Keys | Sort-Object | ForEach-Object { $_ + ':' + (Get-FileHash -LiteralPath $files[$_] -Algorithm SHA256).Hash })
$sha = [Security.Cryptography.SHA256]::Create()
try { $bootstrapId = ([BitConverter]::ToString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes(($parts -join "`n"))))).Replace('-', '').Substring(0, 16).ToLowerInvariant() } finally { $sha.Dispose() }
$bootstrap = Join-Path $installRoot "bootstrap/$bootstrapId"
$package = @{
    env = @(@{DSH_HOUDINI_INSTALL_ROOT=$installRoot.Replace('\','/')}, @{PYTHONPATH=($bootstrap.Replace('\','/')+'/python;$PYTHONPATH')})
    path = $bootstrap.Replace('\','/')
}
if ($PrintOnly) { @{root=$installRoot; bootstrap=$bootstrap; targets=$PackagesDir; package=$package} | ConvertTo-Json -Depth 8; return }
New-Item -ItemType Directory -Path $installRoot -Force | Out-Null
$lockPath = Join-Path $installRoot 'bootstrap-install.lock'
$lock = [IO.File]::Open($lockPath, [IO.FileMode]::OpenOrCreate, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
try {
    $validCopy = Test-Path -LiteralPath $bootstrap
    if ($validCopy) {
        foreach ($relative in $files.Keys) {
            $existingFile = Join-Path $bootstrap $relative
            if (-not (Test-Path -LiteralPath $existingFile -PathType Leaf) -or
                (Get-FileHash -LiteralPath $existingFile).Hash -ne (Get-FileHash -LiteralPath $files[$relative]).Hash) { $validCopy = $false; break }
        }
        if (-not $validCopy) {
            $bootstrap = Join-Path $installRoot ('bootstrap/'+$bootstrapId+'-'+[guid]::NewGuid().ToString('N').Substring(0,8))
            $package.path = $bootstrap.Replace('\','/')
            $package.env[1].PYTHONPATH = $package.path + '/python;$PYTHONPATH'
        }
    }
    if (-not (Test-Path -LiteralPath $bootstrap)) {
        New-Item -ItemType Directory -Path $bootstrap -Force | Out-Null
        foreach ($relative in $files.Keys) {
            $destination = Join-Path $bootstrap $relative
            New-Item -ItemType Directory -Path (Split-Path -Parent $destination) -Force | Out-Null
            Copy-Item -LiteralPath $files[$relative] -Destination $destination
        }
    }
    # Verify an interrupted/previous copy instead of trusting directory existence.
    foreach ($relative in $files.Keys) {
        $destination = Join-Path $bootstrap $relative
        if ((Get-FileHash -LiteralPath $destination).Hash -ne (Get-FileHash -LiteralPath $files[$relative]).Hash) {
            throw 'Bootstrap content differs. Preserve the directory and run a trusted installer again.'
        }
    }
    $utf8 = New-Object Text.UTF8Encoding($false)
    $registrationPath = Join-Path $installRoot 'registrations.json'
    $registered = @()
    if (Test-Path -LiteralPath $registrationPath -PathType Leaf) {
        $registered = @((Get-Content -LiteralPath $registrationPath -Encoding UTF8 -Raw | ConvertFrom-Json).packages)
    }
    foreach ($dir in $PackagesDir) {
        $targetDir = [IO.Path]::GetFullPath($dir)
        New-Item -ItemType Directory -Path $targetDir -Force | Out-Null
        $target = Join-Path $targetDir 'dsh-houdini.json'
        $targetExisted = Test-Path -LiteralPath $target
        if ($targetExisted) {
            $backup = Join-Path $installRoot ('package-backups/'+[guid]::NewGuid().ToString()+'.json')
            New-Item -ItemType Directory -Path (Split-Path -Parent $backup) -Force | Out-Null
            # ReplaceFile requires its backup on the target's volume. Documents
            # may be redirected to another drive; make the durable backup first.
            Copy-Item -LiteralPath $target -Destination $backup
        }
        $temp = $target + '.' + [guid]::NewGuid().ToString() + '.tmp'
        [IO.File]::WriteAllText($temp, ($package | ConvertTo-Json -Depth 6), $utf8)
        try {
            if ($targetExisted) {
                [IO.File]::Replace($temp, $target, [NullString]::Value)
                Write-Output "Previous package preserved: $backup"
            } else { [IO.File]::Move($temp, $target) }
        } catch {
            throw "Could not update Houdini registration '$target'. The previous registration and backup were preserved. Check that this file is writable and not locked by another application, then run Install.cmd again. $($_.Exception.Message)"
        } finally {
            if (Test-Path -LiteralPath $temp -PathType Leaf) { Remove-Item -LiteralPath $temp }
        }
        $registered = @(@($registered) + $target | Sort-Object -Unique)
        $registrationTemp = $registrationPath + '.' + [guid]::NewGuid().ToString() + '.tmp'
        [IO.File]::WriteAllText($registrationTemp, (@{packages=@($registered)} | ConvertTo-Json -Depth 4), $utf8)
        if (Test-Path -LiteralPath $registrationPath) {
            [IO.File]::Replace($registrationTemp, $registrationPath, [NullString]::Value)
        } else { [IO.File]::Move($registrationTemp, $registrationPath) }
        Write-Output "Registered: $target"
    }
} finally { $lock.Dispose() }
$shortcutPath = Join-Path $installRoot 'DSH-Houdini.lnk'
$shortcut = (New-Object -ComObject WScript.Shell).CreateShortcut($shortcutPath)
$shortcut.TargetPath = (Join-Path $PSHOME 'powershell.exe')
$shortcut.Arguments = '-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "' + (Join-Path $bootstrap 'open-workbench.ps1') + '" -Root "' + $installRoot + '"'
$shortcut.WorkingDirectory = $installRoot
$shortcut.IconLocation = (Join-Path $bootstrap 'dsh-houdini.ico') + ',0'
$shortcut.WindowStyle = 7
$shortcut.Save()
$uninstallEntry = '@echo off' + "`r`n" + 'setlocal' + "`r`n" + 'powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0bootstrap\' + (Split-Path -Leaf $bootstrap) + '\uninstall.ps1" -Root "%~dp0." %*' + "`r`n" + 'if errorlevel 1 (pause & exit /b 1)' + "`r`n" + 'pause' + "`r`n"
[IO.File]::WriteAllText((Join-Path $installRoot 'Uninstall.cmd'), $uninstallEntry, [Text.Encoding]::ASCII)
Write-Output "Standalone workspace: $shortcutPath"
if (Test-Path -LiteralPath (Join-Path $sourceRoot 'release.json')) {
    # SideFX records the selected install directory even on another drive.
    # Include those registered H21/H22 roots as well as standard folders.
    $houdiniRoots = @(Get-ChildItem -LiteralPath 'HKLM:\SOFTWARE\Side Effects Software' -ErrorAction SilentlyContinue |
        Where-Object PSChildName -Match '^Houdini (21|22)\.0\.' |
        ForEach-Object { (Get-ItemProperty -LiteralPath $_.PSPath -ErrorAction SilentlyContinue).InstallPath })
    $houdiniRoots += @(Get-ChildItem -Path (Join-Path $env:ProgramFiles 'Side Effects Software/Houdini *') -Directory -ErrorAction SilentlyContinue |
        Where-Object Name -Match '^Houdini (21|22)\.0\.' | ForEach-Object FullName)
    $interpreters = @($houdiniRoots | Where-Object { $_ -and (Test-Path -LiteralPath (Join-Path $_ 'bin/houdini.exe') -PathType Leaf) } |
        ForEach-Object { Get-ChildItem -Path (Join-Path $_ 'python*/python.exe') -ErrorAction SilentlyContinue } |
        Sort-Object FullName -Descending -Unique)
    if ($interpreters.Count) {
        # The chosen interpreter must use its own standard library when this
        # installer was launched from another Houdini/Python environment.
        & $interpreters[0].FullName -E (Join-Path $bootstrap 'python/dsh_deployment.py') stage --root $installRoot --trust (Join-Path $bootstrap 'release-trust.json') --directory $sourceRoot
        if ($LASTEXITCODE -ne 0) { throw 'Offline package was not installed. The manager is available for diagnosis.' }
    } else {
        Write-Output 'Open Version & Updates..., expand advanced settings, and choose release.json from this folder as a local package.'
    }
}
Write-Output 'Open Houdini > DSH-Houdini > Version & Updates... to manage installation. System Node/Python were not changed.'
