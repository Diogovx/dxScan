<#
.SYNOPSIS
    Coleta Informações centrais do sistema e atualiza um arquivo CSV central.
.DESCRIPTION
    Este script coleta informações detalhadas sobre o sistema, incluindo hardware, sistema operacional,
    rede, discos físicos e lógicos, impressoras e software instalado.

    Os resultados são salvos em arquivos CSV e JSON em diretórios configuráveis. Além de guardar dados em um banco de dados.
.OUTPUTS
    - Um arquivo CSV com o inventário de hardware.
    - Um arquivo JSON com o inventário de hardware.
    - Um arquivo CSV com a lista de softwares instalados.
    - Um arquivo JSON com a lista de software instalados.
    - Um arquivo LOG para monitorar as execuções
.NOTES
    Autor: Diogo Velozo Xavier
    Versão: 2.0
    Github: https://github.com/Diogovx/DXSCAN
#>

$scriptPath = Split-Path -Parent $MyInvocation.MyCommand.Definition
$configFile = Join-Path -Path $scriptPath -ChildPath "config.json"

if (Test-Path -Path $configFile) {
    try {
        $config = Get-Content -Path $configFile -Raw | ConvertFrom-Json
    } catch {
        Write-Error "O arquivo config.json está mal formatado."
        exit
    }
} else {
    Write-Error "Arquivo config.json não encontrado. Abortando."
    exit
}

if (-not (Test-Path -Path $config.LogPath)) { New-Item -Path $config.LogPath -ItemType Directory -Force | Out-Null }
$logFile = Join-Path -Path $config.LogPath -ChildPath "$($env:COMPUTERNAME)_$(Get-Date -Format 'yyyy-MM-dd_HH-mm-ss').log"
Start-Transcript -Path $logFile -Append

function Get-SystemInformation {
    try {
        $csInfo = Get-CimInstance -ClassName Win32_ComputerSystem
        $cspInfo = Get-CimInstance -ClassName Win32_ComputerSystemProduct
        $osInfo = Get-CimInstance -ClassName Win32_OperatingSystem
        $cpuInfo = Get-CimInstance -ClassName Win32_Processor | Select-Object -First 1
        $biosInfo = Get-CimInstance -ClassName Win32_BIOS
        
        $chassis = Get-CimInstance -ClassName Win32_SystemEnclosure | Select-Object -ExpandProperty ChassisTypes
        $tipoEquipamento = if ($chassis -match "9|10|11|12|14") { "Notebook" } else { "Desktop" }
        
        $bateriaSaude = "N/A (Desktop)"
        if ($tipoEquipamento -eq "Notebook") {
            try {
                $bateriaData = Get-WmiObject -Namespace root\wmi -Class BatteryFullChargedCapacity -ErrorAction Stop | Select-Object -First 1
                $bateriaEstatica = Get-WmiObject -Namespace root\wmi -Class BatteryStaticData -ErrorAction Stop | Select-Object -First 1
                
                if ($bateriaData.FullChargedCapacity -and $bateriaEstatica.DesignedCapacity -and $bateriaEstatica.DesignedCapacity -gt 0) {
                    $pct = [math]::Round(($bateriaData.FullChargedCapacity / $bateriaEstatica.DesignedCapacity) * 100, 0)
                    $bateriaSaude = "$pct%"
                } else {
                     $batteryBasic = Get-CimInstance -ClassName Win32_Battery -ErrorAction SilentlyContinue | Select-Object -First 1
                     if ($batteryBasic) {
                         $bateriaSaude = "$($batteryBasic.EstimatedChargeRemaining)% (Carga Atual)"
                     } else {
                         $bateriaSaude = "Falha ao ler dados ACPI"
                     }
                }
            } catch {
                 $bateriaSaude = "Bloqueado pelo hardware/driver"
            }
        }

        $currentOsName = $osInfo.Caption
        $manufacturer = $csInfo.Manufacturer.Trim()
        $rawModel = $csInfo.Model.Trim()
        $altModel = $cspInfo.Version.Trim()

        switch -Regex ($manufacturer) {
            "Lenovo" { $normalizedModel = if ($altModel) { $altModel } else { $rawModel } }
            "Dell" { $normalizedModel = $rawModel }
            "HP" { $normalizedModel = $rawModel }
            "Acer" { $normalizedModel = $rawModel }
            default { $normalizedModel = if ($rawModel -and $rawModel -notmatch "To Be Filled|System") { $rawModel } else { "Modelo Genérico" } }
        }

        $uptime = (Get-Date) - $osInfo.LastBootUpTime
        $uptimeFormatted = "$($uptime.Days)d $($uptime.Hours)h $($uptime.Minutes)m"
        $userInfo = $csInfo.UserName -replace "$($config.DomainName)\\", ""
    
        return [PSCustomObject]@{
            "Hostname"             = $env:COMPUTERNAME
            "Serial_Number"        = $biosInfo.SerialNumber.Trim()
            "Manufacturer"         = $csInfo.Manufacturer
            "Model"                = $normalizedModel
            "Equipment_Type"       = $tipoEquipamento
            "BIOS_Version"         = $biosInfo.SMBIOSBIOSVersion
            "Processor"            = $cpuInfo.Name.Trim()
            "RAM_GB"               = [math]::Round($csInfo.TotalPhysicalMemory / 1GB, 2)
            "Operating_System"     = $currentOsName
            "OS_Installation_Date" = $osInfo.InstallDate
            "Uptime"               = $uptimeFormatted
            "Last_Logged_User"     = $userInfo
            "Battery_Health"       = $bateriaSaude
        }
    }
    catch { Write-Warning "Falha ao coletar sistema: $($_.Exception.Message)"; return $null }
}

