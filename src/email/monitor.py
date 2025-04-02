"""
Email Monitor for the Zoom Interview Analysis System.

This module monitors an email inbox for Zoom meeting invitations.
"""

import os
import re
import time
import base64
import email
import email.header
import imaplib
import logging
import json
import hashlib
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
import threading
import sqlite3
import dateutil.parser
import traceback

logger = logging.getLogger(__name__)

class EmailMonitor:
    """Monitors an email inbox for Zoom meeting invitations."""
    
    def __init__(self, email_address, password, imap_server, db_manager, scheduler, 
                 poll_interval=30, mark_as_read=False, gmail_api_credentials=None):
        """Initialize the email monitor.
        
        Args:
            email_address: Email address to monitor
            password: Email password
            imap_server: IMAP server address
            db_manager: Database manager instance
            scheduler: Zoom bot scheduler instance
            poll_interval: Polling interval in seconds
            mark_as_read: Whether to mark emails as read after processing
            gmail_api_credentials: Optional dict with Gmail API credentials
        """
        self.email_address = email_address
        self.email_password = password
        self.imap_server = imap_server
        self.db_manager = db_manager
        self.scheduler = scheduler
        self.poll_interval = poll_interval
        self.mark_as_read = mark_as_read
        self.running = False
        self.thread = None
        self.gmail_api_client = None
        
        # Initialize Gmail API client if credentials are provided
        if gmail_api_credentials:
            try:
                from src.email.gmail_api import GmailAPIClient
                self.gmail_api_client = GmailAPIClient(
                    client_id=gmail_api_credentials.get('client_id'),
                    client_secret=gmail_api_credentials.get('client_secret'),
                    refresh_token=gmail_api_credentials.get('refresh_token')
                )
                logger.info("Gmail API client initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize Gmail API client: {str(e)}")
                logger.info("Falling back to IMAP for email monitoring")
        
        # Regex pattern to extract Zoom meeting URLs
        self.zoom_url_pattern = re.compile(
            r'https://(?:[\w-]+\.)?zoom\.us/j/\d+(?:\?pwd=[\w\.\d\-_]+(?:\.\d+)?)?(?:&[\w\.\d\-_=&]+)?'
        )
        
        # Add debug logging for URL extraction
        logger.info("Initialized Zoom URL pattern for extraction")
        print("[EmailMonitor] Initialized with Zoom URL pattern for extraction")
        
        # Regex pattern to extract meeting details
        self.meeting_title_pattern = re.compile(r'Subject: (.*?)(?:\r?\n)')
        self.meeting_time_pattern = re.compile(r'Time: (.*?)(?:\r?\n)')
        
    def start(self):
        """Start the email monitoring thread."""
        if self.thread and self.thread.is_alive():
            logger.warning("Email monitor is already running")
            return
        
        self.running = True
        self.thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.thread.start()
        logger.info(f"Started email monitoring for {self.email_address}")
        
    def stop(self):
        """Stop the email monitoring thread."""
        self.running = False
        if self.thread:
            self.thread.join(timeout=10)
            logger.info("Stopped email monitoring")
    
    def start_polling(self):
        """Start polling for new emails in a separate thread."""
        if self.running:
            logger.warning("Email monitor is already running")
            return
        
        self.running = True
        self.thread = threading.Thread(target=self._polling_loop)
        self.thread.daemon = True
        self.thread.start()
        logger.info("Started email polling thread")
    
    def stop_polling(self):
        """Stop the polling thread."""
        if not self.running:
            logger.warning("Email monitor is not running")
            return
        
        self.running = False
        if self.thread:
            self.thread.join(timeout=5.0)
            logger.info("Stopped email polling thread")
    
    def _monitor_loop(self):
        """Main monitoring loop that polls the email inbox."""
        while self.running:
            try:
                new_meetings = self._check_for_new_invitations()
                if new_meetings:
                    for meeting in new_meetings:
                        self._process_meeting_invitation(meeting)
                
                # Sleep for the configured interval
                time.sleep(self.poll_interval)
            except Exception as e:
                logger.error(f"Error in email monitoring loop: {str(e)}")
                time.sleep(60)  # Wait a minute before retrying
    
    def _polling_loop(self):
        """Main polling loop that checks for new emails periodically."""
        while self.running:
            try:
                # Check for new meeting invitations
                meetings = self._check_for_new_invitations()
                
                # Process any found meetings
                for meeting_info in meetings:
                    self._process_meeting_invitation(meeting_info)
                
                # Sleep for the configured interval
                time.sleep(self.poll_interval)
            except Exception as e:
                logger.error(f"Error in email polling loop: {str(e)}")
                # Sleep for a short time to avoid tight error loops
                time.sleep(5)
    
    def _check_for_new_invitations(self) -> List[Dict]:
        """Check for new meeting invitations in the inbox.
        
        Returns:
            List of dictionaries containing meeting details
        """
        # Try using Gmail API first if available
        if self.gmail_api_client:
            try:
                logger.info("Checking for new invitations using Gmail API")
                invitations = self.gmail_api_client.find_zoom_invitations()
                
                # Mark messages as read if configured to do so
                if self.mark_as_read and invitations:
                    for invitation in invitations:
                        if 'message_id' in invitation:
                            self.gmail_api_client.mark_as_read(invitation['message_id'])
                
                return invitations
            except Exception as e:
                logger.error(f"Error using Gmail API: {str(e)}")
                logger.info("Falling back to IMAP")
        
        # Fall back to IMAP if Gmail API is not available or fails
        meetings = []
        
        try:
            # Connect to the IMAP server
            mail = imaplib.IMAP4_SSL(self.imap_server)
            mail.login(self.email_address, self.email_password)
            mail.select("INBOX")
            
            # Search for unread emails from the last 24 hours
            date = (datetime.now() - timedelta(days=1)).strftime("%d-%b-%Y")
            status, messages = mail.search(None, f'(UNSEEN SINCE {date})')
            
            if status != "OK" or not messages[0]:
                return []
            
            # Process each unread email
            for message_id in messages[0].split():
                status, msg_data = mail.fetch(message_id, "(RFC822)")
                
                if status != "OK":
                    continue
                
                raw_email = msg_data[0][1]
                email_message = email.message_from_bytes(raw_email)
                
                # Extract subject
                subject = self._decode_email_header(email_message["Subject"])
                
                # Check if this is likely a meeting invitation
                if "zoom" in subject.lower() or "meeting" in subject.lower() or "interview" in subject.lower():
                    meeting_info = self._extract_meeting_info(email_message)
                    
                    if meeting_info and "url" in meeting_info:
                        meetings.append(meeting_info)
                        
                        # Mark as read if configured to do so
                        if self.mark_as_read:
                            mail.store(message_id, "+FLAGS", "\\Seen")
            
            mail.logout()
            
        except Exception as e:
            logger.error(f"Error checking for new invitations: {str(e)}")
        
        return meetings
    
    def _extract_meeting_info(self, email_message) -> Optional[Dict]:
        """Extract meeting information from an email message.
        
        Args:
            email_message: Email message object
            
        Returns:
            Dictionary containing meeting details or None if no meeting found
        """
        meeting_info = {
            "subject": self._decode_email_header(email_message["Subject"]),
            "from": self._decode_email_header(email_message["From"]),
            "date": self._decode_email_header(email_message["Date"]),
            "received_at": datetime.now().isoformat(),
        }
        
        print(f"\n[EmailMonitor] Processing email with subject: {meeting_info['subject']}")
        print(f"[EmailMonitor] From: {meeting_info['from']}")
        
        # Extract the email body
        body = self._get_message_body(email_message)
        
        # Parse Zoom invite details
        zoom_details = self._parse_zoom_invite(body)
        
        if zoom_details and zoom_details.get('meeting_link'):
            meeting_info["url"] = zoom_details.get('meeting_link')
            print(f"[EmailMonitor] Extracted meeting URL from _parse_zoom_invite: {meeting_info['url']}")
            
            # Add meeting ID if available
            if zoom_details.get('meeting_id'):
                meeting_info["meeting_id"] = zoom_details.get('meeting_id')
                print(f"[EmailMonitor] Extracted meeting ID: {meeting_info['meeting_id']}")
            
            # Add password if available
            if zoom_details.get('password'):
                meeting_info["password"] = zoom_details.get('password')
                print(f"[EmailMonitor] Extracted password: {meeting_info['password']}")
            
            # Add start time if available
            if zoom_details.get('start_time'):
                meeting_info["scheduled_time"] = zoom_details.get('start_time')
                print(f"[EmailMonitor] Extracted scheduled time: {meeting_info['scheduled_time']}")
            
            # Extract candidate name if available
            if "candidate" in body.lower() or "applicant" in body.lower():
                candidate_match = re.search(r'[Cc]andidate:?\s*([\w\s]+)', body)
                if candidate_match:
                    meeting_info["candidate_name"] = candidate_match.group(1).strip()
                    print(f"[EmailMonitor] Extracted candidate name: {meeting_info['candidate_name']}")
            
            # Extract position if available
            if "position" in body.lower() or "role" in body.lower():
                position_match = re.search(r'[Pp]osition:?\s*([\w\s]+)', body)
                if position_match:
                    meeting_info["position"] = position_match.group(1).strip()
                    print(f"[EmailMonitor] Extracted position: {meeting_info['position']}")
            
            return meeting_info
        
        # Fallback to the old method if the new parsing doesn't find a meeting link
        print("[EmailMonitor] Using fallback method for URL extraction")
        # Extract Zoom URL
        zoom_urls = self.zoom_url_pattern.findall(body)
        if zoom_urls:
            print(f"[EmailMonitor] Found {len(zoom_urls)} potential Zoom URLs:")
            for i, url in enumerate(zoom_urls):
                print(f"[EmailMonitor] URL {i+1}: {url}")
            
            # Get the first URL that contains a password parameter if possible
            full_url = None
            for url in zoom_urls:
                if "?pwd=" in url:
                    full_url = url
                    print(f"[EmailMonitor] Selected URL with password: {full_url}")
                    break
            
            # If no URL with password found, use the first one
            if not full_url and zoom_urls:
                full_url = zoom_urls[0]
                print(f"[EmailMonitor] No URL with password found, using first URL: {full_url}")
            
            meeting_info["url"] = full_url
            logger.info(f"Extracted Zoom URL with fallback method: {meeting_info['url']}")
            
            # Extract meeting password if not in URL
            if "?pwd=" not in meeting_info["url"] and "password" in body.lower():
                pwd_match = re.search(r'[Pp]assword:?\s*(\w+)', body)
                if pwd_match:
                    meeting_info["password"] = pwd_match.group(1)
                    logger.info(f"Extracted password from email body: {meeting_info['password']}")
                    print(f"[EmailMonitor] Extracted password from email body: {meeting_info['password']}")
                    
                    # Add the password to the URL
                    if '?' in meeting_info["url"]:
                        meeting_info["url"] += f"&pwd={meeting_info['password']}"
                    else:
                        meeting_info["url"] += f"?pwd={meeting_info['password']}"
                    print(f"[EmailMonitor] Added password to URL: {meeting_info['url']}")
                    logger.info(f"Added password to meeting URL: {meeting_info['url']}")
            
            # Extract scheduled time
            time_match = self.meeting_time_pattern.search(body)
            if time_match:
                meeting_info["scheduled_time"] = time_match.group(1).strip()
            
            # Extract candidate name if available
            if "candidate" in body.lower() or "applicant" in body.lower():
                candidate_match = re.search(r'[Cc]andidate:?\s*([\w\s]+)', body)
                if candidate_match:
                    meeting_info["candidate_name"] = candidate_match.group(1).strip()
            
            # Extract position if available
            if "position" in body.lower() or "role" in body.lower():
                position_match = re.search(r'[Pp]osition:?\s*([\w\s]+)', body)
                if position_match:
                    meeting_info["position"] = position_match.group(1).strip()
            
            return meeting_info
        
        return None

    def _get_message_body(self, message):
        """
        Extracts the message body from an email message.
        Looks for a text/plain part first; if not found, falls back to text/html.
        """
        # Handle Gmail API message format
        if isinstance(message, dict) and 'payload' in message:
            payload = message.get('payload', {})
            body = ""
            if 'parts' in payload:
                for part in payload['parts']:
                    mime = part.get('mimeType', '')
                    data = part.get('body', {}).get('data')
                    if data and mime == 'text/plain':
                        body = base64.urlsafe_b64decode(data.encode('UTF-8')).decode('utf-8')
                        return body
                # Fallback: if no plain text found, try HTML parts
                for part in payload['parts']:
                    mime = part.get('mimeType', '')
                    data = part.get('body', {}).get('data')
                    if data and mime == 'text/html':
                        body = base64.urlsafe_b64decode(data.encode('UTF-8')).decode('utf-8')
                        return body
            else:
                data = payload.get('body', {}).get('data')
                if data:
                    body = base64.urlsafe_b64decode(data.encode('UTF-8')).decode('utf-8')
            return body
        
        # Handle standard email.message.Message objects (IMAP)
        body = ""
        if message.is_multipart():
            for part in message.walk():
                content_type = part.get_content_type()
                if content_type == "text/plain" or content_type == "text/html":
                    try:
                        body += part.get_payload(decode=True).decode()
                    except:
                        pass
        else:
            try:
                body = message.get_payload(decode=True).decode()
            except:
                pass
        
        return body

    def _parse_zoom_invite(self, email_body):
        """
        Parses the email body text to extract Zoom meeting details.
        Returns a dictionary with keys:
          - meeting_link
          - meeting_id
          - password
          - start_time
        If any component is not found, its value will be None.
        """
        print("[EmailMonitor] Parsing Zoom invite using _parse_zoom_invite method")
        result = {}

        # Regex patterns for Zoom meeting details
        zoom_link_pattern = r"(https?://[^\s]*zoom\.us/j/\d+(?:\?pwd=[\w\.\d\-_]+(?:\.\d+)?)?(?:&[\w\.\d\-_=&]+)?)"
        meeting_id_pattern = r"Meeting\s*ID[:\s]*([\d\s]+)"
        # Sometimes the invite shows "Passcode" or "Password"
        passcode_pattern = r"(?:Passcode|Password)[:\s]*([\w\d]+)"
        # Attempt to capture a start time. Many invites include a line like "Start Time:" or "When:".
        start_time_pattern = r"(?:Start Time|When)[:\s]*(.+)"

        # Search for a Zoom meeting link in the email body
        link_match = re.search(zoom_link_pattern, email_body, re.IGNORECASE)
        result['meeting_link'] = link_match.group(1) if link_match else None

        # Log the extracted meeting link for debugging
        if result['meeting_link']:
            logger.info(f"_parse_zoom_invite extracted meeting link: {result['meeting_link']}")
            print(f"[EmailMonitor] _parse_zoom_invite extracted meeting link: {result['meeting_link']}")
        else:
            print("[EmailMonitor] No meeting link found by _parse_zoom_invite")
        
        # Search for Meeting ID (if not part of the URL)
        id_match = re.search(meeting_id_pattern, email_body, re.IGNORECASE)
        result['meeting_id'] = id_match.group(1).strip() if id_match else None

        # Search for the Passcode/Password
        pass_match = re.search(passcode_pattern, email_body, re.IGNORECASE)
        result['password'] = pass_match.group(1).strip() if pass_match else None
        
        # If we found a password and the URL doesn't already have it, add it
        if result['password'] and result['meeting_link'] and '?pwd=' not in result['meeting_link']:
            # Extract meeting ID from URL if possible
            meeting_id_from_url = None
            url_id_match = re.search(r'/j/(\d+)', result['meeting_link'])
            if url_id_match:
                meeting_id_from_url = url_id_match.group(1)
            
            # Add password to URL
            if '?' in result['meeting_link']:
                result['meeting_link'] += f"&pwd={result['password']}"
                print(f"[EmailMonitor] Added password to URL with existing parameters: {result['meeting_link']}")
            else:
                result['meeting_link'] += f"?pwd={result['password']}"
                print(f"[EmailMonitor] Added password to URL: {result['meeting_link']}")
            
            logger.info(f"Added password to meeting URL: {result['meeting_link']}")

        # Search for the Start Time
        time_match = re.search(start_time_pattern, email_body, re.IGNORECASE)
        result['start_time'] = time_match.group(1).strip() if time_match else None

        return result

    def _process_meeting_invitation(self, meeting_info: Dict):
        """Process a meeting invitation.
        
        Args:
            meeting_info: Dictionary containing meeting details
            
        Returns:
            Meeting ID if processed successfully, None otherwise
        """
        try:
            print("\n[EmailMonitor] Processing meeting invitation")
            # Extract meeting details
            meeting_url = meeting_info.get('url')
            print(f"[EmailMonitor] Initial meeting URL: {meeting_url}")
            
            # If we don't have a URL in the standard format, check if we have a meeting_link from _parse_zoom_invite
            if not meeting_url and meeting_info.get('meeting_link'):
                meeting_url = meeting_info.get('meeting_link')
                logger.info(f"Using meeting_link as URL: {meeting_url}")
                meeting_info['url'] = meeting_url
                print(f"[EmailMonitor] Using meeting_link as URL: {meeting_url}")
            
            # Check if we have a password that's not in the URL
            password = meeting_info.get('password')
            if password and meeting_url and '?pwd=' not in meeting_url and '&pwd=' not in meeting_url:
                # Add the password to the URL
                if '?' in meeting_url:
                    meeting_url += f"&pwd={password}"
                else:
                    meeting_url += f"?pwd={password}"
                meeting_info['url'] = meeting_url
                print(f"[EmailMonitor] Added password to URL in _process_meeting_invitation: {meeting_url}")
                logger.info(f"Added password to meeting URL in _process_meeting_invitation: {meeting_url}")
            
            from_email = meeting_info.get('from', '').lower()
            message_id = meeting_info.get('message_id')
            
            # Extract the actual email address from the "From" field
            # Example: "John Doe <john@example.com>" -> "john@example.com"
            email_match = re.search(r'<([^>]+)>', from_email)
            if email_match:
                from_email = email_match.group(1).lower()
                print(f"[EmailMonitor] Extracted email address: {from_email}")
            
            if not meeting_url or not from_email:
                logger.warning("Missing required meeting information")
                print("[EmailMonitor] Missing required meeting information, cannot process invitation")
                return None
            
            logger.info(f"Processing meeting invitation from {from_email} with URL {meeting_url}")
            print(f"[EmailMonitor] Processing meeting invitation from {from_email}")
            print(f"[EmailMonitor] With URL: {meeting_url}")
            
            # Extract Zoom meeting ID from URL if available
            zoom_meeting_id = None
            zoom_id_match = re.search(r'/j/(\d+)', meeting_url)
            if zoom_id_match:
                zoom_meeting_id = zoom_id_match.group(1)
                print(f"[EmailMonitor] Extracted Zoom meeting ID from URL: {zoom_meeting_id}")
            
            # Check if a meeting with this URL or Zoom meeting ID already exists
            existing_meeting = self.db_manager.find_meeting_by_url_or_id(url=meeting_url, zoom_meeting_id=zoom_meeting_id)
            if existing_meeting:
                logger.info(f"Meeting with URL {meeting_url} or Zoom ID {zoom_meeting_id} already exists (ID: {existing_meeting['id']})")
                print(f"[EmailMonitor] Meeting already exists in database with ID: {existing_meeting['id']}")
                
                # Check if the meeting is already scheduled or in progress
                meeting_status = existing_meeting.get('status', '').lower()
                if meeting_status in ['scheduled', 'joining', 'in_progress', 'recording']:
                    logger.info(f"Meeting {existing_meeting['id']} is already {meeting_status}, skipping")
                    print(f"[EmailMonitor] Meeting is already {meeting_status}, skipping to prevent duplicate bots")
                    return existing_meeting['id']
                
                # If the meeting exists but has a completed or failed status, we can update it and reschedule
                logger.info(f"Meeting {existing_meeting['id']} has status {meeting_status}, updating and rescheduling")
                print(f"[EmailMonitor] Meeting has status {meeting_status}, updating and rescheduling")
                
                # Update the meeting with new information
                self.db_manager.update_meeting(
                    existing_meeting['id'],
                    url=meeting_url,
                    meeting_id=zoom_meeting_id,
                    password=password,
                    status="pending"
                )
                
                # Schedule the meeting
                scheduled_time_iso = meeting_info.get('scheduled_time')
                if not scheduled_time_iso:
                    logger.warning("No scheduled time found, joining meeting immediately")
                    print("[EmailMonitor] No scheduled time found, joining meeting immediately")
                    
                    # Join the meeting immediately
                    if self.scheduler:
                        print(f"[EmailMonitor] Calling scheduler.join_meeting_now with meeting_id={existing_meeting['id']}, url={meeting_url}")
                        self.scheduler.join_meeting_now(existing_meeting['id'], meeting_url)
                    else:
                        logger.warning("No scheduler available, cannot join meeting immediately")
                        print("[EmailMonitor] No scheduler available, cannot join meeting immediately")
                else:
                    # Schedule the meeting
                    if self.scheduler:
                        print(f"[EmailMonitor] Scheduling meeting with meeting_id={existing_meeting['id']}, url={meeting_url}, time={scheduled_time_iso}")
                        self.scheduler.schedule_meeting(existing_meeting['id'], meeting_url, scheduled_time_iso)
                    else:
                        logger.warning("No scheduler available, cannot schedule meeting")
                        print("[EmailMonitor] No scheduler available, cannot schedule meeting")
                
                return existing_meeting['id']
            
            # Generate a unique hash key for this user/meeting combination
            user_hash_key = hashlib.md5(f"{from_email}_{datetime.now().isoformat()}".encode()).hexdigest()[:16]
            
            # Add the user to the database
            user_id = self.db_manager.add_user(
                email=from_email,
                hash_key=user_hash_key
            )
            
            if not user_id:
                logger.error(f"Failed to add user with email {from_email}")
                print(f"[EmailMonitor] Failed to add user with email {from_email}")
                return None
            
            # Extract meeting ID and password from URL or meeting info
            meeting_id = meeting_info.get('meeting_id')
            if not meeting_id and zoom_meeting_id:
                meeting_id = zoom_meeting_id
            
            # If password is not already set, try to extract it from meeting info
            if not password:
                password = meeting_info.get('password')
            
            # Get scheduled time
            scheduled_time_iso = None
            scheduled_time = meeting_info.get('scheduled_time')
            
            if scheduled_time:
                # Try to parse the scheduled time
                try:
                    if isinstance(scheduled_time, str):
                        parsed_time = self._parse_meeting_time(scheduled_time)
                        if parsed_time:
                            scheduled_time_iso = parsed_time.isoformat()
                    elif isinstance(scheduled_time, datetime):
                        scheduled_time_iso = scheduled_time.isoformat()
                except Exception as e:
                    logger.error(f"Error parsing scheduled time: {str(e)}")
            
            # Add the meeting to the database
            db_meeting_id = self.db_manager.add_meeting(
                user_hash_key=user_hash_key,
                url=meeting_url,
                meeting_id=meeting_id,
                password=password,
                scheduled_time=scheduled_time_iso,
                status="pending"
            )
            
            if not db_meeting_id:
                logger.error(f"Failed to add meeting for user {user_id}")
                print(f"[EmailMonitor] Failed to add meeting for user {user_id}")
                return None
            
            logger.info(f"Added meeting {db_meeting_id} for user {user_id} (hash_key: {user_hash_key})")
            print(f"[EmailMonitor] Added meeting {db_meeting_id} for user {user_id} (hash_key: {user_hash_key})")
            print(f"[EmailMonitor] Meeting URL saved to database: {meeting_url}")
            
            # Mark the message as read if we have a message_id and Gmail API client
            if message_id and self.gmail_api_client:
                self.gmail_api_client.mark_as_read(message_id)
                logger.info(f"Marked message {message_id} as read")
                print(f"[EmailMonitor] Marked message {message_id} as read")
            
            # If no scheduled time is found, join the meeting immediately
            if not scheduled_time_iso:
                logger.warning("No scheduled time found, joining meeting immediately")
                print("[EmailMonitor] No scheduled time found, joining meeting immediately")
                
                # Join the meeting immediately
                if self.scheduler:
                    print(f"[EmailMonitor] Calling scheduler.join_meeting_now with meeting_id={db_meeting_id}, url={meeting_url}")
                    self.scheduler.join_meeting_now(db_meeting_id, meeting_url)
                else:
                    logger.warning("No scheduler available, cannot join meeting immediately")
                    print("[EmailMonitor] No scheduler available, cannot join meeting immediately")
            else:
                # Schedule the meeting
                if self.scheduler:
                    print(f"[EmailMonitor] Scheduling meeting with meeting_id={db_meeting_id}, url={meeting_url}, time={scheduled_time_iso}")
                    self.scheduler.schedule_meeting(db_meeting_id, meeting_url, scheduled_time_iso)
                else:
                    logger.warning("No scheduler available, cannot schedule meeting")
                    print("[EmailMonitor] No scheduler available, cannot schedule meeting")
            
            return db_meeting_id
            
        except Exception as e:
            logger.error(f"Error processing meeting invitation: {str(e)}")
            print(f"[EmailMonitor] Error processing meeting invitation: {str(e)}")
            traceback.print_exc()
            return None

    def _generate_hash_key(self):
        """Generate a unique hash key for a user.
        
        Returns:
            A unique hash key string
        """
        import uuid
        import hashlib
        
        # Generate a random UUID and hash it
        random_uuid = uuid.uuid4()
        hash_obj = hashlib.sha256(str(random_uuid).encode())
        
        # Return the first 16 characters of the hexadecimal digest
        return hash_obj.hexdigest()[:16]
    
    def _parse_meeting_time(self, time_str):
        """Parse a meeting time string into a datetime object.
        
        Args:
            time_str: String containing the meeting time
            
        Returns:
            datetime object or None if parsing fails
        """
        from dateutil import parser
        
        try:
            # Try to parse the time string
            dt = parser.parse(time_str)
            
            # If the parsed time is in the past, it might be for a future date
            now = datetime.now()
            if dt < now:
                # If it's more than 12 hours in the past, assume it's for tomorrow
                if (now - dt).total_seconds() > 12 * 3600:
                    dt = dt.replace(day=now.day + 1)
            
            return dt
        except Exception as e:
            logger.error(f"Error parsing time string '{time_str}': {str(e)}")
            return None

    @staticmethod
    def _decode_email_header(header: str) -> str:
        """Decode an email header string.
        
        Args:
            header: Email header string
            
        Returns:
            Decoded header string
        """
        if not header:
            return ""
        
        decoded_parts = []
        for part, encoding in email.header.decode_header(header):
            if isinstance(part, bytes):
                try:
                    if encoding:
                        decoded_parts.append(part.decode(encoding))
                    else:
                        decoded_parts.append(part.decode())
                except:
                    decoded_parts.append(part.decode('utf-8', errors='replace'))
            else:
                decoded_parts.append(part)
        
        return " ".join(decoded_parts)


