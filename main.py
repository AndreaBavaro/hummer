#!/usr/bin/env python3
"""
Zoom Interview Analysis System

This application automates the extraction, analysis, and reporting of Zoom interview data.
It leverages a Zoom bot to join meetings, captures recordings and transcriptions,
processes them through Hume AI for analytics, uses an LLM for insights,
and compiles everything into a PDF report sent to the interviewer.
"""

import os
import sys
import logging
import json
import time
import argparse
from pathlib import Path
from dotenv import load_dotenv

# Add the src directory to the path
sys.path.append(os.path.join(os.path.dirname(__file__), "src"))

# Import application components
from src.zoom_bot.controller import ZoomBotController
from src.zoom_bot.scheduler import ZoomBotScheduler
from src.storage.manager import StorageManager
from src.analytics.processor import AnalyticsProcessor
from src.reporting.generator import ReportGenerator
from src.email.sender import EmailSender
from src.email.monitor import EmailMonitor
from src.database.manager import DatabaseManager
from src.database.schema import create_database_schema
from src.cli.manual_mode import run_manual_mode as cli_run_manual_mode
from src.cli.monitor_mode import run_monitor_mode as cli_run_monitor_mode
from src.cli.meeting_manager import run_meeting_manager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("app.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def main():
    """Main application entry point."""
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description="Zoom Interview Analysis System")
    parser.add_argument("--mode", choices=["manual", "monitor", "manage"], default="manual",
                      help="Operation mode: manual (join a single meeting), monitor (monitor email for invitations), or manage (manage existing meetings)")
    parser.add_argument("--config", default=".env",
                      help="Path to configuration file")
    parser.add_argument("--init-db", action="store_true",
                      help="Initialize the database schema")
    args = parser.parse_args()
    
    print("=" * 80)
    print("ZOOM INTERVIEW ANALYSIS SYSTEM")
    print("=" * 80)
    
    if args.mode == "manual":
        print("\nMANUAL MODE: Join a single Zoom meeting")
        print("\nThis application will:")
        print("1. Join a Zoom meeting using the Attendee API")
        print("2. Record the meeting and capture the transcript")
        print("3. Process the recording with Hume AI for emotional analysis")
        print("4. Generate insights using an LLM")
        print("5. Create a comprehensive PDF report")
    elif args.mode == "monitor":
        print("\nMONITOR MODE: Monitor email for Zoom meeting invitations")
        print("\nThis application will:")
        print("1. Monitor an email inbox for Zoom meeting invitations")
        print("2. Automatically join scheduled meetings")
        print("3. Record meetings and capture transcripts")
        print("4. Process recordings with Hume AI for emotional analysis")
        print("5. Generate insights and create PDF reports")
        print("6. Send reports to interviewers")
    else:
        print("\nMANAGE MODE: View and manage existing meetings")
        print("\nThis application will:")
        print("1. List all meetings in the database")
        print("2. View meeting details")
        print("3. Update meeting status")
        print("4. Delete meetings")
    
    print("\nNote: You must have the required API keys in your .env file.")
    print("=" * 80)
    
    # Load configuration
    config_path = args.config
    if not os.path.exists(config_path):
        logger.error(f"Configuration file not found: {config_path}")
        print(f"\nERROR: Configuration file not found: {config_path}")
        print("Please create a .env file with your API keys (see README.md for details).")
        return
    
    load_dotenv(config_path)
    
    # Initialize database
    db_path = os.environ.get('DATABASE_PATH', './data/database.db')
    
    # Create database schema if requested or if the database doesn't exist
    if args.init_db or not os.path.exists(db_path):
        print("\nInitializing database schema...")
        if create_database_schema(db_path):
            print("Database schema created successfully.")
        else:
            print("Failed to create database schema.")
            return
    
    # Initialize database manager
    try:
        db_manager = DatabaseManager(db_path)
        logger.info("Initialized DatabaseManager")
    except Exception as e:
        logger.error(f"Failed to initialize DatabaseManager: {e}")
        print(f"\nERROR: Failed to initialize database manager: {e}")
        return
    
    # Choose mode
    if args.mode == "manual":
        # Initialize Zoom bot scheduler
        try:
            # Pass the database manager instance to the scheduler
            scheduler = ZoomBotScheduler(db_manager)
            logger.info("Initialized ZoomBotScheduler")
        except Exception as e:
            logger.error(f"Failed to initialize ZoomBotScheduler: {e}")
            print(f"\nERROR: Failed to initialize Zoom bot scheduler: {e}")
            return
        
        # Run manual mode
        cli_run_manual_mode(db_manager, scheduler)
    
    elif args.mode == "monitor":
        # Initialize Zoom bot scheduler
        try:
            # Pass the database manager instance to the scheduler
            scheduler = ZoomBotScheduler(db_manager)
            logger.info("Initialized ZoomBotScheduler")
        except Exception as e:
            logger.error(f"Failed to initialize ZoomBotScheduler: {e}")
            print(f"\nERROR: Failed to initialize Zoom bot scheduler: {e}")
            return
        
        # Run monitor mode
        cli_run_monitor_mode(db_manager, scheduler)
    
    else:  # manage mode
        # Run meeting manager
        run_meeting_manager(db_manager)

if __name__ == "__main__":
    main()