function Get-SecurityInformation {
    try {
        $cylanceAtivo = try {
            $processo = Get-Process -Name "CylanceSvc", "CylanceUI" -ErrorAction SilentlyContinue
            $servico = Get-Service -Name "CylanceSvc" -ErrorAction SilentlyContinue

            if ($processo -or ($servico -and $servico.Status -eq 'Running')) { "Ativo" } 
            elseif ($servico -and $servico.Status -ne 'Running') { "Instalado, mas Parado!" } 
            else { 
                $instalado = Get-Package -Name "*Cylance*" -ErrorAction SilentlyContinue
                if ($instalado) { "Instalado (Status oculto)" } else { "Não Instalado" }
            }
        } catch { "Erro ao verificar" }

        $admins = try {
            $group = Get-LocalGroupMember -Group "Administradores" -ErrorAction Stop | 
                     Where-Object { $_.ObjectClass -eq 'User' -and $_.Name -notmatch "Administrator|Administrador" } |
                     Select-Object -ExpandProperty Name
            if ($admins) { $admins -join '; ' } else { "Apenas Padrão" }
        } catch { "Erro ao ler" }

        $reboot = $false
        if (Test-Path "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Component Based Servicing\RebootPending") { $reboot = $true }
        if (Test-Path "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\WindowsUpdate\Auto Update\RebootRequired") { $reboot = $true }
        $rebootStatus = if ($reboot) { "Sim" } else { "Não" }

        return [PSCustomObject]@{
            "Antivirus_Status" = $cylanceAtivo
            "Local_Admins"     = $admins
            "Reboot_Pending"   = $rebootStatus
        }
    }
    catch { Write-Warning "Falha segurança"; return $null }
}

function Get-MonitorsInformation {
    try {
        $monitors = Get-CimInstance -Namespace root\wmi -ClassName WmiMonitorID -ErrorAction Stop
        $monitorList = foreach ($mon in $monitors) {
            $fabricante = ($mon.ManufacturerName | Where-Object { $_ -ne 0 } | ForEach-Object { [char]$_ }) -join ''
            $modelo = ($mon.UserFriendlyName | Where-Object { $_ -ne 0 } | ForEach-Object { [char]$_ }) -join ''
            $serial = ($mon.SerialNumberID | Where-Object { $_ -ne 0 } | ForEach-Object { [char]$_ }) -join ''
            
            [PSCustomObject]@{ Manufacturer = $fabricante.Trim(); Model = $modelo.Trim(); Serial = $serial.Trim() }
        }
        return $monitorList
    } catch { return @() }
}

