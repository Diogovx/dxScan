$inventoryPath = ".\inventory"
$outputPath = ".\inventory.csv"

try {
    Get-ChildItem -Path $inventoryPath -Filter "*.csv" |
        Select-Object -ExpandProperty FullName | 
        Import-Csv -Delimiter ';' |
        Export-Csv -Path $outputPath -Delimiter ';' -NoTypeInformation -Encoding UTF8
    
    Write-Host "CSV files successfully merged into: $outputPath" -ForegroundColor Green
}
catch {
    Write-Warning "An error occurred while merging files: $($_.Exception.Message)"
}
