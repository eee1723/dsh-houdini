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
}
foreach ($name in @('dsh_bootstrap.py', 'dsh_install_ui.py', 'dsh_deployment.py', 'dsh_release_policy.py')) {
    $files["python/$name"] = Join-Path $sourceRoot "houdini/python3.11libs/$name"
}
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
    foreach ($dir in $PackagesDir) {
        $targetDir = [IO.Path]::GetFullPath($dir)
        New-Item -ItemType Directory -Path $targetDir -Force | Out-Null
        $target = Join-Path $targetDir 'dsh-houdini.json'
        $targetExisted = Test-Path -LiteralPath $target
        if ($targetExisted) {
            $backup = Join-Path $installRoot ('package-backups/'+[guid]::NewGuid().ToString()+'.json')
            New-Item -ItemType Directory -Path (Split-Path -Parent $backup) -Force | Out-Null
        }
        $temp = $target + '.' + [guid]::NewGuid().ToString() + '.tmp'
        [IO.File]::WriteAllText($temp, ($package | ConvertTo-Json -Depth 6), $utf8)
        if ($targetExisted) {
            [IO.File]::Replace($temp, $target, $backup)
            Write-Output "Previous package preserved: $backup"
        } else { [IO.File]::Move($temp, $target) }
        Write-Output "Registered: $target"
    }
} finally { $lock.Dispose() }
if (Test-Path -LiteralPath (Join-Path $sourceRoot 'release.json')) {
    $interpreters = @(Get-ChildItem -Path (Join-Path $env:ProgramFiles 'Side Effects Software/Houdini */python*/python.exe') -ErrorAction SilentlyContinue | Sort-Object FullName -Descending)
    if ($interpreters.Count) {
        & $interpreters[0].FullName (Join-Path $bootstrap 'python/dsh_deployment.py') stage --root $installRoot --trust (Join-Path $bootstrap 'release-trust.json') --directory $sourceRoot
        if ($LASTEXITCODE -ne 0) { throw 'Offline package was not installed. The manager is available for diagnosis.' }
    } else {
        Write-Output 'Open Version & Diagnostics and use Install local package to select release.json from this folder.'
    }
}
Write-Output 'Open Houdini > DSH-Houdini > Version & Diagnostics. System Node/Python were not changed.'
