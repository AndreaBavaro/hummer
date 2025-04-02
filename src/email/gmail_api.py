"""
Gmail API integration module for the Zoom Interview Analysis System.

This module provides functions to interact with Gmail using the Gmail API,
which is more reliable and feature-rich than IMAP, especially for Google Workspace accounts.
"""

import os
import base64
import logging
import re
from typing import List, Dict, Optional
from datetime import datetime, timedelta

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

logger = logging.getLogger(__name__)

class GmailAPIClient:
    """Gmail API client for accessing Gmail data."""
    
    def __init__(self, client_id, client_secret, refresh_token):
        """Initialize the Gmail API client.
        
        Args:
            client_id: OAuth client ID
            client_secret: OAuth client secret
            refresh_token: OAuth refresh token
        """
        self.client_id = client_id
        self.client_secret = client_secret
        self.refresh_token = refresh_token
        self.service = None
        
        # Initialize the Gmail API service
        self._initialize_service()
    
    def _initialize_service(self):
        """Initialize the Gmail API service."""
        try:
            # Create credentials from the tokens
            creds = Credentials(
                token=None,  # We don't need an access token as we'll use the refresh token
                refresh_token=self.refresh_token,
                token_uri="https://oauth2.googleapis.com/token",
                client_id=self.client_id,
                client_secret=self.client_secret,
                scopes=["https://www.googleapis.com/auth/gmail.modify"]
            )
            
            # Refresh the credentials to get a valid access token
            creds.refresh(Request())
            
            # Build the Gmail API service
            self.service = build('gmail', 'v1', credentials=creds)
            logger.info("Gmail API service initialized successfully")
            
        except Exception as e:
            logger.error(f"Error initializing Gmail API service: {str(e)}")
            raise
    
    def get_unread_messages(self, max_results=100, query_days=1) -> List[Dict]:
        """Get unread messages from Gmail.
        
        Args:
            max_results: Maximum number of messages to retrieve
            query_days: Number of days to look back for messages
            
        Returns:
            List of message dictionaries
        """
        try:
            # Calculate the date for the query
            date = (datetime.now() - timedelta(days=query_days)).strftime("%Y/%m/%d")
            
            # Query for unread messages after the specified date
            query = f"is:unread after:{date}"
            
            # Get the list of message IDs
            results = self.service.users().messages().list(
                userId='me', 
                q=query, 
                maxResults=max_results
            ).execute()
            
            messages = results.get('messages', [])
            
            if not messages:
                logger.info("No unread messages found")
                return []
            
            # Get the full message details for each message ID
            full_messages = []
            for msg in messages:
                try:
                    msg_detail = self.service.users().messages().get(
                        userId='me', 
                        id=msg['id']
                    ).execute()
                    full_messages.append(msg_detail)
                except Exception as e:
                    logger.error(f"Error retrieving message {msg['id']}: {str(e)}")
            
            logger.info(f"Retrieved {len(full_messages)} unread messages")
            return full_messages
            
        except HttpError as error:
            logger.error(f"Gmail API HTTP error: {error}")
            return []
        except Exception as e:
            logger.error(f"Error getting unread messages: {str(e)}")
            return []
    
    def mark_as_read(self, message_id):
        """Mark a message as read.
        
        Args:
            message_id: ID of the message to mark as read
            
        Returns:
            True if successful, False otherwise
        """
        try:
            self.service.users().messages().modify(
                userId='me',
                id=message_id,
                body={'removeLabelIds': ['UNREAD']}
            ).execute()
            logger.info(f"Marked message {message_id} as read")
            return True
        except Exception as e:
            logger.error(f"Error marking message {message_id} as read: {str(e)}")
            return False
    
    def get_message_body(self, message):
        """Extract the message body from a Gmail message.
        
        Args:
            message: Gmail message object
            
        Returns:
            Message body as a string
        """
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
    
    def get_message_headers(self, message):
        """Extract headers from a Gmail message.
        
        Args:
            message: Gmail message object
            
        Returns:
            Dictionary of headers
        """
        headers = {}
        for header in message.get('payload', {}).get('headers', []):
            name = header.get('name', '').lower()
            value = header.get('value', '')
            headers[name] = value
        
        return headers
    
    def parse_zoom_invite(self, email_body):
        """Parse a Zoom meeting invitation from an email body.
        
        Args:
            email_body: Email body text
            
        Returns:
            Dictionary with meeting details or None if no meeting found
        """
        result = {}

        # Regex patterns for Zoom meeting details
        zoom_link_pattern = r"(https?://[^\s]*zoom\.us/j/\d+)"
        meeting_id_pattern = r"Meeting\s*ID[:\s]*([\d\s]+)"
        passcode_pattern = r"(?:Passcode|Password)[:\s]*([\w\d]+)"
        start_time_pattern = r"(?:Start Time|When)[:\s]*(.+)"

        # Search for a Zoom meeting link in the email body
        link_match = re.search(zoom_link_pattern, email_body, re.IGNORECASE)
        result['meeting_link'] = link_match.group(1) if link_match else None

        # Search for Meeting ID (if not part of the URL)
        id_match = re.search(meeting_id_pattern, email_body, re.IGNORECASE)
        result['meeting_id'] = id_match.group(1).strip() if id_match else None

        # Search for the Passcode/Password
        pass_match = re.search(passcode_pattern, email_body, re.IGNORECASE)
        result['password'] = pass_match.group(1).strip() if pass_match else None

        # Search for the Start Time
        time_match = re.search(start_time_pattern, email_body, re.IGNORECASE)
        result['start_time'] = time_match.group(1).strip() if time_match else None

        return result if result.get('meeting_link') else None
    
    def find_zoom_invitations(self) -> List[Dict]:
        """Find Zoom meeting invitations in unread emails.
        
        Returns:
            List of dictionaries with meeting details
        """
        invitations = []
        
        # Get unread messages
        messages = self.get_unread_messages()
        
        for message in messages:
            # Get message headers
            headers = self.get_message_headers(message)
            
            # Check if this is likely a meeting invitation based on subject
            subject = headers.get('subject', '')
            if not any(keyword in subject.lower() for keyword in ['zoom', 'meeting', 'interview']):
                continue
            
            # Get message body
            body = self.get_message_body(message)
            if not body:
                continue
            
            # Check if this is a Zoom invitation
            if "zoom.us/j/" not in body.lower():
                continue
            
            # Parse Zoom meeting details
            zoom_details = self.parse_zoom_invite(body)
            if not zoom_details:
                continue
            
            # Create invitation object
            invitation = {
                'message_id': message['id'],
                'subject': headers.get('subject', 'Untitled Meeting'),
                'from': headers.get('from', ''),
                'to': headers.get('to', ''),
                'date': headers.get('date', ''),
                'received_at': datetime.now().isoformat(),
                'url': zoom_details.get('meeting_link'),
                'meeting_id': zoom_details.get('meeting_id'),
                'password': zoom_details.get('password'),
                'scheduled_time': zoom_details.get('start_time')
            }
            
            invitations.append(invitation)
            logger.info(f"Found Zoom invitation: {invitation['subject']}")
        
        return invitations