def test_email_monitor():
    """Test the email monitor functionality."""
    from types import SimpleNamespace
    import getpass
    import tempfile
    import os
    
    # Create a temporary database for testing
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as temp_db:
        temp_db_path = temp_db.name
    
    try:
        # Create a simple config for testing
        email_address = input("Enter email address: ")
        password = getpass.getpass("Enter email password: ")
        imap_server = "imap.gmail.com"
        poll_interval = 60
        mark_as_read = False
        
        # Set up logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        
        # Create and start the email monitor
        from src.database.manager import DatabaseManager
        from src.zoom_bot.scheduler import ZoomBotScheduler
        db_manager = DatabaseManager(temp_db_path)
        scheduler = ZoomBotScheduler(None)  # Replace with actual scheduler instance
        monitor = EmailMonitor(email_address, password, imap_server, db_manager, scheduler, poll_interval, mark_as_read)
        
        try:
            print("Checking for Zoom meeting invitations...")
            meetings = monitor._check_for_new_invitations()
            
            if meetings:
                print(f"Found {len(meetings)} meeting invitations:")
                for i, meeting in enumerate(meetings, 1):
                    print(f"\nMeeting {i}:")
                    for key, value in meeting.items():
                        print(f"  {key}: {value}")
                    
                    # Process the meeting invitation
                    print(f"\nProcessing meeting {i}...")
                    monitor._process_meeting_invitation(meeting)
            else:
                print("No meeting invitations found.")
                
        except Exception as e:
            print(f"Error: {str(e)}")
            
    finally:
        # Clean up the temporary database
        try:
            os.unlink(temp_db_path)
        except:
            pass


if __name__ == "__main__":
    test_email_monitor()
