[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [ValidateSet('llm', 'red', 'blue', 'arena', 'command')]
    [string]$Role,
    [string]$AdapterName = 'Ethernet',
    [switch]$DisableWiFi
)

# Run in an elevated Windows PowerShell session on the matching laptop.
$nodes = @{
    llm     = @{ Name = 'llm-laptop';     IP = '192.168.50.11' }
    red     = @{ Name = 'red-laptop';     IP = '192.168.50.12' }
    blue    = @{ Name = 'blue-laptop';    IP = '192.168.50.13' }
    arena   = @{ Name = 'arena-laptop';   IP = '192.168.50.14' }
    command = @{ Name = 'command-laptop'; IP = '192.168.50.15' }
}

if (-not (Get-NetAdapter -Name $AdapterName -ErrorAction SilentlyContinue)) {
    throw "Adapter '$AdapterName' was not found. Run Get-NetAdapter and pass the wired adapter name."
}

$node = $nodes[$Role]
Set-NetIPInterface -InterfaceAlias $AdapterName -Dhcp Disabled
Get-NetIPAddress -InterfaceAlias $AdapterName -AddressFamily IPv4 -ErrorAction SilentlyContinue |
    Where-Object { $_.PrefixOrigin -ne 'WellKnown' } |
    Remove-NetIPAddress -Confirm:$false -ErrorAction SilentlyContinue
New-NetIPAddress -InterfaceAlias $AdapterName -IPAddress $node.IP -PrefixLength 24 | Out-Null
Set-DnsClientServerAddress -InterfaceAlias $AdapterName -ResetServerAddresses

if ($DisableWiFi -and (Get-NetAdapter -Name 'Wi-Fi' -ErrorAction SilentlyContinue)) {
    Disable-NetAdapter -Name 'Wi-Fi' -Confirm:$false
}

$hostsPath = Join-Path $env:WINDIR 'System32\drivers\etc\hosts'
$begin = '# PANOPTICON-BEGIN'
$end = '# PANOPTICON-END'
$managed = @(
    $begin,
    '192.168.50.11 llm-laptop',
    '192.168.50.12 red-laptop',
    '192.168.50.13 blue-laptop',
    '192.168.50.14 arena-laptop',
    '192.168.50.15 command-laptop',
    $end
)
$existing = Get-Content -LiteralPath $hostsPath -ErrorAction Stop
$kept = [System.Collections.Generic.List[string]]::new()
$inside = $false
foreach ($line in $existing) {
    if ($line -eq $begin) { $inside = $true; continue }
    if ($line -eq $end) { $inside = $false; continue }
    if (-not $inside) { [void]$kept.Add($line) }
}
$newHosts = @($kept.ToArray()) + @('') + $managed
Set-Content -LiteralPath $hostsPath -Value $newHosts -Encoding ascii

Write-Host "Configured $($node.Name) at $($node.IP) on $AdapterName. Restart after Rename-Computer if this Windows name has not been set yet."
Write-Host 'Use the same five hostname lines in /etc/hosts inside Ubuntu WSL.'
