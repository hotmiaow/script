param(
    [Parameter(Mandatory = $true)]
    [string]$CsvPath,

    [Parameter(Mandatory = $false)]
    [int]$PingCount = 1,

    [Parameter(Mandatory = $false)]
    [int]$DelayMs = 100,

    [Parameter(Mandatory = $false)]
    [int]$TimeoutMs = 3000,

    [Parameter(Mandatory = $false)]
    [string]$OutputCsv = "",

    [Parameter(Mandatory = $false)]
    [switch]$DetailedOutput
)

function Test-IPAddress {
    param([string]$IP)
    try {
        [System.Net.IPAddress]::Parse($IP) | Out-Null
        return $true
    } catch {
        return $false
    }
}

function Test-SubnetFormat {
    param([string]$Input)
    if ($Input -match '^(\d{1,3}\.){3}\d{1,3}/\d{1,2}$') {
        $ip, $cidr = $Input.Split('/')
        try {
            [System.Net.IPAddress]::Parse($ip) | Out-Null
            if ([int]$cidr -ge 1 -and [int]$cidr -le 32) {
                return $true
            }
        } catch { return $false }
    }
    return $false
}

function Expand-Subnet {
    param([string]$Subnet)
    $parts = $Subnet.Split('/')
    $networkIP = $parts[0]
    $cidr = [int]$parts[1]

    $baseIP = [System.Net.IPAddress]::Parse($networkIP)
    $ipBytes = $baseIP.GetAddressBytes()
    [Array]::Reverse($ipBytes)
    $networkInt = [System.BitConverter]::ToUInt32($ipBytes, 0)

    $hostBits = 32 - $cidr
    $numberOfHosts = [math]::Pow(2, $hostBits)

    if ($numberOfHosts -gt 65536) {
        throw "Subnet too large: $numberOfHosts addresses"
    }

    $startOffset = if ($cidr -ge 31) { 0 } else { 1 }
    $endOffset = if ($cidr -ge 31) { $numberOfHosts - 1 } else { $numberOfHosts - 2 }

    $ipList = @()
    for ($i = $startOffset; $i -le $endOffset; $i++) {
        $currentIP = $networkInt + $i
        $bytes = [System.BitConverter]::GetBytes($currentIP)
        [Array]::Reverse($bytes)
        $ipList += [System.Net.IPAddress]::new($bytes).ToString()
    }

    return $ipList
}

function Get-HostName {
    param([string]$IPAddress)
    try {
        return [System.Net.Dns]::GetHostEntry($IPAddress).HostName
    } catch {
        return "Unable to resolve"
    }
}

function Test-PingHost {
    param(
        [string]$IPAddress,
        [int]$Count,
        [int]$Timeout
    )

    $results = @()
    for ($i = 1; $i -le $Count; $i++) {
        try {
            $reply = Test-Connection -ComputerName $IPAddress -Count 1 -Timeout ($Timeout / 1000) -ErrorAction Stop
            $results += [PSCustomObject]@{
                PingNumber   = $i
                Status       = "Success"
                ResponseTime = "$($reply.ResponseTime)ms"
            }
        } catch {
            $results += [PSCustomObject]@{
                PingNumber   = $i
                Status       = "Failed"
                ResponseTime = "N/A"
            }
        }
        if ($i -lt $Count) { Start-Sleep -Milliseconds 100 }
    }

    return $results
}

# Start of script
Write-Host "`n[+] Network Ping Scanner Starting..." -ForegroundColor Green
if (!(Test-Path $CsvPath)) {
    Write-Error "❌ CSV file not found: $CsvPath"
    exit 1
}

if ([string]::IsNullOrWhiteSpace($OutputCsv)) {
    $OutputCsv = "PingScanResults_$(Get-Date -Format 'yyyyMMdd_HHmmss').csv"
}
Write-Host "[*] Output CSV: $OutputCsv" -ForegroundColor Yellow

try {
    $csvData = Import-Csv $CsvPath
    Write-Host "[*] Loaded CSV entries: $($csvData.Count)" -ForegroundColor Cyan
} catch {
    Write-Error "❌ Failed to read CSV: $($_.Exception.Message)"
    exit 1
}

$allResults = @()