# Example usage
def test_gmail_api():
    """Test the Gmail API client."""
    import os
    from dotenv import load_dotenv
    
    # Load environment variables
    load_dotenv()
    
    # Get credentials from environment variables
    client_id = os.environ.get('GMAIL_API_CLIENT_ID')
    client_secret = os.environ.get('GMAIL_API_CLIENT_SECRET')
    refresh_token = os.environ.get('GMAIL_API_REFRESH_TOKEN')
    
    if not all([client_id, client_secret, refresh_token]):
        print("Error: Gmail API credentials not found in environment variables.")
        print("Please run get_gmail_token.py to obtain the necessary credentials.")
        return
    
    try:
        # Initialize the Gmail API client
        gmail_client = GmailAPIClient(client_id, client_secret, refresh_token)
        
        # Find Zoom invitations
        invitations = gmail_client.find_zoom_invitations()
        
        if invitations:
            print(f"Found {len(invitations)} Zoom invitations:")
            for i, invitation in enumerate(invitations, 1):
                print(f"\nInvitation {i}:")
                print(f"  Subject: {invitation['subject']}")
                print(f"  From: {invitation['from']}")
                print(f"  URL: {invitation['url']}")
                print(f"  Meeting ID: {invitation['meeting_id']}")
                print(f"  Password: {invitation['password']}")
                print(f"  Scheduled Time: {invitation['scheduled_time']}")
                
                # Ask if the user wants to mark this message as read
                mark_read = input(f"\nMark invitation {i} as read? (y/n): ").lower() == 'y'
                if mark_read:
                    gmail_client.mark_as_read(invitation['message_id'])
        else:
            print("No Zoom invitations found.")
    
    except Exception as e:
        print(f"Error: {str(e)}")


if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    
    # Run the test
    test_gmail_api()
