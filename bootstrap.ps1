$ErrorActionPreference = 'Stop'
function Test-Python([string]$Exe, [string[]]$PrefixArgs = @()) {
    try {
        $oldPreference = $ErrorActionPreference
        $ErrorActionPreference = 'Continue'
        $output = & $Exe @PrefixArgs -c 'import sys, tkinter; assert sys.version_info >= (3, 11); print(sys.executable)' 2>$null
        $code = $LASTEXITCODE
        $ErrorActionPreference = $oldPreference
        if ($code -eq 0 -and $output) {
            $path = [string](@($output)[-1])
            if (Test-Path -LiteralPath $path) { return $path }
        }
    } catch { } finally { $ErrorActionPreference = 'Stop' }
    return $null
}
function Find-Python {
    $runtime = Join-Path $env:LOCALAPPDATA 'PhotoRawSelector\Python311\python.exe'
    if (Test-Path -LiteralPath $runtime) {
        $found = Test-Python $runtime
        if ($found) { return $found }
    }
    $launcher = Get-Command py.exe -ErrorAction SilentlyContinue
    if ($launcher) {
        foreach ($version in @('-3.11', '-3')) {
            $found = Test-Python $launcher.Source @($version)
            if ($found) { return $found }
        }
    }
    foreach ($name in @('python.exe', 'python3.exe')) {
        $command = Get-Command $name -ErrorAction SilentlyContinue
        if ($command -and $command.Source -notmatch '\\WindowsApps\\') {
            $found = Test-Python $command.Source
            if ($found) { return $found }
        }
    }
    # Standard Python installer registrations, including installations outside PATH.
    foreach ($key in @('HKCU:\Software\Python\PythonCore\*\InstallPath',
                       'HKLM:\Software\Python\PythonCore\*\InstallPath',
                       'HKLM:\Software\WOW6432Node\Python\PythonCore\*\InstallPath')) {
        foreach ($item in @(Get-ItemProperty -Path $key -ErrorAction SilentlyContinue)) {
            $candidate = $item.ExecutablePath
            if (-not $candidate -and $item.'(default)') {
                $candidate = Join-Path $item.'(default)' 'python.exe'
            }
            if ($candidate -and (Test-Path -LiteralPath $candidate)) {
                $found = Test-Python $candidate
                if ($found) { return $found }
            }
        }
    }
    return $null
}
try {
    $appPath = Join-Path $PSScriptRoot 'app.py'
    if (-not (Test-Path -LiteralPath $appPath)) { throw 'app.py is missing. Extract the entire ZIP first.' }
    Write-Host 'Checking installed Python and Tkinter...'
    $pythonExe = Find-Python
    if (-not $pythonExe) {
        Write-Host 'No suitable Python found. Downloading official Python 3.11.9...'
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        $runtimeDir = Join-Path $env:LOCALAPPDATA 'PhotoRawSelector\Python311'
        $installer = Join-Path ([IO.Path]::GetTempPath()) ('photo-python-' + [Guid]::NewGuid().ToString('N') + '.exe')
        $installLog = Join-Path ([IO.Path]::GetTempPath()) 'PhotoRawSelector-python-install.log'
        try {
            Invoke-WebRequest -UseBasicParsing -Uri 'https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe' -OutFile $installer
            $signature = Get-AuthenticodeSignature -LiteralPath $installer
            if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch 'Python Software Foundation') {
                throw 'Installer signature verification failed.'
            }
            Write-Host 'Installing Python. Please wait...'
            $installArgs = '/quiet /log "' + $installLog + '" InstallAllUsers=0 TargetDir="' + $runtimeDir + '" Include_tcltk=1 Include_pip=0 Include_test=0 Include_launcher=0 InstallLauncherAllUsers=0 PrependPath=0 Shortcuts=0 AssociateFiles=0'
            $process = Start-Process -FilePath $installer -ArgumentList $installArgs -Wait -PassThru
            if ($process.ExitCode -notin @(0, 3010)) { throw ('Installer exit code: ' + $process.ExitCode + '. Log: ' + $installLog) }
            # Installer can service an existing installation rather than TargetDir.
            $pythonExe = Find-Python
            if (-not $pythonExe) { throw ('Python with Tkinter was not found after installation. Install Python 3.11+ with Tcl/Tk enabled, then retry. Log: ' + $installLog) }
        } finally {
            if (Test-Path -LiteralPath $installer) { Remove-Item -LiteralPath $installer -Force }
        }
    }
    Write-Host ('Using Python: ' + $pythonExe)
    # Run with python.exe so startup errors remain visible rather than disappearing.
    & $pythonExe $appPath
    if ($LASTEXITCODE -ne 0) { throw ('Application exited with code ' + $LASTEXITCODE) }
} catch {
    Write-Host ('ERROR: ' + $_.Exception.Message) -ForegroundColor Red
    Read-Host 'Press Enter to close'
    exit 1
}