function Get-DiskInformation {
    try {
        $logicalDisks = Get-CimInstance -ClassName Win32_LogicalDisk | Where-Object { $_.DriveType -eq 3 } | ForEach-Object {
            [PSCustomObject]@{ "Drive" = $_.DeviceID; "Size_GB" = [math]::Round($_.Size / 1GB, 2); "Free_GB" = [math]::Round($_.FreeSpace / 1GB, 2) }
        }
        return $logicalDisks
    } catch { return $null }
}

function Get-NetworkInformation {
    try {
        $adapters = Get-NetAdapter -Physical | Where-Object { $_.Status -eq 'Up' }
        $networkInfo = foreach ($adapter in $adapters) {
            $ip = Get-NetIPAddress -InterfaceIndex $adapter.InterfaceIndex -AddressFamily IPv4 | Select-Object -ExpandProperty IPAddress -ErrorAction SilentlyContinue
            [PSCustomObject]@{ Name = $adapter.Name; MAC = $adapter.MacAddress; IP = $ip -join ", " }
        }
        return $networkInfo
    } catch { return $null }
}

function Get-ProgramsInventory {
    try {
        return Get-Package | Where-Object { $_.ProviderName -ne "msu" -and $_.ProviderName -ne "PowerShellGet" } | Select-Object Name, Version | Sort-Object Name
    } catch { return $null }
}

function Invoke-SystemInventory {
    if (-not (Test-Path -Path $config.ComputerInventoryPath)) { New-Item -Path $config.ComputerInventoryPath -ItemType Directory -Force | Out-Null }
    
    $systemInfo = Get-SystemInformation
    $securityInfo = Get-SecurityInformation
    $monitoresInfo = Get-MonitorsInformation
    $diskInfo = Get-DiskInformation
    $networkInfo = Get-NetworkInformation
    $softwareInfo = Get-ProgramsInventory

    # Objeto mestre com as chaves exatas em inglês que a API espera
    $jsonInventory = [PSCustomObject]@{
        "Verification_Date" = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
        "System"            = $systemInfo
        "Security"          = $securityInfo
        "Monitors"          = $monitoresInfo
        "Disks"             = $diskInfo
        "Network"           = $networkInfo
        "Softwares"         = $softwareInfo
    }

    # Salva o arquivo local (opcional)
    $baseFileName = "$($systemInfo.Serial_Number)_$($env:COMPUTERNAME)"
    $jsonHardwarePath = Join-Path -Path $config.ComputerInventoryPath -ChildPath "$baseFileName.json"
    $jsonInventory | ConvertTo-Json -Depth 10 | Set-Content -Path $jsonHardwarePath -Encoding UTF8
    
    Write-Host "Inventário JSON gerado com sucesso em: $jsonHardwarePath" -ForegroundColor Green

    $JsonPayload = $jsonInventory | ConvertTo-Json -Depth 10 -Compress
    
    $Utf8Bytes = [System.Text.Encoding]::UTF8.GetBytes($JsonPayload)
    
    $ApiUrl = $config.ApiUrl

    try {
        Write-Host "Enviando dados para o DXSCAN API..." -ForegroundColor Cyan
        
        $Response = Invoke-RestMethod -Uri $ApiUrl -Method Post -Body $Utf8Bytes -ContentType "application/json; charset=utf-8"
        
        Write-Host "Sucesso! O backend respondeu: $($Response.message)" -ForegroundColor Green
        Write-Host "Serial do Computador salvo: $($Response.computer_serial)" -ForegroundColor Green
    } 
    catch {
        Write-Host "Erro ao tentar enviar para a API!" -ForegroundColor Red
        Write-Host $_.Exception.Message -ForegroundColor Red
    }
}

Invoke-SystemInventory
Stop-Transcript