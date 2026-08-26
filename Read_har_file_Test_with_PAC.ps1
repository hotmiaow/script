# HAR File Network Connectivity Test Script
# This script reads a HAR file, extracts domains and URLs, creates a hosts.csv file, 
# then tests connectivity and outputs results

param(
    [Parameter(Mandatory=$true)]
    [string]$HarFile,
    
    [Parameter(Mandatory=$false)]
    [string]$HostsCsv = "hosts.csv",
    
    [Parameter(Mandatory=$false)]
    [string]$OutputCsv = "connectivity_results.csv",
    
    [Parameter(Mandatory=$false)]
    [int]$TimeoutSeconds = 5
)

# Function to extract hosts from HAR file
function Extract-HostsFromHar {
    param(
        [string]$HarFilePath
    )
    
    try {
        Write-Host "Reading HAR file: $HarFilePath" -ForegroundColor Green
        $harContent = Get-Content $HarFilePath -Raw | ConvertFrom-Json
        
        $extractedHosts = @()
        $uniqueHosts = @{}
        
        # Extract entries from HAR file
        foreach ($entry in $harContent.log.entries) {
            try {
                $url = $entry.request.url
                $uri = [System.Uri]$url
                
                # Extract domain and port
                $domain = $uri.Host
                $port = $uri.Port
                
                # Set default ports if not specified
                if ($port -eq -1) {
                    switch ($uri.Scheme.ToLower()) {
                        "http" { $port = 80 }
                        "https" { $port = 443 }
                        "ftp" { $port = 21 }
                        "ssh" { $port = 22 }
                        default { $port = 80 }
                    }
                }
                
                # Create unique key for deduplication
                $hostKey = "$domain`:$port"
                
                # Add to unique hosts collection
                if (-not $uniqueHosts.ContainsKey($hostKey)) {
                    $uniqueHosts[$hostKey] = @{
                        Domain = $domain
                        Port = $port
                        Scheme = $uri.Scheme.ToLower()
                        FirstSeen = $entry.startedDateTime
                    }
                }
            }
            catch {
                Write-Warning "Failed to parse URL: $($entry.request.url) - $($_.Exception.Message)"
            }
        }
        
        # Convert to array and sort
        $extractedHosts = $uniqueHosts.Values | Sort-Object Domain, Port
        
        Write-Host "Extracted $($extractedHosts.Count) unique hosts from HAR file" -ForegroundColor Yellow
        return $extractedHosts
    }
    catch {
        throw "Failed to read HAR file: $($_.Exception.Message)"
    }
}

# Function to get user's proxy preference
function Get-UserProxyChoice {
    Write-Host "`n=== PROXY CONFIGURATION ===" -ForegroundColor Magenta
    Write-Host "How would you like to connect to the targets?" -ForegroundColor Yellow
    Write-Host "1. Direct connection (no proxy)" -ForegroundColor Green
    Write-Host "2. Use PAC (Proxy Auto-Configuration) file" -ForegroundColor Green
    Write-Host "3. Specify proxy manually" -ForegroundColor Green
    
    do {
        $choice = Read-Host "`nEnter your choice (1-3)"
        switch ($choice) {
            "1" { return "Direct" }
            "2" { return "PAC" }
            "3" { return "Manual" }
            default { 
                Write-Host "Invalid choice. Please enter 1, 2, or 3." -ForegroundColor Red
            }
        }
    } while ($true)
}

# Function to get PAC file path from user
function Get-PACFilePath {
    do {
        $pacFile = Read-Host "`nEnter the path to the PAC file"
        if (Test-Path $pacFile) {
            return $pacFile
        } else {
            Write-Host "PAC file not found: $pacFile" -ForegroundColor Red
            $retry = Read-Host "Do you want to try again? (y/n)"
            if ($retry -notmatch '^[yY]') {
                return $null
            }
        }
    } while ($true)
}

