[CmdletBinding()]
param()

# Run on Laptop 05 / command-laptop. It tests every expected service from the
# same machine that hosts the dashboard, Prometheus, and Grafana.
$checks = @(
    @{ Name = 'LLM gateway'; Host = 'llm-laptop'; Port = 8090; Path = '/health' },
    @{ Name = 'Red agent'; Host = 'red-laptop'; Port = 8081; Path = '/health' },
    @{ Name = 'Blue agent'; Host = 'blue-laptop'; Port = 8082; Path = '/health' },
    @{ Name = 'Arena target'; Host = 'arena-laptop'; Port = 30080; Path = '/health' },
    @{ Name = 'Command dashboard'; Host = 'command-laptop'; Port = 8000; Path = '/control/status' },
    @{ Name = 'Prometheus'; Host = 'command-laptop'; Port = 9090; Path = '/-/healthy' },
    @{ Name = 'Grafana'; Host = 'command-laptop'; Port = 3000; Path = '/api/health' }
)

$failed = @()
foreach ($check in $checks) {
    $tcp = Test-NetConnection -ComputerName $check.Host -Port $check.Port -WarningAction SilentlyContinue
    $http = $false
    if ($tcp.TcpTestSucceeded) {
        try {
            $null = Invoke-WebRequest -UseBasicParsing -TimeoutSec 4 "http://$($check.Host):$($check.Port)$($check.Path)"
            $http = $true
        } catch {}
    }
    [PSCustomObject]@{ Service = $check.Name; Host = $check.Host; Port = $check.Port; TCP = $tcp.TcpTestSucceeded; HTTP = $http } |
        Format-Table -AutoSize
    if (-not $http) { $failed += $check.Name }
}

if ($failed.Count) {
    throw "Failed checks: $($failed -join ', '). Run Publish-PanopticonPorts.ps1 on the owning laptop, then retry."
}
Write-Host 'All Command-laptop connectivity checks passed.' -ForegroundColor Green
