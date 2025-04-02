"""
Zoom Bot Controller for automating Zoom meeting attendance and recording.

This module integrates with the Attendee API (https://app.attendee.dev/api/v1/)
to automatically join scheduled Zoom meetings, capture recordings, and transcriptions.
"""

import os
import logging
import tempfile
import time
import requests
import json
import asyncio
import re
from datetime import datetime
from typing import Union, Dict, Optional, Any
from dotenv import load_dotenv

# Import analytics processor for Hume AI integration
try:
    from src.analytics.processor import AnalyticsProcessor
except ImportError:
    AnalyticsProcessor = None
    
from src.utils.transcript_formatter import format_transcript

logger = logging.getLogger(__name__)

class ZoomBotController:
    """Controller for the Attendee API."""
    
    def __init__(self, config_or_api_key: Union[object, str, Dict[str, Any]]):
        """Initialize the Zoom bot controller.
        
        Args:
            config_or_api_key: Either an application configuration object, API key string,
                              or a dictionary with configuration values
        """
        # Load environment variables if not already loaded
        load_dotenv()
        
        # Handle different types of configuration
        if isinstance(config_or_api_key, str):
            # Direct API key
            self.config = None
            self.api_key = config_or_api_key
            self.temp_dir = tempfile.mkdtemp(dir=os.environ.get('TEMP_STORAGE_PATH', './temp'))
            self.hume_api_key = os.environ.get('HUME_API_KEY')
            self.anthropic_api_key = os.environ.get('ANTHROPIC_API_KEY', '')
        elif isinstance(config_or_api_key, dict):
            # Dictionary of config values
            self.config = config_or_api_key
            self.api_key = config_or_api_key.get('attendee_api_key') or os.environ.get('ATTENDEE_API_KEY')
            self.temp_dir = tempfile.mkdtemp(dir=config_or_api_key.get('temp_storage_path', './temp'))
            self.hume_api_key = config_or_api_key.get('hume_api_key') or os.environ.get('HUME_API_KEY')
            self.anthropic_api_key = config_or_api_key.get('anthropic_api_key') or os.environ.get('ANTHROPIC_API_KEY', '')
        else:
            # Config object
            self.config = config_or_api_key
            self.api_key = getattr(config_or_api_key, 'attendee_api_key', None) or os.environ.get('ATTENDEE_API_KEY')
            self.temp_dir = tempfile.mkdtemp(dir=getattr(config_or_api_key, 'temp_storage_path', './temp'))
            self.hume_api_key = getattr(config_or_api_key, 'hume_api_key', None) or os.environ.get('HUME_API_KEY')
            self.anthropic_api_key = getattr(config_or_api_key, 'anthropic_api_key', None) or os.environ.get('ANTHROPIC_API_KEY', '')
        
        # Validate required credentials
        if not self.api_key:
            raise ValueError("Attendee API key is required")
        
        # Base URL for Attendee API
        self.base_url = "https://app.attendee.dev/api/v1"
        
        # Initialize Analytics Processor if Hume API key is available
        self.analytics_processor = None
        if self.hume_api_key and AnalyticsProcessor:
            try:
                # Create a config object for the AnalyticsProcessor
                from types import SimpleNamespace
                analytics_config = SimpleNamespace()
                analytics_config.hume_api_key = self.hume_api_key
                analytics_config.anthropic_api_key = self.anthropic_api_key
                
                # Pass the config object instead of just the API key
                self.analytics_processor = AnalyticsProcessor(analytics_config)
                logger.info("Initialized Hume AI analytics processor")
            except ImportError as e:
                logger.warning(f"Could not initialize Hume AI analytics processor: {e}")
                logger.warning("Hume AI analysis will be skipped")
        else:
            logger.warning("Hume API key not provided, analytics processing will be skipped")
        
        logger.info(f"Initialized ZoomBotController with temp directory: {self.temp_dir}")
        logger.info("Note: Zoom OAuth and Deepgram credentials should be configured on the Attendee dashboard")
    
    def join_meeting(self, meeting_url, meeting_id=None, db_meeting_id=None):
        """Join a Zoom meeting using the Attendee API.
        
        Args:
            meeting_url: The Zoom meeting URL
            meeting_id: The Zoom meeting ID (optional, can be extracted from URL)
            db_meeting_id: The database meeting ID (optional, used to get user hash key)
            
        Returns:
            dict: Results of the meeting including paths to recordings and analysis
        """
        logger.info(f"Join meeting called for URL: {meeting_url}, ID: {meeting_id}, DB Meeting ID: {db_meeting_id}")
        print(f"\n[ZoomBotController] Join meeting called with URL: {meeting_url}")
        
        # Extract meeting ID from URL if not provided
        if not meeting_id:
            # Try to extract from URL (e.g., https://zoom.us/j/12345678)
            match = re.search(r'/j/(\d+)', meeting_url)
            if match:
                meeting_id = match.group(1)
                logger.info(f"Extracted meeting ID from URL: {meeting_id}")
                print(f"[ZoomBotController] Extracted meeting ID from URL: {meeting_id}")
            else:
                logger.error("Could not extract meeting ID from URL")
                print(f"[ZoomBotController] ERROR: Could not extract meeting ID from URL")
                return None
        
        # Call the existing join_and_record_meeting method with the meeting URL
        print(f"[ZoomBotController] Calling join_and_record_meeting with URL: {meeting_url}")
        recording_path, transcript_path, analytics_path, insights_path = self.join_and_record_meeting(meeting_id, meeting_url=meeting_url, db_meeting_id=db_meeting_id)
        
        # Return results as a dictionary
        return {
            "meeting_id": meeting_id,
            "recording_path": recording_path,
            "transcript_path": transcript_path,
            "analytics_path": analytics_path,
            "insights_path": insights_path,
            "bot_id": self.bot_id if hasattr(self, 'bot_id') else None,
            "report_path": getattr(self, 'report_path', None)
        }
        
    def join_and_record_meeting(self, meeting_id, password=None, meeting_url=None, db_meeting_id=None):
        """Join a Zoom meeting and record it using the Attendee API.
        
        Args:
            meeting_id: The Zoom meeting ID
            password: The Zoom meeting password (if required)
            meeting_url: The full Zoom meeting URL (optional)
            db_meeting_id: The database meeting ID (optional, used to get user hash key)
            
        Returns:
            tuple: (recording_path, transcript_path, hume_analysis_path, insights_path)
        """
        logger.info(f"Joining Zoom meeting {meeting_id}")
        print(f"\n[ZoomBotController] Joining Zoom meeting {meeting_id}")
        
        # Create timestamp for file naming
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Prepare API request headers according to documentation
        headers = {
            "Authorization": f"Token {self.api_key}",
            "Content-Type": "application/json"
        }
        
        # IMPORTANT: Always use the original meeting URL if provided
        # Only construct a URL if one wasn't provided (fallback only)
        if not meeting_url:
            logger.warning(f"No meeting URL provided for meeting {meeting_id}, constructing a basic URL")
            print(f"[ZoomBotController] WARNING: No meeting URL provided for meeting {meeting_id}, constructing a basic URL")
            meeting_url = f"https://zoom.us/j/{meeting_id}"
            if password:
                meeting_url += f"?pwd={password}"
            print(f"[ZoomBotController] Constructed URL: {meeting_url}")
        else:
            logger.info(f"Using original meeting URL: {meeting_url}")
            print(f"[ZoomBotController] Using original meeting URL: {meeting_url}")
        
        session_data = {
            "meeting_url": meeting_url,
            "bot_name": "Zoom Interview Bot"
        }
        
        logger.info(f"Creating Attendee bot for meeting URL: {meeting_url}")
        print(f"[ZoomBotController] Creating Attendee bot for meeting URL: {meeting_url}")
        print(f"[ZoomBotController] Session data being sent to API: {session_data}")
        
        try:
            # Create bot
            response = requests.post(
                f"{self.base_url}/bots",
                headers=headers,
                json=session_data
            )
            response.raise_for_status()
            
            bot_data = response.json()
            bot_id = bot_data["id"]
            
            logger.info(f"Created Attendee bot: {bot_id}")
            logger.info(f"Initial state: {bot_data['state']}, Transcription state: {bot_data.get('transcription_state', 'unknown')}")
            
            # Poll for bot status until meeting ends and transcription is complete
            recording_available = False
            transcript_available = False
            
            # For testing purposes, only poll for 120 seconds after joined and recording
            poll_interval_seconds = 30  # Poll every 30 seconds
            max_poll_time = 120  # Only poll for 120 seconds total
            poll_count = 0
            max_polls = max_poll_time // poll_interval_seconds
            recording_started = False
            
            logger.info(f"Polling bot status every {poll_interval_seconds} seconds for up to {max_poll_time} seconds after recording starts")
            
            while True:
                status_response = requests.get(
                    f"{self.base_url}/bots/{bot_id}",
                    headers=headers
                )
                status_response.raise_for_status()
                
                status = status_response.json()
                logger.info(f"Bot status: {status['state']}, Transcription: {status.get('transcription_state', 'unknown')}, Recording: {status.get('recording_state', 'unknown')}")
                
                # Check if the bot has joined and is recording
                if status["state"] == "joined_recording" and not recording_started:
                    logger.info("Bot has joined the meeting and is now recording")
                    recording_started = True
                    poll_count = 0  # Reset poll count when recording starts
                
                # Check if meeting has ended
                if status["state"] == "ended":
                    logger.info("Meeting has ended")
                    
                    # Check if recording is complete
                    if status.get("recording_state") == "complete":
                        logger.info("Recording is complete")
                        recording_available = True
                    
                    # Check if transcription is complete
                    if status.get("transcription_state") == "complete":
                        logger.info("Transcription is complete")
                        transcript_available = True
                    
                    # If both recording and transcription are complete, break the loop
                    if recording_available and transcript_available:
                        logger.info("Both recording and transcription are complete")
                        break
                    
                    # If recording is complete but transcription failed, we can still proceed
                    if recording_available and status.get("transcription_state") == "failed":
                        logger.warning("Transcription failed, but recording is available")
                        break
                
                # Log events if available
                events = status.get('events', [])
                if events:
                    recent_events = events[-3:] if len(events) > 3 else events
                    logger.info("Recent events:")
                    for event in recent_events:
                        event_type = event.get('type')
                        created_at = event.get('created_at')
                        logger.info(f"  - {event_type} at {created_at}")
                
                # Check if we've exceeded the max poll time
                if poll_count >= max_polls:
                    logger.info("Max poll time exceeded, stopping polling")
                    break
                
                # Wait before polling again (30 seconds)
                logger.info(f"Waiting {poll_interval_seconds} seconds before polling again")
                time.sleep(poll_interval_seconds)
                
                # Only increment poll count if recording has started
                if recording_started:
                    poll_count += 1
                    logger.info(f"Poll count: {poll_count}/{max_polls}")
            
            # Download recording and metadata
            if recording_available:
                logger.info(f"Requesting recording data for bot {bot_id}")
                recording_response = requests.get(
                    f"{self.base_url}/bots/{bot_id}/recording",
                    headers=headers
                )
                
                if recording_response.status_code == 200:
                    recording_data = recording_response.json()
                    
                    # Extract data according to API documentation
                    recording_url = recording_data.get("url")  # Short-lived S3 URL
                    start_timestamp_ms = recording_data.get("start_timestamp_ms")
                    
                    logger.info(f"Recording URL obtained, start timestamp: {start_timestamp_ms}")
                    
                    # Get user hash key from database if db_meeting_id is provided
                    user_hash_key = None
                    meeting_datetime = datetime.now().strftime("%Y%m%d_%H%M%S")
                    
                    # Try to get user hash key and scheduled time from database
                    if hasattr(self, 'config') and hasattr(self.config, 'database_path') and db_meeting_id:
                        try:
                            # Import here to avoid circular imports
                            from src.database.manager import DatabaseManager
                            
                            # Get database manager
                            db_manager = DatabaseManager(self.config.database_path)
                            
                            # Get meeting information
                            meeting_info = db_manager.get_meeting(db_meeting_id)
                            if meeting_info:
                                user_hash_key = meeting_info.get('user_hash_key')
                                
                                # Use scheduled time if available for directory naming
                                scheduled_time = meeting_info.get('scheduled_time')
                                if scheduled_time:
                                    try:
                                        dt = datetime.fromisoformat(scheduled_time)
                                        meeting_datetime = dt.strftime("%Y%m%d_%H%M%S")
                                    except (ValueError, TypeError):
                                        # If scheduled_time is not a valid ISO format, use current time
                                        pass
                                
                                logger.info(f"Retrieved user hash key: {user_hash_key} for meeting {db_meeting_id}")
                                print(f"[ZoomBotController] Retrieved user hash key: {user_hash_key} for meeting {db_meeting_id}")
                        except Exception as e:
                            logger.error(f"Error getting user hash key from database: {str(e)}")
                            print(f"[ZoomBotController] Error getting user hash key from database: {str(e)}")
                    
                    # Create a directory structure based on user hash key and meeting datetime
                    base_storage_path = self.config.local_storage_path if self.config else os.environ.get('LOCAL_STORAGE_PATH', './data')
                    
                    if user_hash_key:
                        # Structure: data/<user_hash_key>/<meeting_datetime>/
                        meeting_dir = os.path.join(base_storage_path, user_hash_key, meeting_datetime)
                    else:
                        # Fallback structure if user hash key is not available: data/unknown/<meeting_id>_<timestamp>/
                        meeting_dir = os.path.join(base_storage_path, "unknown", f"meeting_{meeting_id}_{timestamp}")
                    
                    os.makedirs(meeting_dir, exist_ok=True)
                    logger.info(f"Created directory for meeting recordings: {meeting_dir}")
                    print(f"[ZoomBotController] Created directory for meeting recordings: {meeting_dir}")
                    
                    # Save metadata about the meeting and recording
                    metadata_path = os.path.join(meeting_dir, "metadata.json")
                    with open(metadata_path, 'w', encoding='utf-8') as f:
                        json.dump({
                            "bot_id": bot_id,
                            "meeting_id": meeting_id,
                            "db_meeting_id": db_meeting_id,
                            "user_hash_key": user_hash_key,
                            "meeting_url": meeting_url,
                            "start_timestamp_ms": start_timestamp_ms,
                            "recording_url": recording_url,
                            "timestamp": timestamp,
                            "meeting_datetime": meeting_datetime,
                            "recording_state": status.get("recording_state"),
                            "transcription_state": status.get("transcription_state")
                        }, f, indent=2)
                    logger.info(f"Saved meeting metadata to {metadata_path}")
                    
                    # Download the actual recording file
                    if recording_url:
                        # Update recording path to use the meeting directory
                        recording_path = os.path.join(meeting_dir, "recording.mp4")
                        
                        logger.info(f"Downloading recording from {recording_url}")
                        download_response = requests.get(recording_url, stream=True)
                        
                        if download_response.status_code == 200:
                            with open(recording_path, 'wb') as f:
                                for chunk in download_response.iter_content(chunk_size=8192):
                                    f.write(chunk)
                            logger.info(f"Downloaded recording to {recording_path}")
                        else:
                            logger.warning(f"Failed to download recording from URL: {download_response.status_code}")
                            recording_path = None
                    else:
                        logger.warning("No recording URL available")
                        recording_path = None
                else:
                    logger.warning(f"Failed to get recording data: {recording_response.status_code}")
                    recording_path = None
            else:
                logger.warning("No recording available")
                recording_path = None
            
            # Process recording with Hume AI if available
            hume_analysis_path = None
            insights_path = None
            
            if self.analytics_processor and recording_path and os.path.exists(recording_path):
                logger.info(f"Processing recording with Hume AI: {recording_path}")
                
                try:
                    # Use the analytics processor to process the recording and generate insights
                    # The processor will save files in the same directory as the recording
                    hume_analysis_path, insights_path = self.analytics_processor.process_recording_and_generate_insights(
                        recording_path=recording_path,
                        transcript_path=transcript_path
                    )
                    
                    logger.info(f"Completed Hume AI analysis: {hume_analysis_path}")
                    logger.info(f"Generated insights: {insights_path}")
                
                except Exception as e:
                    logger.exception(f"Error processing recording with Hume AI: {e}")
            else:
                logger.info("Skipping Hume AI analysis (recording or transcript not available)")
            
            # Download transcript if available
            if transcript_available:
                logger.info(f"Requesting transcript data for bot {bot_id}")
                transcript_response = requests.get(
                    f"{self.base_url}/bots/{bot_id}/transcript",
                    headers=headers
                )
                
                if transcript_response.status_code == 200:
                    # According to API documentation, this returns an array of transcribed utterances
                    transcript_data = transcript_response.json()
                    
                    # Create meeting directory if it doesn't exist yet
                    meeting_dir = os.path.join(self.config.local_storage_path if self.config else os.environ.get('LOCAL_STORAGE_PATH', './data'), user_hash_key, meeting_datetime)
                    os.makedirs(meeting_dir, exist_ok=True)
                    
                    # Save raw transcript data
                    raw_transcript_path = os.path.join(meeting_dir, "transcript_raw.json")
                    with open(raw_transcript_path, 'w', encoding='utf-8') as f:
                        json.dump(transcript_data, f, indent=2)
                    logger.info(f"Saved raw transcript data to {raw_transcript_path}")
                    
                    # Format transcript for human readability using the new formatter
                    transcript_path = os.path.join(meeting_dir, "transcript.txt")
                    format_transcript(raw_transcript_path, transcript_path, format_type="conversation")
                    
                else:
                    logger.warning(f"Failed to download transcript: {transcript_response.status_code}")
                    # Ensure meeting directory exists
                    meeting_dir = os.path.join(self.config.local_storage_path if self.config else os.environ.get('LOCAL_STORAGE_PATH', './data'), user_hash_key, meeting_datetime)
                    os.makedirs(meeting_dir, exist_ok=True)
                    
                    # Create an empty transcript file
                    transcript_path = os.path.join(meeting_dir, "transcript.txt")
                    with open(transcript_path, 'w', encoding='utf-8') as f:
                        f.write("No transcript available.")
            else:
                logger.warning("No transcript available")
                # Ensure meeting directory exists
                meeting_dir = os.path.join(self.config.local_storage_path if self.config else os.environ.get('LOCAL_STORAGE_PATH', './data'), user_hash_key, meeting_datetime)
                os.makedirs(meeting_dir, exist_ok=True)
                
                # Create an empty transcript file
                transcript_path = os.path.join(meeting_dir, "transcript.txt")
                with open(transcript_path, 'w', encoding='utf-8') as f:
                    f.write("No transcript available.")
            
            # Create a summary file with all the data paths
            summary_path = os.path.join(meeting_dir, f"interview_{timestamp}_summary.json")
            summary = {
                "bot_id": bot_id,
                "meeting_id": meeting_id,
                "db_meeting_id": db_meeting_id,
                "user_hash_key": user_hash_key,
                "meeting_url": meeting_url,
                "timestamp": timestamp,
                "recording_path": recording_path,
                "transcript_path": transcript_path,
                "hume_analysis_path": hume_analysis_path,
                "insights_path": insights_path
            }
            
            with open(summary_path, 'w', encoding='utf-8') as f:
                json.dump(summary, f, indent=2)
            
            logger.info(f"Created interview summary at {summary_path}")
            
            return recording_path or None, transcript_path or None, hume_analysis_path or None, insights_path or None
            
        except requests.exceptions.RequestException as e:
            logger.exception(f"Error calling Attendee API: {e}")
            return None, None, None, None
        except Exception as e:
            logger.exception(f"Error joining Zoom meeting: {e}")
            return None, None, None, None
    
    def _format_timestamp(self, timestamp_ms):
        """Format millisecond timestamp into a readable format.
        
        Args:
            timestamp_ms: Timestamp in milliseconds
            
        Returns:
            str: Formatted timestamp (HH:MM:SS.mmm)
        """
        total_seconds = timestamp_ms / 1000
        hours = int(total_seconds // 3600)
        minutes = int((total_seconds % 3600) // 60)
        seconds = int(total_seconds % 60)
        milliseconds = int((total_seconds % 1) * 1000)
        
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{milliseconds:03d}"
    
    def get_meeting_info(self, meeting_id):
        """Get information about a Zoom meeting.
        
        Args:
            meeting_id: The Zoom meeting ID
            
        Returns:
            dict: Meeting information
        """
        # This would typically use the Zoom API to get meeting details
        # For now, we'll return a placeholder
        return {
            "id": meeting_id,
            "topic": "Interview Meeting",
            "start_time": datetime.now().isoformat(),
            "duration": 60,  # minutes
            "host_email": "host@example.com",
        }
    
    def cleanup(self):
        """Clean up temporary files."""
        try:
            import shutil
            shutil.rmtree(self.temp_dir)
            logger.info(f"Cleaned up temporary directory: {self.temp_dir}")
        except Exception as e:
            logger.error(f"Error cleaning up temporary directory: {e}")
