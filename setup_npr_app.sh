#!/bin/bash

# Script for installing required dependencies for the NPR Flask application on Linux

# Step 1: Update the package list
echo "Updating package list..."
sudo apt update

# Step 2: Install Python3 and pip3 if not installed
echo "Installing Python3 and pip3..."
sudo apt install -y python3 python3-pip

# Step 3: Install ODBC driver for SQL Server
echo "Installing ODBC Driver for SQL Server..."
curl https://packages.microsoft.com/keys/microsoft.asc | sudo apt-key add -
curl https://packages.microsoft.com/config/ubuntu/$(lsb_release -rs)/prod.list | sudo tee /etc/apt/sources.list.d/msprod.list
sudo apt update
sudo ACCEPT_EULA=Y apt install -y msodbcsql17 unixodbc-dev

# Step 4: Install required Python packages
echo "Installing required Python packages..."
pip3 install flask pyodbc python-dotenv apscheduler

# Step 5: Installation complete
echo -e "\nAll required packages have been installed!"
