# dxScan

dxScan is a simple PowerShell tool for collecting information from computers on a network and consolidating it into CSV files.

## Features

- Collects system, user, hardware, and network information.
- Saves the collected data in individual CSV files.
- Allows you to merge CSV files into a single consolidated file.

## How to use

1. Run the `scanner.ps1` script on each computer you want to record. It will collect the information and save it to a CSV file.
2. After collecting data from all computers, run the `file_manager.ps1` script to merge all CSV files into a single file called `inventory.csv`.

## Requirements

- PowerShell 5.1 or higher
- Permissions to run scripts on the system

## License

This project is licensed under the [MIT License](LICENSE).