# Function to get manual proxy configuration from user
function Get-ManualProxyConfig {
    Write-Host "`n=== MANUAL PROXY CONFIGURATION ===" -ForegroundColor Cyan
    Write-Host "Available proxy types:" -ForegroundColor Yellow
    Write-Host "1. HTTP/HTTPS Proxy" -ForegroundColor Green
    Write-Host "2. SOCKS4 Proxy" -ForegroundColor Green
    Write-Host "3. SOCKS5 Proxy" -ForegroundColor Green
    
    do {
        $proxyType = Read-Host "`nEnter proxy type (1-3)"
        switch ($proxyType) {
            "1" { $type = "PROXY"; break }
            "2" { $type = "SOCKS4"; break }
            "3" { $type = "SOCKS5"; break }
            default { 
                Write-Host "Invalid choice. Please enter 1, 2, or 3." -ForegroundColor Red
                continue
            }
        }
    } while ($proxyType -notmatch '^[123]

# Function to parse PAC file and extract proxy settings
function Get-ProxyFromPAC {
    param(
        [string]$PACFilePath
    )
    
    try {
        Write-Host "Reading PAC file: $PACFilePath" -ForegroundColor Green
        $pacContent = Get-Content $PACFilePath -Raw
        
        # Extract proxy configurations from PAC file using regex patterns
        $proxyPatterns = @(
            'PROXY\s+([^;:\s]+):(\d+)',
            'SOCKS\s+([^;:\s]+):(\d+)',
            'SOCKS5\s+([^;:\s]+):(\d+)',
            'SOCKS4\s+([^;:\s]+):(\d+)'
        )
        
        foreach ($pattern in $proxyPatterns) {
            $matches = [regex]::Matches($pacContent, $pattern, [System.Text.RegularExpressions.RegexOptions]::IgnoreCase)
            if ($matches.Count -gt 0) {
                $match = $matches[0]
                $proxyType = $match.Value.Split()[0]
                $proxyHost = $match.Groups[1].Value
                $proxyPort = [int]$match.Groups[2].Value
                
                $proxyConfig = @{
                    Type = $proxyType
                    Host = $proxyHost
                    Port = $proxyPort
                }
                
                Write-Host "Found proxy configuration: $proxyType $proxyHost`:$proxyPort" -ForegroundColor Yellow
                
                # Test proxy connectivity
                Write-Host "Testing PAC proxy connectivity..." -ForegroundColor Cyan
                $proxyTestResult = Test-ProxyConnectivity -ProxyConfig $proxyConfig
                
                if ($proxyTestResult.Success) {
                    Write-Host "✓ PAC proxy is reachable" -ForegroundColor Green
                    return $proxyConfig
                } else {
                    Write-Host "✗ PAC proxy connection failed: $($proxyTestResult.Error)" -ForegroundColor Red
                    $continue = Read-Host "Do you want to continue anyway? (y/n)"
                    if ($continue -match '^[yY]') {
                        return $proxyConfig
                    }
                }
            }
        }
        
        Write-Warning "No proxy configuration found in PAC file"
        return $null
    }
    catch {
        Write-Warning "Failed to parse PAC file: $($_.Exception.Message)"
        return $null
    }
}
function Test-TcpConnection {
    param(
        [string]$Target,
        [int]$Port,
        [int]$Timeout = 5,
        [hashtable]$ProxyConfig = $null
    )
    
    try {
        if ($ProxyConfig) {
            # Test connection through proxy
            return Test-ProxyConnection -Target $Target -Port $Port -ProxyConfig $ProxyConfig -Timeout $Timeout
        }
        else {
            # Direct connection
            $tcpClient = New-Object System.Net.Sockets.TcpClient
            $stopwatch = [System.Diagnostics.Stopwatch]::StartNew()
            $connect = $tcpClient.BeginConnect($Target, $Port, $null, $null)
            $wait = $connect.AsyncWaitHandle.WaitOne($Timeout * 1000, $false)
            
            if ($wait) {
                try {
                    $tcpClient.EndConnect($connect)
                    $stopwatch.Stop()
                    $result = @{
                        Success = $true
                        Error = $null
                        ResponseTime = $stopwatch.ElapsedMilliseconds
                        Method = "Direct"
                    }
                }
                catch {
                    $stopwatch.Stop()
                    $result = @{
                        Success = $false
                        Error = $_.Exception.Message
                        ResponseTime = $null
                        Method = "Direct"
                    }
                }
            }
            else {
                $stopwatch.Stop()
                $result = @{
                    Success = $false
                    Error = "Connection timeout after $Timeout seconds"
                    ResponseTime = $null
                    Method = "Direct"
                }
            }
            
            $tcpClient.Close()
            return $result
        }
    }
    catch {
        return @{
            Success = $false
            Error = $_.Exception.Message
            ResponseTime = $null
            Method = if ($ProxyConfig) { "Proxy" } else { "Direct" }
        }
    }
}

# Function to test connection through proxy
function Test-ProxyConnection {
    param(
        [string]$Target,
        [int]$Port,
        [hashtable]$ProxyConfig,
        [int]$Timeout = 5
    )
    
    try {
        $stopwatch = [System.Diagnostics.Stopwatch]::StartNew()
        
        # Create TCP client and connect to proxy
        $tcpClient = New-Object System.Net.Sockets.TcpClient
        $proxyConnect = $tcpClient.BeginConnect($ProxyConfig.Host, $ProxyConfig.Port, $null, $null)
        $proxyWait = $proxyConnect.AsyncWaitHandle.WaitOne($Timeout * 1000, $false)
        
        if (-not $proxyWait) {
            $stopwatch.Stop()
            return @{
                Success = $false
                Error = "Proxy connection timeout after $Timeout seconds"
                ResponseTime = $null
                Method = "Proxy ($($ProxyConfig.Type))"
            }
        }
        
        try {
            $tcpClient.EndConnect($proxyConnect)
            $stream = $tcpClient.GetStream()
            
            # Send CONNECT request for HTTP proxy
            if ($ProxyConfig.Type -eq "PROXY") {
                $connectRequest = "CONNECT $Target`:$Port HTTP/1.1`r`nHost: $Target`:$Port`r`n`r`n"
                $requestBytes = [System.Text.Encoding]::ASCII.GetBytes($connectRequest)
                $stream.Write($requestBytes, 0, $requestBytes.Length)
                
                # Read response
                $buffer = New-Object byte[] 4096
                $bytesRead = $stream.Read($buffer, 0, $buffer.Length)
                $response = [System.Text.Encoding]::ASCII.GetString($buffer, 0, $bytesRead)
                
                if ($response -match "HTTP/1\.[01] 200") {
                    $stopwatch.Stop()
                    $result = @{
                        Success = $true
                        Error = $null
                        ResponseTime = $stopwatch.ElapsedMilliseconds
                        Method = "Proxy ($($ProxyConfig.Type))"
                    }
                }
                else {
                    $stopwatch.Stop()
                    $result = @{
                        Success = $false
                        Error = "Proxy returned: $($response.Split("`r`n")[0])"
                        ResponseTime = $null
                        Method = "Proxy ($($ProxyConfig.Type))"
                    }
                }
            }
            else {
                # For SOCKS proxies, this is a simplified test
                $stopwatch.Stop()
                $result = @{
                    Success = $true
                    Error = $null
                    ResponseTime = $stopwatch.ElapsedMilliseconds
                    Method = "Proxy ($($ProxyConfig.Type))"
                }
            }
            
            $stream.Close()
            $tcpClient.Close()
            return $result
        }
        catch {
            $stopwatch.Stop()
            $tcpClient.Close()
            return @{
                Success = $false
                Error = $_.Exception.Message
                ResponseTime = $null
                Method = "Proxy ($($ProxyConfig.Type))"
            }
        }
    }
    catch {
        return @{
            Success = $false
            Error = $_.Exception.Message
            ResponseTime = $null
            Method = "Proxy ($($ProxyConfig.Type))"
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

# Function to test connectivity for all hosts
function Test-HostConnectivity {
    param(
        [array]$HostList,
        [int]$Timeout = 5,
        [hashtable]$ProxyConfig = $null
    )
    
    $results = @()
    $totalHosts = $HostList.Count
    $currentHost = 0
    
    $connectionMethod = if ($ProxyConfig) { "proxy ($($ProxyConfig.Type) $($ProxyConfig.Host):$($ProxyConfig.Port))" } else { "direct connection" }
    Write-Host "`nTesting connectivity to $totalHosts hosts using $connectionMethod..." -ForegroundColor Yellow
    
    foreach ($hostItem in $HostList) {
        $currentHost++
        $target = $hostItem.Domain
        $port = $hostItem.Port
        
        Write-Host "[$currentHost/$totalHosts] Testing $target`:$port" -ForegroundColor Cyan
        
        # Resolve IP address
        $resolvedIp = Get-IpAddress -Hostname $target
        
        # Test connectivity
        $testResult = Test-TcpConnection -Target $target -Port $port -Timeout $Timeout -ProxyConfig $ProxyConfig
        
        # Create result object
        $result = [PSCustomObject]@{
            'Domain' = $target
            'Port' = $port
            'Scheme' = $hostItem.Scheme
            'ResolvedIP' = if ($resolvedIp) { $resolvedIp } else { "Unable to resolve" }
            'Status' = if ($testResult.Success) { "Connected" } else { "Failed" }
            'ResponseTime_ms' = $testResult.ResponseTime
            'ConnectionMethod' = $testResult.Method
            'Error' = $testResult.Error
            'FirstSeen' = $hostItem.FirstSeen
            'TestDateTime' = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
        }
        
        $results += $result
        
        # Display result
        if ($testResult.Success) {
            Write-Host "  ✓ Success ($($testResult.ResponseTime)ms)" -ForegroundColor Green
        } else {
            Write-Host "  ✗ Failed: $($testResult.Error)" -ForegroundColor Red
        }
    }
    
    return $results
}

# Main script execution
try {
    # Check if HAR file exists
    if (-not (Test-Path $HarFile)) {
        throw "HAR file '$HarFile' not found."
    }
    
    # Handle proxy configuration based on user choice
    $proxyConfig = $null
    $userChoice = Get-UserProxyChoice
    
    switch ($userChoice) {
        "Direct" {
            Write-Host "`n=== DIRECT CONNECTION MODE ===" -ForegroundColor Magenta
            Write-Host "Using direct connections (no proxy)" -ForegroundColor Green
            $proxyConfig = $null
        }
        "PAC" {
            Write-Host "`n=== PAC FILE MODE ===" -ForegroundColor Magenta
            $pacFilePath = Get-PACFilePath
            if ($pacFilePath) {
                $proxyConfig = Get-ProxyFromPAC -PACFilePath $pacFilePath
                if (-not $proxyConfig) {
                    Write-Host "Failed to configure PAC proxy. Falling back to direct connection." -ForegroundColor Yellow
                    $proxyConfig = $null
                }
            } else {
                Write-Host "PAC file not specified. Falling back to direct connection." -ForegroundColor Yellow
                $proxyConfig = $null
            }
        }
        "Manual" {
            Write-Host "`n=== MANUAL PROXY MODE ===" -ForegroundColor Magenta
            $proxyConfig = Get-ManualProxyConfig
            if (-not $proxyConfig) {
                Write-Host "Manual proxy configuration failed. Falling back to direct connection." -ForegroundColor Yellow
                $proxyConfig = $null
            }
        }
    }
    
    Write-Host "`n=== HAR FILE ANALYSIS ===" -ForegroundColor Magenta
    
    # Extract hosts from HAR file
    $extractedHosts = Extract-HostsFromHar -HarFilePath $HarFile
    
    if ($extractedHosts.Count -eq 0) {
        throw "No hosts found in HAR file."
    }
    
    # Create hosts.csv
    Write-Host "`nCreating hosts CSV file: $HostsCsv" -ForegroundColor Green
    $hostsForCsv = $extractedHosts | ForEach-Object {
        [PSCustomObject]@{
            'Domain' = $_.Domain
            'Port' = $_.Port
            'Scheme' = $_.Scheme
            'FirstSeen' = $_.FirstSeen
        }
    }
    
    $hostsForCsv | Export-Csv -Path $HostsCsv -NoTypeInformation
    Write-Host "Hosts exported to: $HostsCsv" -ForegroundColor White
    
    # Display extracted hosts summary
    Write-Host "`n=== EXTRACTED HOSTS SUMMARY ===" -ForegroundColor Yellow
    $httpHosts = ($extractedHosts | Where-Object { $_.Scheme -eq "http" }).Count
    $httpsHosts = ($extractedHosts | Where-Object { $_.Scheme -eq "https" }).Count
    $otherHosts = $extractedHosts.Count - $httpHosts - $httpsHosts
    
    Write-Host "Total unique hosts: $($extractedHosts.Count)" -ForegroundColor White
    Write-Host "HTTP hosts: $httpHosts" -ForegroundColor White
    Write-Host "HTTPS hosts: $httpsHosts" -ForegroundColor White
    Write-Host "Other protocols: $otherHosts" -ForegroundColor White
    
    # Test connectivity
    Write-Host "`n=== CONNECTIVITY TESTING ===" -ForegroundColor Magenta
    $connectivityResults = Test-HostConnectivity -HostList $extractedHosts -Timeout $TimeoutSeconds -ProxyConfig $proxyConfig
    
    # Export connectivity results
    Write-Host "`nExporting connectivity results to: $OutputCsv" -ForegroundColor Green
    $connectivityResults | Export-Csv -Path $OutputCsv -NoTypeInformation
    
    # Display final summary
    $successCount = ($connectivityResults | Where-Object { $_.Status -eq "Connected" }).Count
    $failedCount = $connectivityResults.Count - $successCount
    
    Write-Host "`n=== CONNECTIVITY SUMMARY ===" -ForegroundColor Yellow
    Write-Host "Total hosts tested: $($connectivityResults.Count)" -ForegroundColor White
    Write-Host "Successful connections: $successCount" -ForegroundColor Green
    Write-Host "Failed connections: $failedCount" -ForegroundColor Red
    Write-Host "Success rate: $([math]::Round(($successCount / $connectivityResults.Count) * 100, 2))%" -ForegroundColor White
    
    Write-Host "`n=== OUTPUT FILES ===" -ForegroundColor Magenta
    Write-Host "Hosts CSV: $HostsCsv" -ForegroundColor White
    Write-Host "Results CSV: $OutputCsv" -ForegroundColor White
    
    # Display top failed connections
    $failedConnections = $connectivityResults | Where-Object { $_.Status -eq "Failed" } | Select-Object -First 5
    if ($failedConnections.Count -gt 0) {
        Write-Host "`n=== TOP FAILED CONNECTIONS ===" -ForegroundColor Red
        foreach ($failed in $failedConnections) {
            Write-Host "$($failed.Domain):$($failed.Port) - $($failed.Error)" -ForegroundColor Red
        }
    }
    
}
catch {
    Write-Host "Error: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}

# Example usage:
# The script will interactively ask for proxy configuration
# .\HarConnectivityTest.ps1 -HarFile "network_trace.har"
# 
# With custom parameters:
# .\HarConnectivityTest.ps1 -HarFile "trace.har" -HostsCsv "hosts.csv" -OutputCsv "results.csv" -TimeoutSeconds 10
#
# The script will present these options:
# 1. Direct connection (no proxy)
# 2. Use PAC (Proxy Auto-Configuration) file
# 3. Specify proxy manually
#
# For PAC files, you'll be prompted to enter the PAC file path
# For manual proxy, you'll be prompted to enter proxy type, host, and port)
    
    $proxyHost = Read-Host "Enter proxy host/IP address"
    
    do {
        $proxyPortInput = Read-Host "Enter proxy port"
        if ([int]::TryParse($proxyPortInput, [ref]$null) -and [int]$proxyPortInput -gt 0 -and [int]$proxyPortInput -le 65535) {
            $proxyPort = [int]$proxyPortInput
            break
        } else {
            Write-Host "Invalid port number. Please enter a valid port (1-65535)." -ForegroundColor Red
        }
    } while ($true)
    
    $proxyConfig = @{
        Type = $type
        Host = $proxyHost
        Port = $proxyPort
    }
    
    Write-Host "`nProxy configuration:" -ForegroundColor Yellow
    Write-Host "Type: $($proxyConfig.Type)" -ForegroundColor White
    Write-Host "Host: $($proxyConfig.Host)" -ForegroundColor White
    Write-Host "Port: $($proxyConfig.Port)" -ForegroundColor White
    
    # Test proxy connectivity
    Write-Host "`nTesting proxy connectivity..." -ForegroundColor Cyan
    $proxyTestResult = Test-ProxyConnectivity -ProxyConfig $proxyConfig
    
    if ($proxyTestResult.Success) {
        Write-Host "✓ Proxy is reachable" -ForegroundColor Green
    } else {
        Write-Host "✗ Proxy connection failed: $($proxyTestResult.Error)" -ForegroundColor Red
        $continue = Read-Host "Do you want to continue anyway? (y/n)"
        if ($continue -notmatch '^[yY]') {
            return $null
        }
    }
    
    return $proxyConfig
}

# Function to test proxy connectivity
function Test-ProxyConnectivity {
    param(
        [hashtable]$ProxyConfig,
        [int]$Timeout = 5
    )
    
    try {
        $tcpClient = New-Object System.Net.Sockets.TcpClient
        $connect = $tcpClient.BeginConnect($ProxyConfig.Host, $ProxyConfig.Port, $null, $null)
        $wait = $connect.AsyncWaitHandle.WaitOne($Timeout * 1000, $false)
        
        if ($wait) {
            try {
                $tcpClient.EndConnect($connect)
                $tcpClient.Close()
                return @{
                    Success = $true
                    Error = $null
                }
            }
            catch {
                $tcpClient.Close()
                return @{
                    Success = $false
                    Error = $_.Exception.Message
                }
            }
        } else {
            $tcpClient.Close()
            return @{
                Success = $false
                Error = "Connection timeout"
            }
        }
    }
    catch {
        return @{
            Success = $false
            Error = $_.Exception.Message
        }
    }
}

# Function to test TCP connectivity with optional proxy support
function Test-TcpConnection {
    param(
        [string]$Target,
        [int]$Port,
        [int]$Timeout = 5,
        [hashtable]$ProxyConfig = $null
    )
    
    try {
        if ($ProxyConfig) {
            # Test connection through proxy
            return Test-ProxyConnection -Target $Target -Port $Port -ProxyConfig $ProxyConfig -Timeout $Timeout
        }
        else {
            # Direct connection
            $tcpClient = New-Object System.Net.Sockets.TcpClient
            $stopwatch = [System.Diagnostics.Stopwatch]::StartNew()
            $connect = $tcpClient.BeginConnect($Target, $Port, $null, $null)
            $wait = $connect.AsyncWaitHandle.WaitOne($Timeout * 1000, $false)
            
            if ($wait) {
                try {
                    $tcpClient.EndConnect($connect)
                    $stopwatch.Stop()
                    $result = @{
                        Success = $true
                        Error = $null
                        ResponseTime = $stopwatch.ElapsedMilliseconds
                        Method = "Direct"
                    }
                }
                catch {
                    $stopwatch.Stop()
                    $result = @{
                        Success = $false
                        Error = $_.Exception.Message
                        ResponseTime = $null
                        Method = "Direct"
                    }
                }
            }
            else {
                $stopwatch.Stop()
                $result = @{
                    Success = $false
                    Error = "Connection timeout after $Timeout seconds"
                    ResponseTime = $null
                    Method = "Direct"
                }
            }
            
            $tcpClient.Close()
            return $result
        }
    }
    catch {
        return @{
            Success = $false
            Error = $_.Exception.Message
            ResponseTime = $null
            Method = if ($ProxyConfig) { "Proxy" } else { "Direct" }
        }
    }
}

# Function to test connection through proxy
function Test-ProxyConnection {
    param(
        [string]$Target,
        [int]$Port,
        [hashtable]$ProxyConfig,
        [int]$Timeout = 5
    )
    
    try {
        $stopwatch = [System.Diagnostics.Stopwatch]::StartNew()
        
        # Create TCP client and connect to proxy
        $tcpClient = New-Object System.Net.Sockets.TcpClient
        $proxyConnect = $tcpClient.BeginConnect($ProxyConfig.Host, $ProxyConfig.Port, $null, $null)
        $proxyWait = $proxyConnect.AsyncWaitHandle.WaitOne($Timeout * 1000, $false)
        
        if (-not $proxyWait) {
            $stopwatch.Stop()
            return @{
                Success = $false
                Error = "Proxy connection timeout after $Timeout seconds"
                ResponseTime = $null
                Method = "Proxy ($($ProxyConfig.Type))"
            }
        }
        
        try {
            $tcpClient.EndConnect($proxyConnect)
            $stream = $tcpClient.GetStream()
            
            # Send CONNECT request for HTTP proxy
            if ($ProxyConfig.Type -eq "PROXY") {
                $connectRequest = "CONNECT $Target`:$Port HTTP/1.1`r`nHost: $Target`:$Port`r`n`r`n"
                $requestBytes = [System.Text.Encoding]::ASCII.GetBytes($connectRequest)
                $stream.Write($requestBytes, 0, $requestBytes.Length)
                
                # Read response
                $buffer = New-Object byte[] 4096
                $bytesRead = $stream.Read($buffer, 0, $buffer.Length)
                $response = [System.Text.Encoding]::ASCII.GetString($buffer, 0, $bytesRead)
                
                if ($response -match "HTTP/1\.[01] 200") {
                    $stopwatch.Stop()
                    $result = @{
                        Success = $true
                        Error = $null
                        ResponseTime = $stopwatch.ElapsedMilliseconds
                        Method = "Proxy ($($ProxyConfig.Type))"
                    }
                }
                else {
                    $stopwatch.Stop()
                    $result = @{
                        Success = $false
                        Error = "Proxy returned: $($response.Split("`r`n")[0])"
                        ResponseTime = $null
                        Method = "Proxy ($($ProxyConfig.Type))"
                    }
                }
            }
            else {
                # For SOCKS proxies, this is a simplified test
                $stopwatch.Stop()
                $result = @{
                    Success = $true
                    Error = $null
                    ResponseTime = $stopwatch.ElapsedMilliseconds
                    Method = "Proxy ($($ProxyConfig.Type))"
                }
            }
            
            $stream.Close()
            $tcpClient.Close()
            return $result
        }
        catch {
            $stopwatch.Stop()
            $tcpClient.Close()
            return @{
                Success = $false
                Error = $_.Exception.Message
                ResponseTime = $null
                Method = "Proxy ($($ProxyConfig.Type))"
            }
        }
    }
    catch {
        return @{
            Success = $false
            Error = $_.Exception.Message
            ResponseTime = $null
            Method = "Proxy ($($ProxyConfig.Type))"
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

# Function to test connectivity for all hosts
function Test-HostConnectivity {
    param(
        [array]$HostList,
        [int]$Timeout = 5,
        [hashtable]$ProxyConfig = $null
    )
    
    $results = @()
    $totalHosts = $HostList.Count
    $currentHost = 0
    
    $connectionMethod = if ($ProxyConfig) { "proxy ($($ProxyConfig.Type) $($ProxyConfig.Host):$($ProxyConfig.Port))" } else { "direct connection" }
    Write-Host "`nTesting connectivity to $totalHosts hosts using $connectionMethod..." -ForegroundColor Yellow
    
    foreach ($hostItem in $HostList) {
        $currentHost++
        $target = $hostItem.Domain
        $port = $hostItem.Port
        
        Write-Host "[$currentHost/$totalHosts] Testing $target`:$port" -ForegroundColor Cyan
        
        # Resolve IP address
        $resolvedIp = Get-IpAddress -Hostname $target
        
        # Test connectivity
        $testResult = Test-TcpConnection -Target $target -Port $port -Timeout $Timeout -ProxyConfig $ProxyConfig
        
        # Create result object
        $result = [PSCustomObject]@{
            'Domain' = $target
            'Port' = $port
            'Scheme' = $hostItem.Scheme
            'ResolvedIP' = if ($resolvedIp) { $resolvedIp } else { "Unable to resolve" }
            'Status' = if ($testResult.Success) { "Connected" } else { "Failed" }
            'ResponseTime_ms' = $testResult.ResponseTime
            'ConnectionMethod' = $testResult.Method
            'Error' = $testResult.Error
            'FirstSeen' = $hostItem.FirstSeen
            'TestDateTime' = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
        }
        
        $results += $result
        
        # Display result
        if ($testResult.Success) {
            Write-Host "  ✓ Success ($($testResult.ResponseTime)ms)" -ForegroundColor Green
        } else {
            Write-Host "  ✗ Failed: $($testResult.Error)" -ForegroundColor Red
        }
    }
    
    return $results
}

# Main script execution
try {
    # Check if HAR file exists
    if (-not (Test-Path $HarFile)) {
        throw "HAR file '$HarFile' not found."
    }
    
    # Handle PAC file configuration
    $proxyConfig = $null
    if ($UsePAC.IsPresent) {
        if ([string]::IsNullOrEmpty($PACFile)) {
            $PACFile = Read-Host "Enter the path to the PAC file"
        }
        
        if (-not (Test-Path $PACFile)) {
            throw "PAC file '$PACFile' not found."
        }
        
        Write-Host "=== PAC CONFIGURATION ===" -ForegroundColor Magenta
        Write-Host "Reading PAC file: $PACFile" -ForegroundColor Green
        
        # Parse PAC file (simplified approach)
        $pacContent = Get-Content $PACFile -Raw
        Write-Host "PAC file loaded successfully" -ForegroundColor Green
        
        # Extract proxy configuration from PAC file
        $proxyPatterns = @(
            'PROXY\s+([^;:\s]+):(\d+)',
            'SOCKS\s+([^;:\s]+):(\d+)',
            'SOCKS5\s+([^;:\s]+):(\d+)',
            'SOCKS4\s+([^;:\s]+):(\d+)'
        )
        
        foreach ($pattern in $proxyPatterns) {
            $matches = [regex]::Matches($pacContent, $pattern, [System.Text.RegularExpressions.RegexOptions]::IgnoreCase)
            if ($matches.Count -gt 0) {
                $match = $matches[0]
                $proxyType = $match.Value.Split()[0]
                $proxyHost = $match.Groups[1].Value
                $proxyPort = [int]$match.Groups[2].Value
                
                $proxyConfig = @{
                    Type = $proxyType
                    Host = $proxyHost
                    Port = $proxyPort
                }
                
                Write-Host "Proxy configuration found: $proxyType $proxyHost`:$proxyPort" -ForegroundColor Yellow
                break
            }
        }
        
        if (-not $proxyConfig) {
            Write-Warning "No proxy configuration found in PAC file. Using direct connection."
            $proxyConfig = $null
        }
    }
    else {
        Write-Host "=== DIRECT CONNECTION MODE ===" -ForegroundColor Magenta
        Write-Host "PAC file not specified. Using direct connections." -ForegroundColor Green
    }
    
    Write-Host "`n=== HAR FILE ANALYSIS ===" -ForegroundColor Magenta
    
    # Extract hosts from HAR file
    $extractedHosts = Extract-HostsFromHar -HarFilePath $HarFile
    
    if ($extractedHosts.Count -eq 0) {
        throw "No hosts found in HAR file."
    }
    
    # Create hosts.csv
    Write-Host "`nCreating hosts CSV file: $HostsCsv" -ForegroundColor Green
    $hostsForCsv = $extractedHosts | ForEach-Object {
        [PSCustomObject]@{
            'Domain' = $_.Domain
            'Port' = $_.Port
            'Scheme' = $_.Scheme
            'FirstSeen' = $_.FirstSeen
        }
    }
    
    $hostsForCsv | Export-Csv -Path $HostsCsv -NoTypeInformation
    Write-Host "Hosts exported to: $HostsCsv" -ForegroundColor White
    
    # Display extracted hosts summary
    Write-Host "`n=== EXTRACTED HOSTS SUMMARY ===" -ForegroundColor Yellow
    $httpHosts = ($extractedHosts | Where-Object { $_.Scheme -eq "http" }).Count
    $httpsHosts = ($extractedHosts | Where-Object { $_.Scheme -eq "https" }).Count
    $otherHosts = $extractedHosts.Count - $httpHosts - $httpsHosts
    
    Write-Host "Total unique hosts: $($extractedHosts.Count)" -ForegroundColor White
    Write-Host "HTTP hosts: $httpHosts" -ForegroundColor White
    Write-Host "HTTPS hosts: $httpsHosts" -ForegroundColor White
    Write-Host "Other protocols: $otherHosts" -ForegroundColor White
    
    # Test connectivity
    Write-Host "`n=== CONNECTIVITY TESTING ===" -ForegroundColor Magenta
    $connectivityResults = Test-HostConnectivity -HostList $extractedHosts -Timeout $TimeoutSeconds -ProxyConfig $proxyConfig
    
    # Export connectivity results
    Write-Host "`nExporting connectivity results to: $OutputCsv" -ForegroundColor Green
    $connectivityResults | Export-Csv -Path $OutputCsv -NoTypeInformation
    
    # Display final summary
    $successCount = ($connectivityResults | Where-Object { $_.Status -eq "Connected" }).Count
    $failedCount = $connectivityResults.Count - $successCount
    
    Write-Host "`n=== CONNECTIVITY SUMMARY ===" -ForegroundColor Yellow
    Write-Host "Total hosts tested: $($connectivityResults.Count)" -ForegroundColor White
    Write-Host "Successful connections: $successCount" -ForegroundColor Green
    Write-Host "Failed connections: $failedCount" -ForegroundColor Red
    Write-Host "Success rate: $([math]::Round(($successCount / $connectivityResults.Count) * 100, 2))%" -ForegroundColor White
    
    Write-Host "`n=== OUTPUT FILES ===" -ForegroundColor Magenta
    Write-Host "Hosts CSV: $HostsCsv" -ForegroundColor White
    Write-Host "Results CSV: $OutputCsv" -ForegroundColor White
    
    # Display top failed connections
    $failedConnections = $connectivityResults | Where-Object { $_.Status -eq "Failed" } | Select-Object -First 5
    if ($failedConnections.Count -gt 0) {
        Write-Host "`n=== TOP FAILED CONNECTIONS ===" -ForegroundColor Red
        foreach ($failed in $failedConnections) {
            Write-Host "$($failed.Domain):$($failed.Port) - $($failed.Error)" -ForegroundColor Red
        }
    }
    
}
catch {
    Write-Host "Error: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}

# Example usage:
# Direct connection:
# .\HarConnectivityTest.ps1 -HarFile "network_trace.har"

# With PAC file (will prompt for PAC file path):
# .\HarConnectivityTest.ps1 -HarFile "network_trace.har" -UsePAC

# With specific PAC file:
# .\HarConnectivityTest.ps1 -HarFile "network_trace.har" -UsePAC -PACFile "proxy.pac"

# With all custom parameters:
# .\HarConnectivityTest.ps1 -HarFile "trace.har" -UsePAC -PACFile "proxy.pac" -HostsCsv "hosts.csv" -OutputCsv "results.csv" -TimeoutSeconds 10