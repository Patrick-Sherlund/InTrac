#Requires -Version 5.1
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
Set-Location $PSScriptRoot
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

function Require-Success([string]$Action) {
    if ($LASTEXITCODE -ne 0) { throw "$Action failed (exit $LASTEXITCODE). Resolve the error above and rerun this script." }
}

function Request-Restart {
    Write-Host ''
    Write-Host 'Windows needs a restart to finish installing its container prerequisites.' -ForegroundColor Yellow
    Write-Host 'Save your work, restart Windows, then open PowerShell as Administrator in this folder and run:'
    Write-Host 'powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\setup-windows.ps1'
    Write-Host 'The script safely continues; it does not erase existing InTrac data.'
    exit 3010
}

try {
    if ($env:OS -ne 'Windows_NT' -or -not [Environment]::Is64BitProcess) {
        throw 'Use 64-bit Windows PowerShell on Windows 10/11. For a Mac, use setup-macos.sh.'
    }
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw 'Close this window, right-click Windows PowerShell, choose Run as administrator, then rerun the documented command.'
    }
    if (-not (Test-Path 'compose.yaml') -or -not (Test-Path 'backend/requirements.txt')) {
        throw 'Extract the entire InTrac ZIP first. Do not run this script from inside the ZIP viewer.'
    }
    $osInfo = Get-CimInstance Win32_OperatingSystem
    if ([int]$osInfo.BuildNumber -lt 19045 -or $osInfo.ProductType -ne 1) {
        throw 'Use a currently supported Windows 10/11 desktop release (minimum build 19045), not Windows Server.'
    }

    $restartNeeded = $false
    foreach ($featureName in @('Microsoft-Windows-Subsystem-Linux', 'VirtualMachinePlatform')) {
        $feature = Get-WindowsOptionalFeature -Online -FeatureName $featureName
        if ($feature.State -eq 'EnablePending') { $restartNeeded = $true }
        elseif ($feature.State -ne 'Enabled') {
            Write-Host "Enabling $featureName..."
            $result = Enable-WindowsOptionalFeature -Online -FeatureName $featureName -All -NoRestart
            if ($result.RestartNeeded) { $restartNeeded = $true }
        }
    }
    if ($restartNeeded) { Request-Restart }

    # WSL is installed directly by Windows; no Store login, winget, Git, or Linux distro is needed.
    $ErrorActionPreference = 'Continue'
    & wsl.exe --version *> $null
    $wslVersionCode = $LASTEXITCODE
    $ErrorActionPreference = 'Stop'
    if ($wslVersionCode -ne 0) {
        & wsl.exe --install --no-distribution --web-download
        if ($LASTEXITCODE -eq 3010) { Request-Restart }
        Require-Success 'WSL installation'
    }
    & wsl.exe --update --web-download
    if ($LASTEXITCODE -eq 3010) { Request-Restart }
    Require-Success 'WSL update'
    & wsl.exe --set-default-version 2
    Require-Success 'Selecting WSL 2'

    $dockerLocations = @(
        "$env:ProgramFiles\Docker\Docker",
        "$env:LOCALAPPDATA\Programs\DockerDesktop"
    )
    $dockerDirectory = $dockerLocations | Where-Object { Test-Path "$_\Docker Desktop.exe" } | Select-Object -First 1
    if (-not $dockerDirectory) {
        $architecture = $env:PROCESSOR_ARCHITECTURE
        if ($architecture -eq 'ARM64') { $dockerArch = 'arm64' }
        elseif ($architecture -eq 'AMD64') { $dockerArch = 'amd64' }
        else { throw "Unsupported Windows processor: $architecture" }
        $installer = Join-Path ([IO.Path]::GetTempPath()) ("intrac-docker-" + [guid]::NewGuid() + '.exe')
        try {
            Write-Host 'Downloading Docker Desktop. This can take several minutes.'
            $ProgressPreference = 'SilentlyContinue'
            Invoke-WebRequest -UseBasicParsing -Uri "https://desktop.docker.com/win/main/$dockerArch/Docker%20Desktop%20Installer.exe" -OutFile $installer
            $signature = Get-AuthenticodeSignature $installer
            if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch 'Docker') {
                throw 'The Docker installer signature could not be verified. Delete the download and retry on a trusted connection.'
            }
            Write-Host 'Installing Docker Desktop. Complete any installer prompts.'
            $process = Start-Process -FilePath $installer -ArgumentList @('install', '--backend=wsl-2', '--no-windows-containers') -Wait -PassThru
            if ($process.ExitCode -in @(3010, 1641)) { Request-Restart }
            if ($process.ExitCode -ne 0) { throw "Docker installation failed (exit $($process.ExitCode))." }
        }
        finally { if (Test-Path $installer) { Remove-Item $installer -Force } }
        $dockerDirectory = $dockerLocations | Where-Object { Test-Path "$_\Docker Desktop.exe" } | Select-Object -First 1
        if (-not $dockerDirectory) { throw 'Docker Desktop was not found after installation. Check the installer and rerun.' }
    }
    $env:Path = "$dockerDirectory\resources\bin;" + $env:Path
    Start-Process -FilePath "$dockerDirectory\Docker Desktop.exe"
    Write-Host 'Finish the Docker Desktop welcome screens and review/accept its terms if you agree.'
    Write-Host 'Use recommended settings. You can skip Docker account sign-in.'
    Write-Host 'Waiting up to 10 minutes for the Linux container engine...'
    $dockerReady = $false
    for ($attempt = 0; $attempt -lt 120; $attempt++) {
        # Windows PowerShell treats native stderr as errors; discard expected startup diagnostics.
        $previousPreference = $ErrorActionPreference
        $ErrorActionPreference = 'Continue'
        & docker info *> $null
        $readyCode = $LASTEXITCODE
        $ErrorActionPreference = $previousPreference
        if ($readyCode -eq 0) { $dockerReady = $true; break }
        if ($attempt % 6 -eq 0) { Write-Host 'Still waiting; check the Docker Desktop window.' }
        Start-Sleep -Seconds 5
    }
    if (-not $dockerReady) { throw 'Docker did not start. Check Docker Desktop for a WSL/virtualization error, restart Windows if asked, then rerun.' }
    $engine = & docker info --format '{{.OSType}}'
    Require-Success 'Checking Docker'
    if ($engine -ne 'linux') { throw 'Choose Switch to Linux containers from the Docker Desktop tray menu, then rerun.' }
    & docker compose version
    Require-Success 'Checking Docker Compose'

    if (-not (Test-Path '.env')) { Copy-Item '.env.example' '.env' }
    Write-Host 'Building and starting InTrac. The first build downloads its software dependencies.'
    & docker compose up -d --build --wait --wait-timeout 180
    Require-Success 'Building/starting InTrac'
    Write-Host 'Choose an administrator password (12-128 characters). Typing is hidden. Save it in your password manager.'
    & docker compose exec api python -m app.create_admin --first-name System --last-name Administrator --username admin --if-missing
    Require-Success 'Administrator setup'
    & docker compose ps
    Require-Success 'Checking InTrac containers'
    Write-Host 'InTrac is ready. Default address: http://localhost (username: admin).' -ForegroundColor Green
    Write-Host 'If you changed .env, use your configured address/port.'
    Write-Host 'For free public HTTPS, follow docs/CLOUDFLARE.md. For local HTTPS, see docs/HTTPS.md.'
    Write-Host 'Keep Docker Desktop running and this computer awake while people use InTrac.'
}
catch {
    Write-Host "Setup stopped: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
