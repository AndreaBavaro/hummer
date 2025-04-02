"""
Command-line interface for email monitoring mode.
This module provides a CLI for monitoring emails for Zoom meeting invitations.
"""

import os
import sys
import logging
import getpass
import time
import signal
from dotenv import load_dotenv

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Flag to indicate whether the monitoring should continue
keep_monitoring = True

def signal_handler(sig, frame):
    """
    Handle Ctrl+C to gracefully stop the monitoring.
    """
    global keep_monitoring
    logger.info("Stopping email monitoring...")
    keep_monitoring = False

def get_email_credentials():
    """
    Prompt the user for email credentials if not provided in environment variables.
    
    Returns:
        tuple: A tuple containing the email address, password, and IMAP server.
    """
    # Get email credentials from environment variables
    email_address = os.environ.get('EMAIL_ADDRESS')
    password = os.environ.get('EMAIL_PASSWORD')
    imap_server = os.environ.get('EMAIL_IMAP_SERVER')
    
    # If any credential is missing, prompt the user
    if not email_address:
        email_address = input("Enter email address: ").strip()
        while not email_address or "@" not in email_address:
            print("Invalid email address.")
            email_address = input("Enter email address: ").strip()
    
    if not password:
        password = getpass.getpass("Enter email password: ")
        while not password:
            print("Password is required.")
            password = getpass.getpass("Enter email password: ")
    
    if not imap_server:
        imap_server = input("Enter IMAP server (e.g., imap.gmail.com): ").strip()
        while not imap_server:
            print("IMAP server is required.")
            imap_server = input("Enter IMAP server (e.g., imap.gmail.com): ").strip()
    
    return email_address, password, imap_server

def get_gmail_api_credentials():
    """
    Check if Gmail API credentials are available in environment variables.
    
    Returns:
        dict or None: A dictionary containing the Gmail API credentials if available, None otherwise.
    """
    client_id = os.environ.get('GMAIL_API_CLIENT_ID')
    client_secret = os.environ.get('GMAIL_API_CLIENT_SECRET')
    refresh_token = os.environ.get('GMAIL_API_REFRESH_TOKEN')
    
    if client_id and client_secret and refresh_token:
        logger.info("Gmail API credentials found in environment variables")
        return {
            'client_id': client_id,
            'client_secret': client_secret,
            'refresh_token': refresh_token
        }
    
    logger.info("Gmail API credentials not found in environment variables")
    return None

def run_monitor_mode(db_manager, scheduler, email_monitor=None):
    """
    Run the email monitoring mode.
    
    Args:
        db_manager: The database manager instance.
        scheduler: The scheduler instance.
        email_monitor: An existing email monitor instance, if available.
    
    Returns:
        bool: True if the operation was successful, False otherwise.
    """
    global keep_monitoring
    
    try:
        # Set up signal handler for Ctrl+C
        signal.signal(signal.SIGINT, signal_handler)
        
        # If no email monitor is provided, create one
        if email_monitor is None:
            # Get email credentials
            email_address, password, imap_server = get_email_credentials()
            
            # Get poll interval from environment variable or use default
            poll_interval = int(os.environ.get('EMAIL_POLL_INTERVAL', 60))
            
            # Get whether to mark emails as read from environment variable or use default
            mark_as_read = os.environ.get('MARK_EMAILS_AS_READ', 'false').lower() == 'true'
            
            # Check for Gmail API credentials
            gmail_api_credentials = get_gmail_api_credentials()
            
            # Create an email monitor instance
            from src.email.monitor import EmailMonitor
            email_monitor = EmailMonitor(
                email_address=email_address,
                password=password,
                imap_server=imap_server,
                db_manager=db_manager,
                scheduler=scheduler,
                poll_interval=poll_interval,
                mark_as_read=mark_as_read,
                gmail_api_credentials=gmail_api_credentials
            )
            
            # Log which method we're using
            if gmail_api_credentials:
                logger.info("Using Gmail API for email monitoring")
            else:
                logger.info("Using IMAP for email monitoring")
        
        # Start the email monitor
        email_monitor.start()
        
        print("\nEmail monitoring started.")
        print(f"Monitoring {email_monitor.email_address} for Zoom meeting invitations.")
        print("Press Ctrl+C to stop monitoring.")
        
        # Keep the main thread running until Ctrl+C is pressed
        while keep_monitoring:
            time.sleep(1)
        
        # Stop the email monitor
        email_monitor.stop()
        print("\nEmail monitoring stopped.")
        
        return True
        
    except Exception as e:
        logger.error(f"Error running monitor mode: {str(e)}")
        print(f"\nError: {str(e)}")
        return False

if __name__ == "__main__":
    # This is just for testing the module directly
    from src.database.manager import DatabaseManager
    from src.zoom_bot.scheduler import ZoomBotScheduler
    
    # Load environment variables
    load_dotenv()
    
    # Create a database manager instance
    db_path = os.environ.get('DATABASE_PATH', './data/database.db')
    db_manager = DatabaseManager(db_path)
    
    # Create a scheduler instance
    scheduler = ZoomBotScheduler(db_manager)
    
    # Run the monitor mode
    run_monitor_mode(db_manager, scheduler)
