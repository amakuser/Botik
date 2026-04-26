# Win32 window helpers — minimal P/Invoke surface for desktop-native smoke.
# Used by run-automated-smoke.ps1 to find the Tauri shell HWND, check visibility,
# and capture a screenshot via PrintWindow.
#
# Restored 2026-04-26 in minimal form — full original (with reconcile / focus
# helpers) was lost in M1 cleanup.

if (-not ('Botik.Win32Window' -as [type])) {
    Add-Type -Namespace Botik -Name Win32Window -MemberDefinition @'
[DllImport("user32.dll", SetLastError = true, CharSet = CharSet.Unicode)]
public static extern IntPtr FindWindowW(string lpClassName, string lpWindowName);

[DllImport("user32.dll", SetLastError = true, CharSet = CharSet.Unicode)]
public static extern int GetWindowTextW(IntPtr hWnd, System.Text.StringBuilder lpString, int nMaxCount);

[DllImport("user32.dll")]
public static extern bool IsWindow(IntPtr hWnd);

[DllImport("user32.dll")]
public static extern bool IsWindowVisible(IntPtr hWnd);

[DllImport("user32.dll")]
public static extern bool GetWindowRect(IntPtr hWnd, out RECT lpRect);

[DllImport("user32.dll")]
public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint lpdwProcessId);

[DllImport("user32.dll")]
public static extern bool EnumWindows(EnumWindowsProc lpEnumFunc, IntPtr lParam);

[DllImport("user32.dll")]
public static extern bool PrintWindow(IntPtr hwnd, IntPtr hdcBlt, uint nFlags);

public delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);

[StructLayout(LayoutKind.Sequential)]
public struct RECT {
    public int Left;
    public int Top;
    public int Right;
    public int Bottom;
}
'@
}

function Find-BotikDesktopWindow {
    param(
        [int]$ProcessId,
        [int]$TimeoutSeconds = 60
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    $found = [IntPtr]::Zero

    while ((Get-Date) -lt $deadline -and $found -eq [IntPtr]::Zero) {
        $script:matchedHwnd = [IntPtr]::Zero
        $callback = [Botik.Win32Window+EnumWindowsProc] {
            param([IntPtr]$hWnd, [IntPtr]$lParam)

            if (-not [Botik.Win32Window]::IsWindow($hWnd)) { return $true }
            if (-not [Botik.Win32Window]::IsWindowVisible($hWnd)) { return $true }

            $procId = 0
            [void][Botik.Win32Window]::GetWindowThreadProcessId($hWnd, [ref]$procId)
            if ($procId -ne $script:targetPid) { return $true }

            $sb = New-Object System.Text.StringBuilder 512
            [void][Botik.Win32Window]::GetWindowTextW($hWnd, $sb, $sb.Capacity)
            $title = $sb.ToString()

            # Skip empty / placeholder titles (Tauri may briefly show none)
            if ([string]::IsNullOrWhiteSpace($title)) { return $true }

            # Tauri Botik shell exposes the configured productName as title.
            # Match loosely on "Botik" — no substring trap here because we also
            # filter on PID, so other windows with "Botik" in the title (browser
            # tabs, IDE windows) do not collide.
            if ($title -match 'Botik') {
                $script:matchedHwnd = $hWnd
                return $false  # stop EnumWindows
            }

            return $true
        }

        $script:targetPid = $ProcessId
        [void][Botik.Win32Window]::EnumWindows($callback, [IntPtr]::Zero)

        if ($script:matchedHwnd -ne [IntPtr]::Zero) {
            $found = $script:matchedHwnd
            break
        }

        Start-Sleep -Milliseconds 500
    }

    return $found
}

function Get-WindowSnapshot {
    param([IntPtr]$Hwnd)

    if (-not [Botik.Win32Window]::IsWindow($Hwnd)) {
        return @{ ok = $false; reason = 'invalid_hwnd' }
    }

    $rect = New-Object Botik.Win32Window+RECT
    if (-not [Botik.Win32Window]::GetWindowRect($Hwnd, [ref]$rect)) {
        return @{ ok = $false; reason = 'getwindowrect_failed' }
    }

    $sb = New-Object System.Text.StringBuilder 512
    [void][Botik.Win32Window]::GetWindowTextW($Hwnd, $sb, $sb.Capacity)

    return @{
        ok      = $true
        hwnd    = $Hwnd.ToInt64()
        title   = $sb.ToString()
        left    = $rect.Left
        top     = $rect.Top
        right   = $rect.Right
        bottom  = $rect.Bottom
        width   = $rect.Right - $rect.Left
        height  = $rect.Bottom - $rect.Top
        visible = [Botik.Win32Window]::IsWindowVisible($Hwnd)
    }
}

function Save-WindowScreenshot {
    param(
        [IntPtr]$Hwnd,
        [string]$OutPath
    )

    Add-Type -AssemblyName System.Drawing

    $rect = New-Object Botik.Win32Window+RECT
    [void][Botik.Win32Window]::GetWindowRect($Hwnd, [ref]$rect)
    $w = $rect.Right - $rect.Left
    $h = $rect.Bottom - $rect.Top
    if ($w -le 0 -or $h -le 0) { return $false }

    # Full-screen capture is more reliable than PrintWindow against WebView2 —
    # PrintWindow on Tauri's WebView2 child window often returns a black image
    # because the GPU-rendered surface is not in the printable buffer.
    $bmp = New-Object System.Drawing.Bitmap $w, $h
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $g.CopyFromScreen($rect.Left, $rect.Top, 0, 0, (New-Object System.Drawing.Size $w, $h))
    $g.Dispose()

    $dir = Split-Path -Parent $OutPath
    if ($dir -and -not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }

    $bmp.Save($OutPath, [System.Drawing.Imaging.ImageFormat]::Png)
    $bmp.Dispose()
    return Test-Path $OutPath
}

# NOTE: This file is dot-sourced from run-automated-smoke.ps1. Do not call
# Export-ModuleMember here — that only works inside .psm1 module files.
# Functions defined above are already in the caller's scope after dot-source.
