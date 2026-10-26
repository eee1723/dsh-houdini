# Native Desktop activation only. No Houdini discovery, Python or private Host.
$ErrorActionPreference = 'Stop'
try {
    Start-Process 'dsh://open'
} catch {
    Add-Type -AssemblyName System.Windows.Forms
    [System.Windows.Forms.MessageBox]::Show('Install official DSH Desktop and enable the Houdini plugin first.', 'DSH-Houdini') | Out-Null
    exit 1
}
