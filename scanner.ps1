<#
.SYNOPSIS
    Collects central system information and updates a central CSV file.
#>


$domainName = "domainname\"

$inventoryPath = "path\to\file"

try {
    $csInfo = Get-CimInstance -ClassName Win32_ComputerSystem
    $userInfo = $csInfo.UserName.trim($domainName)
    $osInfo = Get-CimInstance -ClassName Win32_OperatingSystem
    $cpuInfo = Get-CimInstance -ClassName Win32_Processor | Select-Object -First 1
    $biosInfo = Get-CimInstance -ClassName Win32_BIOS
    $diskInfo = Get-CimInstance Win32_DiskDrive | Select-Object Model, Size, MediaType

    $macWifi  = (Get-NetAdapter | Select-Object Name, MacAddress | Where-Object { $_.Name -match "Wi-Fi|Wireless" } | Select-Object -ExpandProperty MacAddress -First 1)
    $macLan = (Get-NetAdapter | Select-Object Name, MacAddress | Where-Object { $_.Name -eq "Ethernet" }).MacAddress

    $ipInfo = (Get-NetIPAddress -AddressFamily IPv4 |
        Where-Object {
            $_.IPAddress -notlike "169.*" -and
            $_.IPAddress -ne "127.0.0.1" -and
            $_.InterfaceAlias -notmatch "Virtual|VMware|Loopback|Default Switch"
        } | Select-Object -First 1).IPAddress

    $currentOsName = $osInfo.Caption.trim()

    $localData = [PSCustomObject]@{
        "Hostname" = $env:COMPUTERNAME
        "Manufacturer" = $csInfo.Manufacturer 
        "Model" = $csInfo.Model
        "Last logged in user" = $userInfo
        "Serial number" = $biosInfo.SerialNumber.trim()
        "Current OS" = $currentOsName
        "Windows Installation Date" = $osInfo.InstallDate
        "Last Reboot" = $osInfo.LastBootUpTime
        "CPU" = $cpuInfo.Name.trim()
        "RAM GB" = [math]::Round($csInfo.TotalPhysicalMemory / 1GB, 2)
        "Disk GB" = [math]::Round($diskInfo.Size / 1GB, 2)
        "MAC Wifi" = $macWifi
        "MAC LAN" = $macLan
        "IP" = $ipInfo
        "Last Verification" = Get-Date
    }
}
catch {
    Write-Warning "Failed to collect local information. Aborting."
    return
}

try{
    $localData | Export-Csv -Path $inventoryPath -NoTypeInformation -Delimiter ";"

} catch{
    Write-Host "Error saving file."
}