param([string]$SourceRoot, [string]$Root, [string]$Hfs)
$ErrorActionPreference = 'Stop'
try {
    $candidates = @($Hfs, $env:HFS)
    $candidates += @(Get-ChildItem -LiteralPath 'HKLM:\SOFTWARE\Side Effects Software' -ErrorAction SilentlyContinue |
        Where-Object PSChildName -Match '^Houdini (21|22)\.0\.' | Sort-Object PSChildName -Descending |
        ForEach-Object { (Get-ItemProperty -LiteralPath $_.PSPath).InstallPath })
    $selected = $candidates | Where-Object { $_ -and (Test-Path -LiteralPath (Join-Path $_ 'bin/houdini.exe')) } | Select-Object -First 1
    if (-not $selected) { throw 'Houdini 21 or 22 was not found. Pass -Hfs with the installed Houdini directory.' }
    $python = Get-ChildItem -LiteralPath $selected -Directory -Filter 'python3*' |
        ForEach-Object { Join-Path $_.FullName 'python.exe' } | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
    if (-not $python) { throw 'The selected Houdini Python runtime is incomplete.' }
    if ($SourceRoot) {
        $entry = Join-Path $SourceRoot 'houdini/python3.11libs/dsh_workbench_start.py'
        & $python $entry --hfs $selected --source-root $SourceRoot
    } else {
        $entry = Join-Path $PSScriptRoot 'python/dsh_workbench_start.py'
        & $python $entry --hfs $selected --root $Root
    }
    if ($LASTEXITCODE -ne 0) { throw 'DSH-Houdini did not start. See the startup message or runtime diagnostics.' }
} catch {
    Add-Type -AssemblyName System.Windows.Forms
    [System.Windows.Forms.MessageBox]::Show($_.Exception.Message, 'DSH-Houdini') | Out-Null
    exit 1
}
