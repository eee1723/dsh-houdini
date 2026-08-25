param(
    [Parameter(Mandatory = $true)]
    [int]$TargetProcessId,
    [string]$DumpDirectory = "C:\dumps"
)

$ErrorActionPreference = "Stop"

Add-Type @"
using System;
using System.Text;
using System.Runtime.InteropServices;

public static class DshWindowProbe {
    public delegate bool EnumWindowsProc(IntPtr hwnd, IntPtr lparam);

    [DllImport("user32.dll")]
    public static extern bool EnumWindows(EnumWindowsProc callback, IntPtr lparam);

    [DllImport("user32.dll")]
    public static extern bool EnumChildWindows(
        IntPtr parent, EnumWindowsProc callback, IntPtr lparam);

    [DllImport("user32.dll")]
    public static extern uint GetWindowThreadProcessId(IntPtr hwnd, out uint pid);

    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    public static extern int GetWindowText(IntPtr hwnd, StringBuilder text, int maxCount);
}
"@

New-Item -ItemType Directory -Path $DumpDirectory -Force | Out-Null
$watchLog = Join-Path $DumpDirectory ("houdini-gl-watch-{0}.log" -f $TargetProcessId)

function Write-WatchLog([string]$Message) {
    $line = "{0:o} {1}" -f (Get-Date), $Message
    Add-Content -LiteralPath $watchLog -Value $line -Encoding UTF8
}

function Get-ProcessWindowText([int]$ProcessId) {
    $texts = [System.Collections.Generic.List[string]]::new()
    $readText = {
        param([IntPtr]$WindowHandle)
        $buffer = [System.Text.StringBuilder]::new(2048)
        [void][DshWindowProbe]::GetWindowText($WindowHandle, $buffer, $buffer.Capacity)
        if ($buffer.Length -gt 0) {
            $texts.Add($buffer.ToString())
        }
    }
    $topCallback = [DshWindowProbe+EnumWindowsProc]{
        param([IntPtr]$WindowHandle, [IntPtr]$Ignored)
        [uint32]$owner = 0
        [void][DshWindowProbe]::GetWindowThreadProcessId($WindowHandle, [ref]$owner)
        if ($owner -eq $ProcessId) {
            & $readText $WindowHandle
            $childCallback = [DshWindowProbe+EnumWindowsProc]{
                param([IntPtr]$ChildHandle, [IntPtr]$ChildIgnored)
                & $readText $ChildHandle
                return $true
            }
            [void][DshWindowProbe]::EnumChildWindows(
                $WindowHandle, $childCallback, [IntPtr]::Zero)
        }
        return $true
    }
    [void][DshWindowProbe]::EnumWindows($topCallback, [IntPtr]::Zero)
    return $texts
}

Write-WatchLog "watch_started pid=$TargetProcessId"
while (Get-Process -Id $TargetProcessId -ErrorAction SilentlyContinue) {
    $windowText = (Get-ProcessWindowText -ProcessId $TargetProcessId) -join " | "
    if ($windowText -match "OpenGL Fatal Error|not able to run OpenGL 3\.3") {
        $timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
        $dumpPath = Join-Path $DumpDirectory (
            "houdini-gl-fatal-{0}-{1}.dmp" -f $TargetProcessId, $timestamp)
        Write-WatchLog "fatal_detected dump=$dumpPath text=$windowText"
        $comsvcs = Join-Path $env:SystemRoot "System32\comsvcs.dll"
        $dump = Start-Process -FilePath "rundll32.exe" -WindowStyle Hidden -Wait -PassThru `
            -ArgumentList @($comsvcs + ",", "MiniDump", $TargetProcessId, $dumpPath, "full")
        Write-WatchLog "dump_finished exit_code=$($dump.ExitCode) exists=$(Test-Path -LiteralPath $dumpPath)"
        exit $dump.ExitCode
    }
    Start-Sleep -Milliseconds 250
}
Write-WatchLog "process_exited_before_fatal"
