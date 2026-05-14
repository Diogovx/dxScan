# dxScan - Automated IT Asset Inventory System

dxScan is a modern, client-server architecture tool designed to automatically collect, transmit, and store detailed hardware and software inventories from Windows machines across a network.

Gone are the days of manually merging CSV files. dxScan now utilizes a robust REST API to ingest data seamlessly into a relational database.

## 🏗️ Architecture Overview

The system is divided into three main components:

1. **Client Agent (PowerShell):** A lightweight script that runs on end-user machines. It queries deep system metrics using WMI/CIM, compiles the data into a structured JSON payload, and sends it to the backend via an HTTP POST request.
2. **Backend API (Python/FastAPI):** A high-performance RESTful API that acts as the gateway. It uses Pydantic to strictly validate incoming payloads and processes the data asynchronously.
3. **Database (PostgreSQL):** A relational database where the information is securely stored and organized across multiple tables (Computers, Disks, Monitors, Networks, Softwares) via SQLAlchemy ORM.

## ✨ Features

- **Deep System Telemetry:** Collects OS details, CPU, RAM, BIOS version, and battery health.
- **Security Posture:** Checks for active Antivirus (e.g., Cylance), local administrators, and pending system reboots.
- **Peripheral & Network Tracking:** Inventories connected monitors (with serial numbers), logical disks, and network adapters.
- **Software Auditing:** Retrieves a comprehensive list of installed software and their versions.
- **Centralized API Ingestion:** Handles multiple simultaneous requests effortlessly using SQLAlchemy connection pooling.
- **Built-in Documentation:** Automatically generated Swagger UI to test and explore API endpoints.

## 📋 Requirements

**For the Backend:**

- Python 3.10+
- PostgreSQL Server
- `uv` package manager (recommended)

**For the Client:**

- Windows OS with PowerShell 5.1 or higher
- Network access to the backend API

---

## 🚀 How to Use

### 1. Database Setup

1. Open your PostgreSQL manager (e.g., DBeaver).
2. Create a new database named `dxscan_db` (or your preferred name).

### 2. Backend Setup

1. Navigate to the `backend` directory.

2. Create a `.env` file at the root of the backend folder with your database credentials:

   ```env
   DB_USER=postgres
   DB_PASSWORD=your_password
   DB_HOST=localhost
   DB_PORT=5432
   DB_NAME=dxscan_db

### 3. Client Setup & Execution

1. Navigate to the folder containing the PowerShell script.

2. Ensure your config.json is properly configured with your domain details and local paths (if logging is enabled).

3. Ensure the $ApiUrl variable inside the PowerShell script points to your active backend (e.g., http://YOUR_SERVER_IP:8000/api/v1/inventory/).

4. Run the script on the target machine:

    ```PowerShell
    .\scanner.ps1
    ```

5. The script will automatically collect the data, convert it to a secure UTF-8 byte stream, and POST it to the API. You will receive a success message in the console once the data is saved in the database.

## 📄 License

This project is licensed under the MIT License.
