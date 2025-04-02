"""
Command-line interface for manual meeting management.
This module provides a CLI for manually adding and joining meetings.
"""

import os
import sys
import logging
import getpass
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def get_meeting_details():
    """
    Prompt the user for meeting details.
    
    Returns:
        dict: A dictionary containing the meeting details.
    """
    print("\n=== Manual Meeting Entry ===\n")
    
    # Get meeting URL
    meeting_url = input("Enter Zoom meeting URL: ").strip()
    while not meeting_url or "zoom.us" not in meeting_url:
        print("Invalid Zoom meeting URL. It should contain 'zoom.us'.")
        meeting_url = input("Enter Zoom meeting URL: ").strip()
    
    # Get meeting title
    meeting_title = input("Enter meeting title (optional): ").strip()
    
    # Get organizer email
    organizer_email = input("Enter organizer email: ").strip()
    while not organizer_email or "@" not in organizer_email:
        print("Invalid email address.")
        organizer_email = input("Enter organizer email: ").strip()
    
    # Get organizer name
    organizer_name = input("Enter organizer name (optional): ").strip()
    
    # Get organizer company
    organizer_company = input("Enter organizer company (optional): ").strip()
    
    # Get organizer role
    organizer_role = input("Enter organizer role (optional): ").strip()
    
    # Get candidate name
    candidate_name = input("Enter candidate name: ").strip()
    while not candidate_name:
        print("Candidate name is required.")
        candidate_name = input("Enter candidate name: ").strip()
    
    # Get position
    position = input("Enter position being interviewed for: ").strip()
    while not position:
        print("Position is required.")
        position = input("Enter position being interviewed for: ").strip()
    
    # Get scheduled time
    scheduled_time_str = input("Enter scheduled time (YYYY-MM-DD HH:MM, leave blank for now): ").strip()
    if scheduled_time_str:
        try:
            scheduled_time = datetime.strptime(scheduled_time_str, "%Y-%m-%d %H:%M")
        except ValueError:
            print("Invalid date format. Using current time.")
            scheduled_time = datetime.now()
    else:
        scheduled_time = datetime.now()
    
    # Ask if the meeting should be joined immediately
    join_now_str = input("Join meeting immediately? (y/n): ").strip().lower()
    join_now = join_now_str == "y" or join_now_str == "yes"
    
    # Return the meeting details
    return {
        "meeting_url": meeting_url,
        "meeting_title": meeting_title,
        "organizer_email": organizer_email,
        "organizer_name": organizer_name,
        "organizer_company": organizer_company,
        "organizer_role": organizer_role,
        "candidate_name": candidate_name,
        "position": position,
        "scheduled_time": scheduled_time,
        "join_now": join_now
    }

def run_manual_mode(db_manager, scheduler):
    """
    Run the manual meeting management mode.
    
    Args:
        db_manager: The database manager instance.
        scheduler: The scheduler instance.
    
    Returns:
        bool: True if the operation was successful, False otherwise.
    """
    try:
        # Get meeting details from the user
        meeting_details = get_meeting_details()
        
        # Add or get the organizer
        organizer_id = db_manager.add_user(
            email=meeting_details["organizer_email"],
            name=meeting_details["organizer_name"],
            company=meeting_details["organizer_company"],
            role=meeting_details["organizer_role"]
        )
        
        # Add the meeting to the database
        meeting_id = db_manager.add_meeting(
            url=meeting_details["meeting_url"],
            title=meeting_details["meeting_title"] or f"Interview with {meeting_details['candidate_name']}",
            organizer_id=organizer_id,
            scheduled_time=meeting_details["scheduled_time"].isoformat(),
            candidate_name=meeting_details["candidate_name"],
            position=meeting_details["position"],
            status="scheduled"
        )
        
        # Add the organizer as a participant
        db_manager.add_meeting_participant(meeting_id, organizer_id, "interviewer")
        
        logger.info(f"Meeting added with ID: {meeting_id}")
        
        # Join the meeting immediately or schedule it
        if meeting_details["join_now"]:
            logger.info("Joining meeting now...")
            result = scheduler.join_meeting_now(meeting_id)
            if result:
                logger.info("Meeting joined successfully")
                return True
            else:
                logger.error("Failed to join meeting")
                return False
        else:
            logger.info(f"Scheduling meeting for {meeting_details['scheduled_time']}...")
            result = scheduler.schedule_meeting(meeting_id)
            if result:
                logger.info("Meeting scheduled successfully")
                return True
            else:
                logger.error("Failed to schedule meeting")
                return False
        
    except Exception as e:
        logger.error(f"Error in manual mode: {str(e)}")
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
    
    # Run the manual mode
    run_manual_mode(db_manager, scheduler)
