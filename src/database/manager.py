"""
Database manager for the Zoom Interview Analysis System.

This module handles database operations for storing user information,
meeting details, and analysis results.
"""

import os
import logging
import sqlite3
import json
import time
import threading
import hashlib
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple, Union

logger = logging.getLogger(__name__)

class DatabaseManager:
    """Manages database operations for the Zoom Interview Analysis System."""
    
    _instance = None
    _lock = threading.RLock()
    
    def __new__(cls, config_or_path: Union[object, str]):
        """Implement singleton pattern to ensure only one DatabaseManager instance exists."""
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(DatabaseManager, cls).__new__(cls)
                cls._instance._initialized = False
            return cls._instance
    
    def __init__(self, config_or_path: Union[object, str]):
        """Initialize the database manager.
        
        Args:
            config_or_path: Either an application configuration object or a direct path to the database
        """
        # Skip initialization if already initialized
        if getattr(self, '_initialized', False):
            return
            
        # Handle either a config object or a direct path string
        if isinstance(config_or_path, str):
            self.config = None
            self.db_path = config_or_path
        else:
            self.config = config_or_path
            self.db_path = config_or_path.database_path
        
        # Create database directory if it doesn't exist
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        
        # Initialize connection management
        self._max_retries = 5
        self._retry_delay = 0.1  # seconds
        
        # Initialize the database
        self._initialize_database()
        self._initialized = True
    
    def _get_connection(self):
        """Get a database connection for the current thread.
        
        Returns:
            sqlite3.Connection: A connection to the database
        """
        # Always create a new connection
        connection = sqlite3.connect(self.db_path, timeout=20.0)
        # Enable foreign keys
        connection.execute("PRAGMA foreign_keys = ON")
        return connection
    
    def _close_connection(self, connection):
        """Close the database connection."""
        if connection is not None:
            connection.close()
    
    def _execute_with_retry(self, operation, *args, **kwargs):
        """Execute a database operation with retry logic for handling locks.
        
        Args:
            operation: Function to execute
            *args: Arguments to pass to the function
            **kwargs: Keyword arguments to pass to the function
            
        Returns:
            Result of the operation
            
        Raises:
            Exception: If the operation fails after all retries
        """
        for attempt in range(self._max_retries):
            try:
                return operation(*args, **kwargs)
            except sqlite3.OperationalError as e:
                if "database is locked" in str(e) and attempt < self._max_retries - 1:
                    # Close and reopen the connection
                    # Exponential backoff
                    delay = self._retry_delay * (2 ** attempt)
                    logger.warning(f"Database is locked, retrying in {delay:.2f} seconds (attempt {attempt+1}/{self._max_retries})")
                    time.sleep(delay)
                else:
                    logger.error(f"Database error: {str(e)}")
                    raise
            except Exception as e:
                logger.error(f"Error in database operation: {str(e)}")
                raise
    
    def _initialize_database(self):
        """Initialize the database schema if it doesn't exist."""
        def initialize_schema():
            conn = self._get_connection()
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
                    scheduled_time TEXT,
                    start_time TIMESTAMP,
                    end_time TIMESTAMP,
                    actual_start_time TEXT,
                    actual_end_time TEXT,
                    candidate_name TEXT,
                    position TEXT,
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
            
            # Create analysis_results table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS analysis_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    meeting_id INTEGER NOT NULL,
                    result_type TEXT NOT NULL,
                    result_data TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (meeting_id) REFERENCES meetings (id)
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
            
            conn.commit()
            self._close_connection(conn)
            logger.info("Database initialized successfully")
            
        self._execute_with_retry(initialize_schema)
    
    def _generate_hash_key(self, email: str) -> str:
        """Generate a unique hash key for a user.
        
        Args:
            email: User's email address
            
        Returns:
            A unique hash key
        """
        # Create a hash using the email and a salt
        # This is a simple implementation - in production, use a more secure method
        salt = os.urandom(16).hex()
        hash_input = f"{email}:{salt}"
        hash_key = hashlib.sha256(hash_input.encode()).hexdigest()
        return hash_key
    
    def add_user(self, email: str, name: str = None, company: str = None, 
                 role: str = None, api_key: str = None, hash_key: str = None,
                 onboarded_at: str = None, last_login: str = None) -> int:
        """Add a new user to the database.
        
        Args:
            email: User's email address
            name: User's name (optional)
            company: User's company (optional)
            role: User's role (optional)
            api_key: User's API key (optional)
            hash_key: Custom hash key (optional, one will be generated if not provided)
            onboarded_at: Timestamp when the user was onboarded (optional)
            last_login: Timestamp of the user's last login (optional)
            
        Returns:
            User ID if successful, None otherwise
        """
        def add_user_operation():
            # Generate a hash key if not provided
            user_hash_key = hash_key if hash_key else self._generate_hash_key(email)
            
            conn = self._get_connection()
            cursor = conn.cursor()
            
            try:
                cursor.execute('''
                    INSERT INTO users (email, hash_key, name, company, role, api_key, onboarded_at, last_login)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (email, user_hash_key, name, company, role, api_key, onboarded_at, last_login))
                
                user_id = cursor.lastrowid
                conn.commit()
                self._close_connection(conn)
                logger.info(f"Added user with email {email} and hash key {user_hash_key}")
                return user_id
            except sqlite3.IntegrityError as e:
                # If the hash_key already exists, this will fail
                if "UNIQUE constraint failed: users.hash_key" in str(e):
                    logger.warning(f"User with hash key {user_hash_key} already exists")
                    # Get the existing user ID
                    cursor.execute('SELECT id FROM users WHERE hash_key = ?', (user_hash_key,))
                    row = cursor.fetchone()
                    if row:
                        self._close_connection(conn)
                        return row[0]
                    self._close_connection(conn)
                    return None
                else:
                    logger.error(f"Database error: {str(e)}")
                    self._close_connection(conn)
                    return None
            except Exception as e:
                logger.error(f"Database error: {str(e)}")
                self._close_connection(conn)
                raise
            
        return self._execute_with_retry(add_user_operation)
    
    def get_users_by_email(self, email: str) -> List[Dict]:
        """Get all users with a specific email address.
        
        Args:
            email: User's email address
            
        Returns:
            List of dictionaries containing user information
        """
        def get_users_by_email_operation():
            conn = self._get_connection()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute('SELECT * FROM users WHERE email = ?', (email,))
            rows = cursor.fetchall()
            self._close_connection(conn)
            
            return [dict(row) for row in rows]
            
        return self._execute_with_retry(get_users_by_email_operation)
    
    def get_user_by_hash_key(self, hash_key: str) -> Optional[Dict]:
        """Get user information from the database by hash key.
        
        Args:
            hash_key: User's hash key
            
        Returns:
            Dictionary containing user information or None if not found
        """
        def get_user_operation():
            conn = self._get_connection()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute('SELECT * FROM users WHERE hash_key = ?', (hash_key,))
            row = cursor.fetchone()
            self._close_connection(conn)
            
            if row:
                return dict(row)
            return None
            
        return self._execute_with_retry(get_user_operation)
    
    def get_user(self, user_id: int = None, email: str = None, hash_key: str = None) -> Optional[Dict]:
        """Get user information from the database.
        
        Args:
            user_id: User ID
            email: User's email address (if multiple users have the same email, returns the first one found)
            hash_key: User's hash key (unique identifier)
            
        Returns:
            Dictionary containing user information or None if not found
        """
        def get_user_operation():
            conn = self._get_connection()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            if user_id:
                cursor.execute('SELECT * FROM users WHERE id = ?', (user_id,))
            elif hash_key:
                cursor.execute('SELECT * FROM users WHERE hash_key = ?', (hash_key,))
            elif email:
                cursor.execute('SELECT * FROM users WHERE email = ? LIMIT 1', (email,))
            else:
                logger.error("Either user_id, email, or hash_key must be provided")
                self._close_connection(conn)
                return None
            
            row = cursor.fetchone()
            self._close_connection(conn)
            
            if row:
                return dict(row)
            return None
            
        return self._execute_with_retry(get_user_operation)
    
    def verify_hash_key(self, email: str, hash_key: str) -> bool:
        """Verify if a hash key matches an existing user with the given email.
        
        Args:
            email: User's email address
            hash_key: Hash key to verify
            
        Returns:
            True if the hash key is valid for the email, False otherwise
        """
        def verify_hash_key_operation():
            conn = self._get_connection()
            cursor = conn.cursor()
            
            cursor.execute('SELECT COUNT(*) FROM users WHERE email = ? AND hash_key = ?', 
                          (email, hash_key))
            count = cursor.fetchone()[0]
            self._close_connection(conn)
            
            return count > 0
            
        return self._execute_with_retry(verify_hash_key_operation)
    
    def add_meeting(self, user_hash_key: str, url: str, title: str = None, 
                   scheduled_time: str = None, status: str = 'scheduled',
                   meeting_id: str = None, password: str = None) -> int:
        """Add a new meeting to the database.
        
        Args:
            user_hash_key: User's hash key
            url: Meeting URL
            title: Meeting title (optional)
            scheduled_time: Scheduled time for the meeting (optional)
            status: Meeting status (default: 'scheduled')
            meeting_id: Zoom meeting ID (optional)
            password: Zoom meeting password (optional)
            
        Returns:
            Meeting ID if successful, None otherwise
        """
        def add_meeting_operation():
            conn = self._get_connection()
            cursor = conn.cursor()
            
            # Verify that the hash key exists
            cursor.execute('SELECT COUNT(*) FROM users WHERE hash_key = ?', (user_hash_key,))
            count = cursor.fetchone()[0]
            
            if count == 0:
                logger.error(f"User with hash key {user_hash_key} not found")
                self._close_connection(conn)
                return None
            
            try:
                cursor.execute('''
                    INSERT INTO meetings (user_hash_key, url, title, scheduled_time, status, meeting_id, password)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (user_hash_key, url, title, scheduled_time, status, meeting_id, password))
                
                new_meeting_id = cursor.lastrowid
                conn.commit()
                self._close_connection(conn)
                logger.info(f"Added meeting with ID {new_meeting_id} for user with hash key {user_hash_key}")
                return new_meeting_id
            except Exception as e:
                logger.error(f"Database error: {str(e)}")
                self._close_connection(conn)
                return None
            
        return self._execute_with_retry(add_meeting_operation)
    
    def get_meeting(self, meeting_id: int) -> Optional[Dict]:
        """Get meeting information from the database.
        
        Args:
            meeting_id: Meeting ID
            
        Returns:
            Dictionary containing meeting information or None if not found
        """
        def get_meeting_operation():
            conn = self._get_connection()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute('SELECT * FROM meetings WHERE id = ?', (meeting_id,))
            row = cursor.fetchone()
            self._close_connection(conn)
            
            if row:
                return dict(row)
            return None
            
        return self._execute_with_retry(get_meeting_operation)
    
    def get_user_meetings(self, user_hash_key: str) -> List[Dict]:
        """Get all meetings for a user.
        
        Args:
            user_hash_key: User's hash key
            
        Returns:
            List of dictionaries containing meeting information
        """
        def get_user_meetings_operation():
            conn = self._get_connection()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute('SELECT * FROM meetings WHERE user_hash_key = ? ORDER BY created_at DESC', (user_hash_key,))
            rows = cursor.fetchall()
            self._close_connection(conn)
            
            return [dict(row) for row in rows]
            
        return self._execute_with_retry(get_user_meetings_operation)
    
    def find_meeting_by_url_or_id(self, url: str = None, zoom_meeting_id: str = None) -> Optional[Dict]:
        """Find a meeting by URL or Zoom meeting ID.
        
        Args:
            url: Meeting URL
            zoom_meeting_id: Zoom meeting ID
            
        Returns:
            Dictionary containing meeting information or None if not found
        """
        if not url and not zoom_meeting_id:
            logger.warning("Both URL and Zoom meeting ID are None, cannot find meeting")
            return None
            
        def find_meeting_operation():
            conn = self._get_connection()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            if url and zoom_meeting_id:
                cursor.execute('SELECT * FROM meetings WHERE url = ? OR meeting_id = ?', (url, zoom_meeting_id))
            elif url:
                cursor.execute('SELECT * FROM meetings WHERE url = ?', (url,))
            else:
                cursor.execute('SELECT * FROM meetings WHERE meeting_id = ?', (zoom_meeting_id,))
                
            row = cursor.fetchone()
            self._close_connection(conn)
            
            if row:
                return dict(row)
            return None
            
        return self._execute_with_retry(find_meeting_operation)
    
    def update_meeting(self, meeting_id: int, **kwargs) -> bool:
        """Update meeting information in the database.
        
        Args:
            meeting_id: Meeting ID
            **kwargs: Fields to update
            
        Returns:
            True if successful, False otherwise
        """
        def update_meeting_operation():
            if not kwargs:
                logger.warning("No fields provided for update")
                return False
            
            # Build the update query
            fields = []
            values = []
            
            valid_fields = [
                'url', 'title', 'meeting_id', 'password',
                'scheduled_time', 'start_time', 'end_time',
                'actual_start_time', 'actual_end_time', 
                'candidate_name', 'position', 'status', 'bot_id',
                'recording_path', 'transcript_path', 'analytics_path', 
                'insights_path', 'report_path'
            ]
            
            for key, value in kwargs.items():
                if key in valid_fields:
                    fields.append(f"{key} = ?")
                    values.append(value)
            
            if not fields:
                logger.warning("No valid fields provided for update")
                return False
            
            # Add updated_at timestamp
            fields.append("updated_at = ?")
            values.append(datetime.now().isoformat())
            
            # Add meeting_id to values
            values.append(meeting_id)
            
            conn = self._get_connection()
            cursor = conn.cursor()
            
            cursor.execute(f'''
                UPDATE meetings
                SET {", ".join(fields)}
                WHERE id = ?
            ''', values)
            
            conn.commit()
            self._close_connection(conn)
            
            logger.info(f"Updated meeting with ID {meeting_id}")
            return True
            
        return self._execute_with_retry(update_meeting_operation)
    
    def update_user(self, user_hash_key: str = None, **kwargs) -> bool:
        """Update user information in the database.
        
        Args:
            user_hash_key: User's hash key
            **kwargs: Fields to update
            
        Returns:
            True if successful, False otherwise
        """
        def update_user_operation():
            if not kwargs:
                logger.warning("No fields provided for update")
                return False
            
            if not user_hash_key:
                logger.error("User hash key must be provided")
                return False
            
            # Build the update query
            fields = []
            values = []
            
            for key, value in kwargs.items():
                if key in ['email', 'name', 'company', 'role', 'api_key', 'onboarded_at', 'last_login']:
                    fields.append(f"{key} = ?")
                    values.append(value)
            
            if not fields:
                logger.warning("No valid fields provided for update")
                return False
            
            # Add updated_at timestamp
            fields.append("updated_at = ?")
            values.append(datetime.now().isoformat())
            
            conn = self._get_connection()
            cursor = conn.cursor()
            
            values.append(user_hash_key)
                
            cursor.execute(f'''
                UPDATE users
                SET {", ".join(fields)}
                WHERE hash_key = ?
            ''', values)
            
            conn.commit()
            self._close_connection(conn)
            
            logger.info(f"Updated user with hash key {user_hash_key}")
            return True
            
        return self._execute_with_retry(update_user_operation)
    
    def add_analysis_result(self, meeting_id: int, result_type: str, result_data: Dict) -> int:
        """Add an analysis result to the database.
        
        Args:
            meeting_id: Meeting ID
            result_type: Type of analysis result
            result_data: Analysis result data
            
        Returns:
            Analysis result ID
        """
        def add_analysis_result_operation():
            conn = self._get_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO analysis_results (meeting_id, result_type, result_data)
                VALUES (?, ?, ?)
            ''', (meeting_id, result_type, json.dumps(result_data)))
            
            result_id = cursor.lastrowid
            conn.commit()
            self._close_connection(conn)
            
            logger.info(f"Added new analysis result with ID {result_id} for meeting {meeting_id}")
            return result_id
            
        return self._execute_with_retry(add_analysis_result_operation)
    
    def get_analysis_results(self, meeting_id: int, result_type: str = None) -> List[Dict]:
        """Get analysis results for a meeting.
        
        Args:
            meeting_id: Meeting ID
            result_type: Type of analysis result (optional)
            
        Returns:
            List of dictionaries containing analysis results
        """
        def get_analysis_results_operation():
            conn = self._get_connection()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            if result_type:
                cursor.execute(
                    'SELECT * FROM analysis_results WHERE meeting_id = ? AND result_type = ?',
                    (meeting_id, result_type)
                )
            else:
                cursor.execute(
                    'SELECT * FROM analysis_results WHERE meeting_id = ?',
                    (meeting_id,)
                )
            
            rows = cursor.fetchall()
            self._close_connection(conn)
            
            results = []
            for row in rows:
                result = dict(row)
                # Parse the JSON data
                if result['result_data']:
                    result['result_data'] = json.loads(result['result_data'])
                results.append(result)
            
            return results
            
        return self._execute_with_retry(get_analysis_results_operation)


def test_database_manager():
    """Test the database manager functionality."""
    from types import SimpleNamespace
    import tempfile
    
    # Create a temporary database for testing
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as temp_db:
        temp_db_path = temp_db.name
    
    try:
        # Set up logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        
        # Create a simple config for testing
        config = SimpleNamespace(
            database_path=temp_db_path
        )
        
        # Create the database manager
        db_manager = DatabaseManager(config)
        
        # Test user operations
        print("\nTesting user operations:")
        user_hash_key = db_manager._generate_hash_key("test@example.com")
        user_id = db_manager.add_user(
            email="test@example.com",
            name="Test User",
            company="Test Company",
            role="HR Manager",
            hash_key=user_hash_key,
            onboarded_at=datetime.now().isoformat()
        )
        print(f"Added user with ID: {user_id}")
        
        user = db_manager.get_user_by_hash_key(user_hash_key)
        print(f"Retrieved user: {user}")
        
        # Test meeting operations
        print("\nTesting meeting operations:")
        meeting_id = db_manager.add_meeting(
            user_hash_key=user_hash_key,
            url="https://zoom.us/j/123456789",
            title="Interview with John Doe",
            scheduled_time="2023-04-15T14:30:00",
            status="scheduled",
            meeting_id="123456789",
            password="password123"
        )
        print(f"Added meeting with ID: {meeting_id}")
        
        meeting = db_manager.get_meeting(meeting_id)
        print(f"Retrieved meeting: {meeting}")
        
        db_manager.update_meeting(
            meeting_id,
            status="completed",
            start_time="2023-04-15T14:30:00",
            end_time="2023-04-15T15:15:00",
            actual_start_time="2023-04-15T14:32:00",
            actual_end_time="2023-04-15T15:18:00"
        )
        meeting = db_manager.get_meeting(meeting_id)
        print(f"Updated meeting: {meeting}")
        
        # Test analysis results
        print("\nTesting analysis results:")
        result_id = db_manager.add_analysis_result(
            meeting_id=meeting_id,
            result_type="hume_analysis",
            result_data={
                "summary": {
                    "top_emotions": [("Joy", 0.85), ("Interest", 0.72)]
                },
                "user_response_analysis": {
                    "diction_analysis": {
                        "total_word_count": 500,
                        "unique_word_count": 250,
                        "vocabulary_diversity": 0.5
                    }
                }
            }
        )
        print(f"Added analysis result with ID: {result_id}")
        
        results = db_manager.get_analysis_results(meeting_id)
        print(f"Retrieved analysis results: {results}")
        
        # Test getting user meetings
        user_meetings = db_manager.get_user_meetings(user_hash_key)
        print(f"\nUser meetings: {user_meetings}")
        
        # Test getting users by email
        users = db_manager.get_users_by_email("test@example.com")
        print(f"\nUsers with email test@example.com: {users}")
        
        # Test verifying hash key
        is_valid = db_manager.verify_hash_key("test@example.com", user_hash_key)
        print(f"\nHash key verification: {is_valid}")
        
        # Test updating user
        db_manager.update_user(
            user_hash_key=user_hash_key,
            name="Updated Test User",
            company="Updated Test Company"
        )
        updated_user = db_manager.get_user_by_hash_key(user_hash_key)
        print(f"\nUpdated user: {updated_user}")
        
        # Test finding meeting by URL or ID
        meeting = db_manager.find_meeting_by_url_or_id(url="https://zoom.us/j/123456789")
        print(f"\nMeeting found by URL: {meeting}")
        
        meeting = db_manager.find_meeting_by_url_or_id(zoom_meeting_id="123456789")
        print(f"\nMeeting found by ID: {meeting}")
        
    finally:
        # Clean up the temporary database
        try:
            os.unlink(temp_db_path)
        except:
            pass


if __name__ == "__main__":
    test_database_manager()
