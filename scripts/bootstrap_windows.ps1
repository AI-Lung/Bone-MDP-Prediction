$ErrorActionPreference = "Stop"

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$BootstrapPy = Join-Path $ProjectRoot "scripts\bootstrap.py"

function Test-PythonVersion {
    param(
        [string[]]$CommandParts
    )

    try {
        $ExtraArgs = @()
        if ($CommandParts.Length -gt 1) {
            $ExtraArgs = $CommandParts[1..($CommandParts.Length - 1)]
        }
        $version = & $CommandParts[0] @ExtraArgs -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
        if (-not $version) {
            return $false
        }
        $parts = $version.Trim().Split(".")
        if ([int]$parts[0] -eq 3 -and [int]$parts[1] -ge 10 -and [int]$parts[1] -le 12) { return $true }
        return $false
    }
    catch {
        return $false
    }
}

function Get-PythonCommand {
    $Candidates = @()

    if (Get-Command py -ErrorAction SilentlyContinue) {
        $Candidates += ,@("py", "-3.10")
    }

    if (Get-Command python -ErrorAction SilentlyContinue) {
        $Candidates += ,@("python")
    }

    foreach ($Candidate in $Candidates) {
        if (Test-PythonVersion -CommandParts $Candidate) {
            return $Candidate
        }
    }

    return $null
}

function Install-PythonWithWinget {
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        return
    }

    Write-Host "[bootstrap] Installing Python 3.10 with winget..."
    winget install --id Python.Python.3.10 -e --source winget --accept-source-agreements --accept-package-agreements
}

function Install-PythonDirect {
    $InstallerUrl = "https://www.python.org/ftp/python/3.10.11/python-3.10.11-amd64.exe"
    $InstallerPath = Join-Path $env:TEMP "python-3.10.11-amd64.exe"
    Write-Host "[bootstrap] Downloading Python 3.10 installer..."
    Invoke-WebRequest -Uri $InstallerUrl -OutFile $InstallerPath
    Write-Host "[bootstrap] Running Python installer..."
    Start-Process -FilePath $InstallerPath -ArgumentList "/quiet InstallAllUsers=0 PrependPath=1 Include_test=0 Include_launcher=1 SimpleInstall=1" -Wait
}

$PythonCommand = Get-PythonCommand
if (-not $PythonCommand) {
    Install-PythonWithWinget
    $PythonCommand = Get-PythonCommand
}

if (-not $PythonCommand) {
    Install-PythonDirect
    $PythonCommand = Get-PythonCommand
}

if (-not $PythonCommand) {
    throw "Python 3.10 could not be located or installed automatically."
}

Write-Host "[bootstrap] Using Python launcher: $($PythonCommand -join ' ')"
$LaunchArgs = @()
if ($PythonCommand.Length -gt 1) {
    $LaunchArgs = $PythonCommand[1..($PythonCommand.Length - 1)]
}
& $PythonCommand[0] @LaunchArgs $BootstrapPy
exit $LASTEXITCODE
