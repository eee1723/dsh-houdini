[CmdletBinding()]
param(
    [string]$Root = (Join-Path $env:LOCALAPPDATA 'DSH-Houdini'),
    [string[]]$PackagesDir,
    [switch]$PrintOnly
)
$ErrorActionPreference = 'Stop'
$env:PSModulePath = (Join-Path $PSHOME 'Modules') + [IO.Path]::PathSeparator + $env:PSModulePath
$installRoot = [IO.Path]::GetFullPath($Root).TrimEnd('\', '/')
if ($installRoot -eq [IO.Path]::GetPathRoot($installRoot).TrimEnd('\') -or
    $installRoot -eq $env:USERPROFILE.TrimEnd('\')) { throw 'Choose a dedicated installation directory.' }

# The recorded targets cover custom preferences. Standard locations also cover
# installations made before target recording was introduced or after a partial
# manual deletion. Actual package content remains the ownership check.
$targets = @()
$incomplete = @()
$registrationPath = Join-Path $installRoot 'registrations.json'
if (Test-Path -LiteralPath $registrationPath -PathType Leaf) {
    try { $targets += @((Get-Content -LiteralPath $registrationPath -Encoding UTF8 -Raw | ConvertFrom-Json).packages) }
    catch {
        $incomplete += "Could not read recorded preferences '$registrationPath'. Standard locations were checked; custom preferences may need -PackagesDir. $($_.Exception.Message)"
    }
}
$documents = [Environment]::GetFolderPath('MyDocuments')
foreach ($version in @('21.0', '22.0')) {
    $targets += Join-Path (Join-Path (Join-Path $documents "houdini$version") 'packages') 'dsh-houdini.json'
    if ($env:HOUDINI_USER_PREF_DIR -and $env:HOUDINI_USER_PREF_DIR.Contains('__HVER__')) {
        $targets += Join-Path (Join-Path ($env:HOUDINI_USER_PREF_DIR.Replace('__HVER__', $version)) 'packages') 'dsh-houdini.json'
    }
}
foreach ($directory in $PackagesDir) { $targets += Join-Path ([IO.Path]::GetFullPath($directory)) 'dsh-houdini.json' }
$targets = @($targets | Where-Object { $_ } | Sort-Object -Unique)
if ($PrintOnly) { @{root=$installRoot; targets=$targets; preserve='All installation files, credentials, sessions and projects'} | ConvertTo-Json -Depth 4; return }
if (-not (Test-Path -LiteralPath $installRoot -PathType Container)) {
    Write-Output 'Installation directory is missing. Checking remaining Houdini registrations.'
    $lock = $null
} else {
    $lock = [IO.File]::Open((Join-Path $installRoot 'bootstrap-install.lock'), [IO.FileMode]::OpenOrCreate, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
}
try {
    foreach ($target in $targets) {
        # A stale or edited record can never authorize removing an arbitrary file.
        if ([IO.Path]::GetFileName($target) -ne 'dsh-houdini.json' -or -not (Test-Path -LiteralPath $target -PathType Leaf)) { continue }
        try { $package = Get-Content -LiteralPath $target -Encoding UTF8 -Raw | ConvertFrom-Json }
        catch { $incomplete += "Preserved unreadable package '$target': $($_.Exception.Message)"; continue }
        $owned = $false
        foreach ($entry in $package.env) {
            if ($entry.DSH_HOUDINI_INSTALL_ROOT) {
                try { $owned = [IO.Path]::GetFullPath([string]$entry.DSH_HOUDINI_INSTALL_ROOT).TrimEnd('\', '/') -eq $installRoot }
                catch { $incomplete += "Preserved package with invalid installation root '$target': $($_.Exception.Message)"; $owned = $null }
                break
            }
        }
        if ($null -eq $owned) { continue }
        if (-not $owned) { Write-Output "Preserved registration for another installation: $target"; continue }
        try {
            Remove-Item -LiteralPath $target
            Write-Output "Unregistered: $target"
        } catch { $incomplete += "Could not remove registration '$target': $($_.Exception.Message)" }
    }
    $shortcut = Join-Path $installRoot 'DSH-Houdini.lnk'
    if (Test-Path -LiteralPath $shortcut -PathType Leaf) { Remove-Item -LiteralPath $shortcut }
} finally { if ($lock) { $lock.Dispose() } }
if ($incomplete.Count) {
    throw ("Uninstall incomplete. Completed removals are listed above; unresolved files were preserved. Installation files and user data were retained.`n" + ($incomplete -join "`n"))
}
Write-Output 'DSH-Houdini has been unregistered. Restart Houdini to remove its menu.'
Write-Output "Saved versions, credentials and sessions were retained at: $installRoot"
Write-Output 'Projects and independent DSH installations were not changed. Run Install.cmd to register again.'
