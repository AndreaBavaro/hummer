#!/usr/bin/env python3
"""
Setup script for the Zoom Interview Analysis System.
This script helps users set up the application by:
1. Creating a virtual environment
2. Installing dependencies in the virtual environment
3. Creating the .env file from the template
4. Initializing the database
"""

import os
import sys
import subprocess
import shutil
import logging
import venv
from pathlib import Path

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

def create_virtual_environment():
    """Create a virtual environment if it doesn't exist."""
    print("\n=== Creating Virtual Environment ===\n")
    
    if os.path.exists("venv"):
        print("Virtual environment already exists. Skipping.")
        return True
    
    try:
        print("Creating virtual environment...")
        venv.create("venv", with_pip=True)
        print("Virtual environment created successfully.")
        return True
    except Exception as e:
        logger.error(f"Error creating virtual environment: {e}")
        print(f"Error creating virtual environment: {e}")
        return False

def get_python_executable():
    """Get the Python executable from the virtual environment."""
    if os.name == 'nt':  # Windows
        return os.path.join("venv", "Scripts", "python.exe")
    else:  # Unix/Linux/Mac
        return os.path.join("venv", "bin", "python")

def install_dependencies():
    """Install dependencies from requirements.txt in the virtual environment."""
    print("\n=== Installing Dependencies ===\n")
    
    python_executable = get_python_executable()
    
    try:
        # Install core dependencies first
        print("Installing core dependencies...")
        subprocess.check_call([python_executable, "-m", "pip", "install", 
                              "python-dotenv==1.0.1", 
                              "requests==2.31.0",
                              "pydantic==2.10.6",
                              "SQLAlchemy==2.0.39",
                              "tabulate==0.9.0",
                              "pandas==2.2.2",
                              "yagmail==0.15.293",
                              "imaplib2==3.6",
                              "email-validator==2.2.0",
                              "google-api-python-client==2.107.0",
                              "google-auth-httplib2==0.1.0",
                              "google-auth-oauthlib==1.1.0"])
        
        # Try to install the rest, but continue if some fail
        print("\nInstalling optional dependencies...")
        try:
            subprocess.check_call([python_executable, "-m", "pip", "install", "-r", "requirements.txt"])
            print("All dependencies installed successfully.")
        except subprocess.CalledProcessError as e:
            logger.warning(f"Some optional dependencies could not be installed: {e}")
            print("\nWARNING: Some optional dependencies could not be installed.")
            print("This is normal and the application will still function with reduced capabilities.")
            print("You can manually install specific dependencies later if needed.")
        
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"Error installing core dependencies: {e}")
        print(f"Error installing core dependencies: {e}")
        return False

def create_env_file():
    """Create .env file from template if it doesn't exist."""
    print("\n=== Creating .env File ===\n")
    
    if os.path.exists(".env"):
        print(".env file already exists. Skipping.")
        return True
    
    if not os.path.exists("config_template.env"):
        logger.error("config_template.env not found")
        print("Error: config_template.env not found.")
        return False
    
    try:
        shutil.copy("config_template.env", ".env")
        print(".env file created from template.")
        print("Please edit the .env file to add your API keys and credentials.")
        return True
    except Exception as e:
        logger.error(f"Error creating .env file: {e}")
        print(f"Error creating .env file: {e}")
        return False

def initialize_database():
    """Initialize the database schema."""
    print("\n=== Initializing Database ===\n")
    
    python_executable = get_python_executable()
    
    try:
        # Create the data directory if it doesn't exist
        os.makedirs("data", exist_ok=True)
        
        # Run the main script with --init-db flag
        subprocess.check_call([python_executable, "main.py", "--init-db"])
        print("Database initialized successfully.")
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"Error initializing database: {e}")
        print(f"Error initializing database: {e}")
        return False

def create_data_directories():
    """Create necessary data directories."""
    print("\n=== Creating Data Directories ===\n")
    
    directories = [
        "data",
        "data/recordings",
        "data/transcripts",
        "data/reports"
    ]
    
    try:
        for directory in directories:
            os.makedirs(directory, exist_ok=True)
            print(f"Created directory: {directory}")
        return True
    except Exception as e:
        logger.error(f"Error creating directories: {e}")
        print(f"Error creating directories: {e}")
        return False

