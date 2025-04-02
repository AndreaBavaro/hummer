"""
Scheduler for the Zoom Interview Analysis System.

This module handles scheduling of Zoom meetings for the bot to join.
"""

import os
import logging
import threading
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import schedule

from src.database.manager import DatabaseManager
from src.zoom_bot.controller import ZoomBotController
from src.zoom_bot.meeting_queue import MeetingQueue

logger = logging.getLogger(__name__)

class ZoomBotScheduler:
    """Schedules and manages Zoom meetings for the bot to join."""
    
    def __init__(self, db_manager):
        """Initialize the Zoom bot scheduler.
        
        Args:
            db_manager: DatabaseManager instance
        """
        self.db_manager = db_manager
        self.running = False
        self.thread = None
        self.scheduled_jobs = {}  # Dictionary to track scheduled jobs
        
        # Initialize meeting queue for future meetings
        self.meeting_queue = MeetingQueue(self.join_meeting_now)
        
        # Set up a schedule to check for urgent meetings every minute
        schedule.every(1).minutes.do(self._check_urgent_meetings)
    
    def start(self):
        """Start the scheduler."""
        if self.thread and self.thread.is_alive():
            logger.warning("Scheduler is already running")
            return
        
        self.running = True
        self.thread = threading.Thread(target=self._scheduler_loop, daemon=True)
        self.thread.start()
        logger.info("Started Zoom bot scheduler")
        
        # Start the meeting queue
        self.meeting_queue.start()
        
        # Load any previously scheduled meetings from the database
        self._load_scheduled_meetings()
    
    def stop(self):
        """Stop the scheduler."""
        self.running = False
        if self.thread:
            self.thread.join(timeout=10)
            logger.info("Stopped Zoom bot scheduler")
        
        # Stop the meeting queue
        self.meeting_queue.stop()
    
    def _scheduler_loop(self):
        """Main scheduler loop."""
        while self.running:
            schedule.run_pending()
            time.sleep(1)
    
    def _check_urgent_meetings(self):
        """Check for meetings that have become urgent (within 15 minutes)."""
        try:
            logger.debug("Checking for urgent meetings")
            self.meeting_queue.check_for_urgent_meetings()
        except Exception as e:
            logger.error(f"Error checking for urgent meetings: {str(e)}")
    
    def _load_scheduled_meetings(self):
        """Load scheduled meetings from the database."""
        try:
            # Get all meetings with status 'scheduled'
            conn = self.db_manager._get_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT id, url, scheduled_time FROM meetings
                WHERE status = 'scheduled'
            ''')
            
            scheduled_meetings = cursor.fetchall()
            conn.close()
            
            for meeting_id, url, scheduled_time in scheduled_meetings:
                if scheduled_time:
                    try:
                        # Parse the scheduled time
                        meeting_dt = datetime.fromisoformat(scheduled_time)
                        
                        # If the meeting is in the future, schedule it
                        if meeting_dt > datetime.now():
                            self.schedule_meeting(meeting_id, url, meeting_dt)
                            logger.info(f"Loaded scheduled meeting {meeting_id} at {meeting_dt}")
                    except ValueError as e:
                        logger.error(f"Error parsing scheduled time for meeting {meeting_id}: {str(e)}")
                    except Exception as e:
                        logger.error(f"Error loading scheduled meeting {meeting_id}: {str(e)}")
            
        except Exception as e:
            logger.error(f"Error loading scheduled meetings: {str(e)}")
    
    def schedule_meeting(self, meeting_id: int, meeting_url: str, meeting_time: datetime) -> bool:
        """Schedule a Zoom meeting for the bot to join.
        
        Args:
            meeting_id: Meeting ID in the database
            meeting_url: Zoom meeting URL
            meeting_time: Scheduled meeting time
            
        Returns:
            True if scheduled successfully, False otherwise
        """
        try:
            print(f"\n[ZoomBotScheduler] Scheduling meeting {meeting_id}")
            print(f"[ZoomBotScheduler] Meeting URL: {meeting_url}")
            print(f"[ZoomBotScheduler] Scheduled time: {meeting_time}")
            
            # Calculate the time difference from now
            now = datetime.now()
            time_diff = meeting_time - now
            
            # For immediate meetings, use join_meeting_now
            if time_diff.total_seconds() <= 0:
                logger.warning(f"Meeting {meeting_id} is in the past, joining immediately")
                print(f"[ZoomBotScheduler] Meeting {meeting_id} is in the past, joining immediately")
                return self.join_meeting_now(meeting_id, meeting_url)
            
            # For future meetings, use the meeting queue
            success = self.meeting_queue.schedule_meeting(meeting_id, meeting_url, meeting_time)
            
            if success:
                # Update the meeting status in the database
                self.db_manager.update_meeting(
                    meeting_id,
                    status="scheduled"
                )
                
                # Log whether this is an urgent meeting (within 15 minutes)
                is_urgent = time_diff <= timedelta(minutes=15)
                if is_urgent:
                    logger.info(f"Scheduled URGENT meeting {meeting_id} at {meeting_time} (within 15 minutes)")
                    print(f"[ZoomBotScheduler] Scheduled URGENT meeting {meeting_id} at {meeting_time} (within 15 minutes)")
                else:
                    logger.info(f"Scheduled meeting {meeting_id} at {meeting_time}")
                    print(f"[ZoomBotScheduler] Scheduled meeting {meeting_id} at {meeting_time}")
                
                return True
            else:
                logger.error(f"Failed to schedule meeting {meeting_id}")
                print(f"[ZoomBotScheduler] Failed to schedule meeting {meeting_id}")
                return False
            
        except Exception as e:
            logger.error(f"Error scheduling meeting {meeting_id}: {str(e)}")
            print(f"[ZoomBotScheduler] Error scheduling meeting {meeting_id}: {str(e)}")
            return False
    
    def join_meeting_now(self, meeting_id: int, meeting_url: str) -> bool:
        """Join a Zoom meeting immediately.
        
        Args:
            meeting_id: Meeting ID in the database
            meeting_url: Zoom meeting URL
            
        Returns:
            True if joined successfully, False otherwise
        """
        try:
            logger.info(f"Joining meeting {meeting_id} (joining 1 minute after scheduled start time)")
            logger.info(f"Full meeting URL being used: {meeting_url}")
            print(f"\n[ZoomBotScheduler] Joining meeting {meeting_id} (joining 1 minute after scheduled start time)")
            print(f"[ZoomBotScheduler] Full meeting URL being used: {meeting_url}")
            
            # Update the meeting status in the database
            self.db_manager.update_meeting(
                meeting_id,
                status="joining",
                actual_start_time=datetime.now().isoformat()
            )
            
            # Create a bot controller and join the meeting in a separate thread
            thread = threading.Thread(
                target=self._join_meeting_thread,
                args=(meeting_id, meeting_url),
                daemon=True
            )
            thread.start()
            
            return True
            
        except Exception as e:
            logger.error(f"Error joining meeting {meeting_id}: {str(e)}")
            print(f"[ZoomBotScheduler] Error joining meeting {meeting_id}: {str(e)}")
            return False
    
    def _join_meeting_thread(self, meeting_id: int, meeting_url: str):
        """Join a meeting in a separate thread.
        
        Args:
            meeting_id: Meeting ID in the database
            meeting_url: Zoom meeting URL
        """
        try:
            # Create a config object with all required fields
            from types import SimpleNamespace
            
            # Get environment variables with fallbacks
            hume_api_key = os.environ.get('HUME_API_KEY', '')
            anthropic_api_key = os.environ.get('ANTHROPIC_API_KEY', '')
            attendee_api_key = os.environ.get('ATTENDEE_API_KEY', 'test_api_key')
            
            # Create the configuration object with attributes (not just values)
            config = SimpleNamespace()
            config.database_path = getattr(self.db_manager, 'database_path', './data/database.db')
            config.attendee_api_key = attendee_api_key
            config.data_dir = './data'
            config.hume_api_key = hume_api_key
            config.anthropic_api_key = anthropic_api_key
            config.local_storage_path = './data'
            config.temp_storage_path = './temp'
            
            controller = ZoomBotController(config)
            # Pass the database meeting ID to the controller
            result = controller.join_meeting(meeting_url, db_meeting_id=meeting_id)
            
            if result:
                logger.info(f"Successfully joined and processed meeting {meeting_id}")
                
                # Update the meeting in the database with the results
                self.db_manager.update_meeting(
                    meeting_id,
                    status="completed",
                    actual_end_time=datetime.now().isoformat(),
                    bot_id=result.get("bot_id"),
                    recording_path=result.get("recording_path"),
                    transcript_path=result.get("transcript_path"),
                    analytics_path=result.get("analytics_path"),
                    insights_path=result.get("insights_path"),
                    report_path=result.get("report_path")
                )
            else:
                logger.error(f"Failed to join or process meeting {meeting_id}")
                
                # Update the meeting status in the database
                self.db_manager.update_meeting(
                    meeting_id,
                    status="failed"
                )
            
        except Exception as e:
            logger.error(f"Error in join meeting thread for meeting {meeting_id}: {str(e)}")
            
            # Update the meeting status in the database
            self.db_manager.update_meeting(
                meeting_id,
                status="failed"
            )


def test_scheduler():
    """Test the scheduler functionality."""
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
            database_path=temp_db_path,
            attendee_api_key="test_api_key",
            data_dir="./data",
            hume_api_key=None,
            anthropic_api_key=None
        )
        
        # Create the database manager and add a test meeting
        db_manager = DatabaseManager(config)
        
        # Add a test user
        user_id = db_manager.add_user(
            email="test@example.com",
            name="Test User"
        )
        
        # Get the user's hash key
        conn = db_manager._get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT hash_key FROM users WHERE id = ?', (user_id,))
        user_hash_key = cursor.fetchone()[0]
        conn.close()
        
        # Add a test meeting scheduled for 1 minute from now
        meeting_time = datetime.now() + timedelta(minutes=1)
        meeting_id = db_manager.add_meeting(
            url="https://zoom.us/j/123456789",
            title="Test Meeting",
            scheduled_time=meeting_time.isoformat(),
            user_hash_key=user_hash_key
        )
        
        print(f"Created test meeting with ID {meeting_id} scheduled for {meeting_time}")
        
        # Create and start the scheduler
        scheduler = ZoomBotScheduler(db_manager)
        scheduler.start()
        
        # Schedule the test meeting
        scheduler.schedule_meeting(meeting_id, "https://zoom.us/j/123456789", meeting_time)
        
        print("Scheduler is running. Press Ctrl+C to stop.")
        
        # Keep the main thread running
        while True:
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("Stopping scheduler...")
        
    finally:
        # Clean up the temporary database
        try:
            os.unlink(temp_db_path)
        except:
            pass


if __name__ == "__main__":
    test_scheduler()
