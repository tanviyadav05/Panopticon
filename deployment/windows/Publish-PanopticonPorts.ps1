[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [ValidateSet('llm', 'red', 'blue', 'arena', 'command')]
    [string]$Role,
    [string]$Distro = 'Ubuntu-24.04'
)

# Run in an elevated Windows PowerShell session after the role's WSL service
# is started. Re-run it after a Windows restart when using NAT-mode WSL.
$portsByRole = @{
    llm     = @(8090, 9100)
    red     = @(8081, 9100)
    blue    = @(8082, 9100)
    arena   = @(6443, 30080, 9100)
    command = @(8000, 9600, 9500, 9090, 3000, 9100)
}

$wslIP = (wsl.exe -d $Distro hostname -I).Trim().Split([char[]]' ', [System.StringSplitOptions]::RemoveEmptyEntries)[0]
if (-not $wslIP) { throw "Could not obtain a WSL IP from distribution '$Distro'." }

foreach ($port in $portsByRole[$Role]) {
    netsh interface portproxy delete v4tov4 listenport=$port listenaddress=0.0.0.0 | Out-Null
    netsh interface portproxy add v4tov4 listenport=$port listenaddress=0.0.0.0 connectport=$port connectaddress=$wslIP | Out-Null
    New-NetFirewallRule -DisplayName "Panopticon TCP $port" -Direction Inbound -Action Allow -Protocol TCP -LocalPort $port -ErrorAction SilentlyContinue | Out-Null
}

Write-Host "Published $Role ports through Windows to WSL IP $wslIP."
netsh interface portproxy show v4tov4