foreach ($entry in $csvData) {
    $target = $null
    $possibleColumns = @('IP', 'Subnet', 'Host', 'Address', 'Target', 'Network')
    foreach ($col in $possibleColumns) {
        if ($entry.PSObject.Properties.Name -contains $col -and ![string]::IsNullOrWhiteSpace($entry.$col)) {
            $target = $entry.$col.Trim()
            break
        }
    }

    if (!$target) {
        $firstProperty = $entry.PSObject.Properties | Select-Object -First 1
        $target = $firstProperty.Value.Trim()
    }

    if ([string]::IsNullOrWhiteSpace($target)) {
        Write-Warning "Skipping empty row"
        continue
    }

    Write-Host "`n[>] Processing: $target" -ForegroundColor Cyan
    $ipList = @()
    if (Test-SubnetFormat $target) {
        try {
            $ipList = Expand-Subnet $target
            Write-Host "    ✓ Subnet expanded to $($ipList.Count) IPs" -ForegroundColor Gray
        } catch {
            Write-Warning "    ✗ Failed to expand subnet: $_"
            continue
        }
    } else {
        $ipList = @($target)
    }

    foreach ($ip in $ipList) {
        Write-Host "  → Testing: $ip" -ForegroundColor White
        $hostname = Get-HostName $ip
        $pingResults = Test-PingHost -IPAddress $ip -Count $PingCount -Timeout $TimeoutMs

        $successCount = ($pingResults | Where-Object { $_.Status -eq "Success" }).Count
        $successRate = [math]::Round(($successCount / $PingCount) * 100, 2)
        $times = $pingResults | Where-Object { $_.Status -eq "Success" -and $_.ResponseTime -ne "N/A" } |
                 ForEach-Object { ($_).ResponseTime -replace "ms", "" } | ForEach-Object { [int]$_ }

        $avgResponseTime = if ($times.Count -gt 0) { [math]::Round(($times | Measure-Object -Average).Average, 2) } else { 0 }
        $minTime = if ($times.Count -gt 0) { ($times | Measure-Object -Minimum).Minimum } else { 0 }
        $maxTime = if ($times.Count -gt 0) { ($times | Measure-Object -Maximum).Maximum } else { 0 }
        $isOnline = $successCount -gt 0

        $allResults += [PSCustomObject]@{
            ScanDateTime         = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
            OriginalTarget       = $target
            IPAddress            = $ip
            Hostname             = $hostname
            PingCount            = $PingCount
            SuccessfulPings      = $successCount
            FailedPings          = $PingCount - $successCount
            SuccessRate          = "$successRate%"
            AverageResponseTime  = if ($avgResponseTime -gt 0) { "${avgResponseTime}ms" } else { "N/A" }
            Status               = if ($isOnline) { "Online" } else { "Offline" }
            MinResponseTimeMs    = $minTime
            MaxResponseTimeMs    = $maxTime
            DetailedResults      = ($pingResults | ForEach-Object { "Ping $($_.PingNumber): $($_.Status) ($($_.ResponseTime))" }) -join "; "
            Notes                = if (!$isOnline) { "Unreachable or filtered" } elseif ($successRate -lt 100) { "Intermittent loss" } else { "OK" }
        }

        $color = if ($isOnline) { "Green" } else { "Red" }
        Write-Host "    [$((if ($isOnline) { 'Online' } else { 'Offline' }))] Hostname: $hostname, Success: $successRate%" -ForegroundColor $color        Start-Sleep -Milliseconds $DelayMs
    }
}

Write-Host "`n[✔] Scan completed — Exporting results..." -ForegroundColor Green

# Export results
try {
    $allResults | Export-Csv -Path $OutputCsv -NoTypeInformation -Encoding UTF8
    Write-Host "    ✓ Results exported to $OutputCsv" -ForegroundColor Green
} catch {
    Write-Warning "    ✗ Failed to export CSV: $_"
}

# Export summary
$summaryPath = $OutputCsv -replace '\.csv$', '_Summary.csv'
try {
    $summary = [PSCustomObject]@{
        ScanDateTime    = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
        InputFile       = $CsvPath
        TotalTargets    = $csvData.Count
        TotalIPsScanned = $allResults.Count
        OnlineHosts     = ($allResults | Where-Object { $_.Status -eq 'Online' }).Count
        OfflineHosts    = ($allResults | Where-Object { $_.Status -eq 'Offline' }).Count
        OutputFile      = $OutputCsv
    }
    $summary | Export-Csv -Path $summaryPath -NoTypeInformation -Encoding UTF8
    Write-Host "    ✓ Summary exported to $summaryPath" -ForegroundColor Green
} catch {
    Write-Warning "    ✗ Failed to export summary CSV: $_"
}

Write-Host "`n[🏁] Done!" -ForegroundColor Cyan
