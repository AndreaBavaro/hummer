"""
Command-line interface for viewing and managing meetings.
This module provides a CLI for listing, viewing, and managing meetings.
"""

import os
import sys
import logging
import json
from datetime import datetime
from tabulate import tabulate
from dotenv import load_dotenv

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def format_datetime(dt_str):
    """
    Format a datetime string for display.
    
    Args:
        dt_str (str): The datetime string in ISO format.
    
    Returns:
        str: The formatted datetime string.
    """
    if not dt_str:
        return "N/A"
    
    try:
        dt = datetime.fromisoformat(dt_str)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except:
        return dt_str

def list_meetings(db_manager, status=None, limit=10):
    """
    List meetings in the database.
    
    Args:
        db_manager: The database manager instance.
        status (str, optional): Filter meetings by status.
        limit (int, optional): Maximum number of meetings to list.
    
    Returns:
        bool: True if the operation was successful, False otherwise.
    """
    try:
        # Get meetings from the database
        meetings = db_manager.get_meetings(status=status, limit=limit)
        
        if not meetings:
            print("No meetings found.")
            return True
        
        # Prepare table headers and rows
        headers = ["ID", "Title", "Candidate", "Position", "Scheduled Time", "Status"]
        rows = []
        
        for meeting in meetings:
            rows.append([
                meeting["id"],
                meeting["title"] or "N/A",
                meeting["candidate_name"] or "N/A",
                meeting["position"] or "N/A",
                format_datetime(meeting["scheduled_time"]),
                meeting["status"] or "N/A"
            ])
        
        # Print the table
        print("\n=== Meetings ===\n")
        print(tabulate(rows, headers=headers, tablefmt="grid"))
        print()
        
        return True
        
    except Exception as e:
        logger.error(f"Error listing meetings: {str(e)}")
        return False

def view_meeting(db_manager, meeting_id):
    """
    View details of a specific meeting.
    
    Args:
        db_manager: The database manager instance.
        meeting_id (int): The ID of the meeting to view.
    
    Returns:
        bool: True if the operation was successful, False otherwise.
    """
    try:
        # Get the meeting from the database
        meeting = db_manager.get_meeting(meeting_id)
        
        if not meeting:
            print(f"Meeting with ID {meeting_id} not found.")
            return False
        
        # Get the organizer
        organizer = db_manager.get_user(meeting["organizer_id"]) if meeting["organizer_id"] else None
        
        # Get meeting participants
        participants = db_manager.get_meeting_participants(meeting_id)
        
        # Get analysis results
        analysis_results = db_manager.get_analysis_results(meeting_id)
        
        # Print meeting details
        print("\n=== Meeting Details ===\n")
        print(f"ID: {meeting['id']}")
        print(f"Title: {meeting['title'] or 'N/A'}")
        print(f"URL: {meeting['url'] or 'N/A'}")
        print(f"Candidate: {meeting['candidate_name'] or 'N/A'}")
        print(f"Position: {meeting['position'] or 'N/A'}")
        print(f"Scheduled Time: {format_datetime(meeting['scheduled_time'])}")
        print(f"Start Time: {format_datetime(meeting['start_time'])}")
        print(f"End Time: {format_datetime(meeting['end_time'])}")
        print(f"Status: {meeting['status'] or 'N/A'}")
        print(f"Bot ID: {meeting['bot_id'] or 'N/A'}")
        
        # Print organizer details
        print("\n=== Organizer ===\n")
        if organizer:
            print(f"Name: {organizer['name'] or 'N/A'}")
            print(f"Email: {organizer['email'] or 'N/A'}")
            print(f"Company: {organizer['company'] or 'N/A'}")
            print(f"Role: {organizer['role'] or 'N/A'}")
        else:
            print("No organizer information available.")
        
        # Print participants
        print("\n=== Participants ===\n")
        if participants:
            headers = ["Name", "Email", "Company", "Role", "Participant Role"]
            rows = []
            
            for participant in participants:
                rows.append([
                    participant["name"] or "N/A",
                    participant["email"] or "N/A",
                    participant["company"] or "N/A",
                    participant["role"] or "N/A",
                    participant["participant_role"] or "N/A"
                ])
            
            print(tabulate(rows, headers=headers, tablefmt="grid"))
        else:
            print("No participants found.")
        
        # Print file paths
        print("\n=== Files ===\n")
        print(f"Recording: {meeting['recording_path'] or 'N/A'}")
        print(f"Transcript: {meeting['transcript_path'] or 'N/A'}")
        print(f"Analytics: {meeting['analytics_path'] or 'N/A'}")
        print(f"Insights: {meeting['insights_path'] or 'N/A'}")
        print(f"Report: {meeting['report_path'] or 'N/A'}")
        
        # Print analysis results
        print("\n=== Analysis Results ===\n")
        if analysis_results:
            for result in analysis_results:
                print(f"Type: {result['result_type'] or 'N/A'}")
                print(f"Created At: {format_datetime(result['created_at'])}")
                
                # Try to pretty-print the JSON data
                try:
                    data = json.loads(result["result_data"])
                    print("Data:")
                    print(json.dumps(data, indent=2))
                except:
                    print(f"Data: {result['result_data'] or 'N/A'}")
                
                print()
        else:
            print("No analysis results found.")
        
        return True
        
    except Exception as e:
        logger.error(f"Error viewing meeting: {str(e)}")
        return False

