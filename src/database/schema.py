"""
Database schema initialization script for the Zoom Interview Analysis System.
This script creates the necessary tables in the SQLite database.
"""

import os
import sqlite3
import logging
from pathlib import Path
from dotenv import load_dotenv

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def create_database_schema(db_path=None):
    """
    Create the database schema for the Zoom Interview Analysis System.
    
    Args:
        db_path (str, optional): Path to the database file. Defaults to None.
        
    Returns:
        bool: True if successful, False otherwise.
    """
    try:
        # Load environment variables
        load_dotenv()
        
        # If no db_path is provided, use the one from environment variables
        if db_path is None:
            db_path = os.environ.get('DATABASE_PATH', './data/database.db')
        
        # Create directory if it doesn't exist
        db_dir = os.path.dirname(db_path)
        if db_dir:
            Path(db_dir).mkdir(parents=True, exist_ok=True)
        
        # Connect to database
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Create users table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL,
            hash_key TEXT UNIQUE NOT NULL,
            name TEXT,
            company TEXT,
            role TEXT,
            api_key TEXT,
            onboarded_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_login TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        
        # Create meetings table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS meetings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_hash_key TEXT NOT NULL,
            url TEXT NOT NULL,
            title TEXT,
            meeting_id TEXT,
            password TEXT,
            scheduled_time TIMESTAMP,
            start_time TIMESTAMP,
            end_time TIMESTAMP,
            actual_start_time TIMESTAMP,
            actual_end_time TIMESTAMP,
            status TEXT,
            bot_id TEXT,
            recording_path TEXT,
            transcript_path TEXT,
            analytics_path TEXT,
            insights_path TEXT,
            report_path TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_hash_key) REFERENCES users (hash_key)
        )
        ''')
        
        # Create meeting_participants table (many-to-many relationship)
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS meeting_participants (
            meeting_id INTEGER,
            user_hash_key TEXT,
            role TEXT,
            PRIMARY KEY (meeting_id, user_hash_key),
            FOREIGN KEY (meeting_id) REFERENCES meetings (id),
            FOREIGN KEY (user_hash_key) REFERENCES users (hash_key)
        )
        ''')
        
        # Create analysis_results table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS analysis_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            meeting_id INTEGER,
            result_type TEXT,
            result_data TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (meeting_id) REFERENCES meetings (id)
        )
        ''')
        
        # Create triggers to update the updated_at timestamp
        cursor.execute('''
        CREATE TRIGGER IF NOT EXISTS update_users_timestamp
        AFTER UPDATE ON users
        FOR EACH ROW
        BEGIN
            UPDATE users SET updated_at = CURRENT_TIMESTAMP WHERE id = OLD.id;
        END;
        ''')
        
        cursor.execute('''
        CREATE TRIGGER IF NOT EXISTS update_meetings_timestamp
        AFTER UPDATE ON meetings
        FOR EACH ROW
        BEGIN
            UPDATE meetings SET updated_at = CURRENT_TIMESTAMP WHERE id = OLD.id;
        END;
        ''')
        
        # Commit changes
        conn.commit()
        logger.info(f"Database schema created successfully at {db_path}")
        
        # Close connection
        conn.close()
        return True
        
    except Exception as e:
        logger.error(f"Error creating database schema: {str(e)}")
        return False

if __name__ == "__main__":
    # This allows the script to be run directly to initialize the database
    create_database_schema()
