# Network Connectivity Test Script
# This script reads a CSV file with URLs/IPs and ports, tests connectivity, and outputs results

param(
    [Parameter(Mandatory=$true)]
    [string]$InputCsv,
   
    [Parameter(Mandatory=$false)]
    [string]$OutputCsv = "connectivity_results.csv",
   
    [Parameter(Mandatory=$false)]
    [int]$TimeoutSeconds = 5
)

# Function to test TCP connectivity
function Test-TcpConnection {
    param(
        [string]$Target,
        [int]$Port,
        [int]$Timeout = 5
    )
   
    try {
        $tcpClient = New-Object System.Net.Sockets.TcpClient
        $connect = $tcpClient.BeginConnect($Target, $Port, $null, $null)
        $wait = $connect.AsyncWaitHandle.WaitOne($Timeout * 1000, $false)
       
        if ($wait) {
            try {
                $tcpClient.EndConnect($connect)
                $result = @{
                    Success = $true
                    Error = $null
                    ResponseTime = (Measure-Command { $tcpClient.Close() }).TotalMilliseconds
                }
            }
            catch {
                $result = @{
                    Success = $false
                    Error = $_.Exception.Message
                    ResponseTime = $null
                }
            }
        }
        else {
            $result = @{
                Success = $false
                Error = "Connection timeout after $Timeout seconds"
                ResponseTime = $null
            }
        }
       
        $tcpClient.Close()
        return $result
    }
    catch {
        return @{
            Success = $false
            Error = $_.Exception.Message
            ResponseTime = $null
        }
    }
}

# Function to resolve hostname to IP
function Get-IpAddress {
    param([string]$Hostname)
   
    try {
        $ip = [System.Net.Dns]::GetHostAddresses($Hostname) | Where-Object { $_.AddressFamily -eq 'InterNetwork' } | Select-Object -First 1
        return $ip.IPAddressToString
    }
    catch {
        return $null
    }
}

# Main script execution
try {
    # Check if input file exists
    if (-not (Test-Path $InputCsv)) {
        throw "Input CSV file '$InputCsv' not found."
    }
   
    # Read the CSV file
    Write-Host "Reading input file: $InputCsv" -ForegroundColor Green
    $inputData = Import-Csv $InputCsv
   
    # Validate CSV structure
    $requiredColumns = @('URL', 'Port')
    $csvColumns = $inputData | Get-Member -MemberType NoteProperty | Select-Object -ExpandProperty Name
   
    $missingColumns = $requiredColumns | Where-Object { $_ -notin $csvColumns }
    if ($missingColumns) {
        throw "Missing required columns: $($missingColumns -join ', '). Expected columns: URL, Port"
    }
   
    # Initialize results array
    $results = @()
    $totalHosts = $inputData.Count
    $currentHost = 0
   
    Write-Host "Testing connectivity to $totalHosts hosts..." -ForegroundColor Yellow
   
    # Process each row
    foreach ($row in $inputData) {
        $currentHost++
        $target = $row.URL.Trim()
        $port = [int]$row.Port
       
        Write-Host "[$currentHost/$totalHosts] Testing $target`:$port" -ForegroundColor Cyan
       
        # Resolve IP address
        $resolvedIp = Get-IpAddress -Hostname $target
       
        # Test connectivity
        $testResult = Test-TcpConnection -Target $target -Port $port -Timeout $TimeoutSeconds
       
        # Create result object
        $result = [PSCustomObject]@{
            'Target' = $target
            'Port' = $port
            'ResolvedIP' = if ($resolvedIp) { $resolvedIp } else { "Unable to resolve" }
            'Status' = if ($testResult.Success) { "Connected" } else { "Failed" }
            'ResponseTime_ms' = $testResult.ResponseTime
            'Error' = $testResult.Error
            'TestDateTime' = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
        }
       
        $results += $result
       
        # Display result
        if ($testResult.Success) {
            Write-Host "  ✓ Success" -ForegroundColor Green
        } else {
            Write-Host "  ✗ Failed: $($testResult.Error)" -ForegroundColor Red
        }
    }
   
    # Export results to CSV
    Write-Host "`nExporting results to: $OutputCsv" -ForegroundColor Green
    $results | Export-Csv -Path $OutputCsv -NoTypeInformation
   
    # Display summary
    $successCount = ($results | Where-Object { $_.Status -eq "Connected" }).Count
    $failedCount = $totalHosts - $successCount
   
    Write-Host "`n=== SUMMARY ===" -ForegroundColor Yellow
    Write-Host "Total hosts tested: $totalHosts" -ForegroundColor White
    Write-Host "Successful connections: $successCount" -ForegroundColor Green
    Write-Host "Failed connections: $failedCount" -ForegroundColor Red
    Write-Host "Results saved to: $OutputCsv" -ForegroundColor White
   
}
catch {
    Write-Host "Error: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}

# Example usage:
# .\NetworkConnectivityTest.ps1 -InputCsv "hosts.csv" -OutputCsv "results.csv" -TimeoutSeconds 10