def update_meeting_status(db_manager, meeting_id, status):
    """
    Update the status of a meeting.
    
    Args:
        db_manager: The database manager instance.
        meeting_id (int): The ID of the meeting to update.
        status (str): The new status of the meeting.
    
    Returns:
        bool: True if the operation was successful, False otherwise.
    """
    try:
        # Get the meeting from the database
        meeting = db_manager.get_meeting(meeting_id)
        
        if not meeting:
            print(f"Meeting with ID {meeting_id} not found.")
            return False
        
        # Update the meeting status
        db_manager.update_meeting(meeting_id, status=status)
        
        print(f"Meeting status updated to '{status}'.")
        return True
        
    except Exception as e:
        logger.error(f"Error updating meeting status: {str(e)}")
        return False

def delete_meeting(db_manager, meeting_id):
    """
    Delete a meeting from the database.
    
    Args:
        db_manager: The database manager instance.
        meeting_id (int): The ID of the meeting to delete.
    
    Returns:
        bool: True if the operation was successful, False otherwise.
    """
    try:
        # Get the meeting from the database
        meeting = db_manager.get_meeting(meeting_id)
        
        if not meeting:
            print(f"Meeting with ID {meeting_id} not found.")
            return False
        
        # Confirm deletion
        confirm = input(f"Are you sure you want to delete meeting '{meeting['title']}' (ID: {meeting_id})? (y/n): ").strip().lower()
        
        if confirm != "y" and confirm != "yes":
            print("Deletion cancelled.")
            return False
        
        # Delete the meeting
        db_manager.delete_meeting(meeting_id)
        
        print(f"Meeting with ID {meeting_id} deleted.")
        return True
        
    except Exception as e:
        logger.error(f"Error deleting meeting: {str(e)}")
        return False

def run_meeting_manager(db_manager):
    """
    Run the meeting manager CLI.
    
    Args:
        db_manager: The database manager instance.
    
    Returns:
        bool: True if the operation was successful, False otherwise.
    """
    try:
        while True:
            print("\n=== Meeting Manager ===\n")
            print("1. List all meetings")
            print("2. List scheduled meetings")
            print("3. List completed meetings")
            print("4. View meeting details")
            print("5. Update meeting status")
            print("6. Delete meeting")
            print("0. Exit")
            
            choice = input("\nEnter your choice: ").strip()
            
            if choice == "0":
                break
            
            elif choice == "1":
                list_meetings(db_manager)
            
            elif choice == "2":
                list_meetings(db_manager, status="scheduled")
            
            elif choice == "3":
                list_meetings(db_manager, status="completed")
            
            elif choice == "4":
                meeting_id = input("Enter meeting ID: ").strip()
                try:
                    meeting_id = int(meeting_id)
                    view_meeting(db_manager, meeting_id)
                except ValueError:
                    print("Invalid meeting ID. Please enter a number.")
            
            elif choice == "5":
                meeting_id = input("Enter meeting ID: ").strip()
                try:
                    meeting_id = int(meeting_id)
                    
                    print("\nAvailable statuses:")
                    print("1. scheduled")
                    print("2. joining")
                    print("3. recording")
                    print("4. completed")
                    print("5. failed")
                    
                    status_choice = input("Enter status number: ").strip()
                    
                    status_map = {
                        "1": "scheduled",
                        "2": "joining",
                        "3": "recording",
                        "4": "completed",
                        "5": "failed"
                    }
                    
                    if status_choice in status_map:
                        update_meeting_status(db_manager, meeting_id, status_map[status_choice])
                    else:
                        print("Invalid status choice.")
                
                except ValueError:
                    print("Invalid meeting ID. Please enter a number.")
            
            elif choice == "6":
                meeting_id = input("Enter meeting ID: ").strip()
                try:
                    meeting_id = int(meeting_id)
                    delete_meeting(db_manager, meeting_id)
                except ValueError:
                    print("Invalid meeting ID. Please enter a number.")
            
            else:
                print("Invalid choice. Please try again.")
        
        return True
        
    except Exception as e:
        logger.error(f"Error in meeting manager: {str(e)}")
        return False

if __name__ == "__main__":
    # This is just for testing the module directly
    from src.database.manager import DatabaseManager
    
    # Load environment variables
    load_dotenv()
    
    # Create a database manager instance
    db_path = os.environ.get('DATABASE_PATH', './data/database.db')
    db_manager = DatabaseManager(db_path)
    
    # Run the meeting manager
    run_meeting_manager(db_manager)
