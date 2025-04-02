"""
Database initialization script for the Zoom Interview Analysis System.
This script initializes the database with the schema and optional test data.
"""

import os
import argparse
import logging
from pathlib import Path
from dotenv import load_dotenv

from schema import create_database_schema
from manager import DatabaseManager

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def initialize_database(db_path=None, add_test_data=False):
    """
    Initialize the database with the schema and optional test data.
    
    Args:
        db_path (str, optional): Path to the SQLite database file.
            If not provided, it will use the DATABASE_PATH from environment variables.
        add_test_data (bool, optional): Whether to add test data to the database.
            Defaults to False.
    
    Returns:
        bool: True if the database was initialized successfully, False otherwise.
    """
    # Load environment variables if not already loaded
    if 'DATABASE_PATH' not in os.environ:
        load_dotenv()
    
    # Get database path from environment variable if not provided
    if db_path is None:
        db_path = os.environ.get('DATABASE_PATH', './data/database.db')
    
    # Create the database schema
    if not create_database_schema(db_path):
        logger.error("Failed to create database schema")
        return False
    
    # Add test data if requested
    if add_test_data:
        try:
            # Create a database manager instance
            db_manager = DatabaseManager(db_path)
            
            # Add test users
            user1_id = db_manager.add_user(
                email="interviewer@example.com",
                name="John Smith",
                company="Example Corp",
                role="HR Manager"
            )
            
            user2_id = db_manager.add_user(
                email="candidate@example.com",
                name="Jane Doe",
                company="Job Seeker",
                role="Software Engineer"
            )
            
            # Add a test meeting
            meeting_id = db_manager.add_meeting(
                url="https://zoom.us/j/1234567890?pwd=abcdef",
                title="Interview with Jane Doe",
                organizer_id=user1_id,
                scheduled_time="2023-12-31 10:00:00",
                candidate_name="Jane Doe",
                position="Software Engineer",
                status="scheduled"
            )
            
            # Add meeting participants
            db_manager.add_meeting_participant(meeting_id, user1_id, "interviewer")
            db_manager.add_meeting_participant(meeting_id, user2_id, "candidate")
            
            logger.info("Test data added successfully")
            return True
            
        except Exception as e:
            logger.error(f"Error adding test data: {str(e)}")
            return False
    
    return True

if __name__ == "__main__":
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Initialize the database for the Zoom Interview Analysis System")
    parser.add_argument("--db-path", help="Path to the SQLite database file")
    parser.add_argument("--test-data", action="store_true", help="Add test data to the database")
    args = parser.parse_args()
    
    # Initialize the database
    if initialize_database(args.db_path, args.test_data):
        logger.info("Database initialized successfully")
    else:
        logger.error("Failed to initialize database")