def create_batch_scripts():
    """Create batch scripts for running the application."""
    print("\n=== Creating Batch Scripts ===\n")
    
    scripts = {
        "run.bat": """@echo off
echo ================================================================================
echo ZOOM INTERVIEW ANALYSIS SYSTEM
echo ================================================================================
echo.

REM Activate the virtual environment
call venv\\Scripts\\activate.bat

REM Run the application with any passed arguments
python main.py %*

REM Deactivate the virtual environment when done
call deactivate

echo.
echo ================================================================================
echo Application closed.
echo ================================================================================
""",
        "run_manual.bat": """@echo off
echo ================================================================================
echo ZOOM INTERVIEW ANALYSIS SYSTEM - MANUAL MODE
echo ================================================================================
echo.

REM Activate the virtual environment
call venv\\Scripts\\activate.bat

REM Run the application in manual mode
python main.py --mode manual

REM Deactivate the virtual environment when done
call deactivate

echo.
echo ================================================================================
echo Application closed.
echo ================================================================================
""",
        "run_monitor.bat": """@echo off
echo ================================================================================
echo ZOOM INTERVIEW ANALYSIS SYSTEM - MONITOR MODE
echo ================================================================================
echo.

REM Activate the virtual environment
call venv\\Scripts\\activate.bat

REM Run the application in monitor mode
python main.py --mode monitor

REM Deactivate the virtual environment when done
call deactivate

echo.
echo ================================================================================
echo Application closed.
echo ================================================================================
""",
        "run_manage.bat": """@echo off
echo ================================================================================
echo ZOOM INTERVIEW ANALYSIS SYSTEM - MANAGE MODE
echo ================================================================================
echo.

REM Activate the virtual environment
call venv\\Scripts\\activate.bat

REM Run the application in manage mode
python main.py --mode manage

REM Deactivate the virtual environment when done
call deactivate

echo.
echo ================================================================================
echo Application closed.
echo ================================================================================
"""
    }
    
    try:
        for filename, content in scripts.items():
            with open(filename, "w") as f:
                f.write(content)
            print(f"Created script: {filename}")
        return True
    except Exception as e:
        logger.error(f"Error creating batch scripts: {e}")
        print(f"Error creating batch scripts: {e}")
        return False

def main():
    """Main setup function."""
    print("=" * 80)
    print("ZOOM INTERVIEW ANALYSIS SYSTEM SETUP")
    print("=" * 80)
    print("\nThis script will help you set up the Zoom Interview Analysis System.")
    print("It will:")
    print("1. Create a virtual environment")
    print("2. Install dependencies in the virtual environment")
    print("3. Create the .env file from the template")
    print("4. Create necessary data directories")
    print("5. Initialize the database")
    print("6. Create batch scripts for running the application")
    print("\nPress Enter to continue or Ctrl+C to cancel.")
    input()
    
    # Create virtual environment
    if not create_virtual_environment():
        print("\nSetup failed at virtual environment creation step.")
        return
    
    # Install dependencies
    if not install_dependencies():
        print("\nSetup failed at dependency installation step.")
        return
    
    # Create .env file
    if not create_env_file():
        print("\nSetup failed at .env file creation step.")
        return
    
    # Create data directories
    if not create_data_directories():
        print("\nSetup failed at data directory creation step.")
        return
    
    # Initialize database
    if not initialize_database():
        print("\nSetup failed at database initialization step.")
        return
    
    # Create batch scripts
    if not create_batch_scripts():
        print("\nSetup failed at batch script creation step.")
        return
    
    print("\n=== Setup Complete ===\n")
    print("The Zoom Interview Analysis System has been set up successfully.")
    print("Next steps:")
    print("1. Edit the .env file to add your API keys and credentials")
    print("2. Run the application using one of the batch scripts:")
    print("   - run.bat - Run with custom arguments")
    print("   - run_manual.bat - Run in manual mode")
    print("   - run_monitor.bat - Run in monitor mode")
    print("   - run_manage.bat - Run in manage mode")
    print("\nFor more information, see the README.md file.")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nSetup cancelled by user.")
    except Exception as e:
        logger.exception(f"Unexpected error during setup: {e}")
        print(f"\nUnexpected error during setup: {e}")
        print("Please check the logs for details.")
