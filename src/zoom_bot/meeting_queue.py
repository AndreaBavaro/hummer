"""
Meeting Queue for the Zoom Interview Analysis System.

This module provides a priority queue for scheduled meetings.
"""

import logging
import heapq
import threading
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Callable

logger = logging.getLogger(__name__)

class MeetingQueue:
    """Priority queue for scheduled meetings with retry functionality."""
    
    def __init__(self, join_callback: Callable[[int, str], bool]):
        """Initialize the meeting queue.
        
        Args:
            join_callback: Callback function to join a meeting (meeting_id, url) -> success
        """
        self._queue = []  # Priority queue of (scheduled_time, meeting_id, url, retry_count)
        self._lock = threading.RLock()
        self._running = False
        self._thread = None
        self._join_callback = join_callback
        self._meetings = {}  # Dict of meeting_id -> (scheduled_time, url, retry_count, max_retries, is_urgent)
        self._urgent_retry_minutes = 3  # Retry every 3 minutes for urgent meetings
        self._normal_retry_minutes = 5  # Retry every 5 minutes for normal meetings
    
    def start(self):
        """Start the meeting queue processor."""
        if self._thread and self._thread.is_alive():
            logger.warning("Meeting queue is already running")
            return
        
        self._running = True
        self._thread = threading.Thread(target=self._process_queue, daemon=True)
        self._thread.start()
        logger.info("Started meeting queue processor")
    
    def stop(self):
        """Stop the meeting queue processor."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=10)
            logger.info("Stopped meeting queue processor")
    
    def schedule_meeting(self, meeting_id: int, url: str, scheduled_time: datetime, 
                         max_retries: int = 5) -> bool:
        """Schedule a meeting to be joined at the specified time.
        
        Args:
            meeting_id: Meeting ID in the database
            url: Meeting URL
            scheduled_time: When to join the meeting
            max_retries: Maximum number of retry attempts if joining fails
            
        Returns:
            True if scheduled successfully, False otherwise
        """
        with self._lock:
            # If meeting is already scheduled, update it
            if meeting_id in self._meetings:
                self._remove_meeting(meeting_id)
            
            # Check if the meeting time is in the past
            now = datetime.now()
            
            # Add a 1-minute delay after the scheduled start time
            # This ensures the host has time to start the meeting
            actual_join_time = scheduled_time + timedelta(minutes=1)
            
            if actual_join_time < now:
                logger.warning(f"Meeting {meeting_id} is scheduled in the past, joining immediately")
                return self._join_callback(meeting_id, url)
            
            # Check if the meeting is within the next 15 minutes
            is_urgent = (actual_join_time - now) <= timedelta(minutes=15)
            if is_urgent:
                logger.info(f"Meeting {meeting_id} is within 15 minutes, marking as urgent")
            
            # Add to meetings dict
            self._meetings[meeting_id] = (actual_join_time, url, 0, max_retries, is_urgent)
            
            # Add to priority queue
            heapq.heappush(self._queue, (actual_join_time, meeting_id, url, 0))
            
            logger.info(f"Scheduled meeting {meeting_id} at {scheduled_time} (will join at {actual_join_time}, 1 minute after scheduled start)")
            return True
    
    def reschedule_meeting(self, meeting_id: int, delay_minutes: int = None) -> bool:
        """Reschedule a meeting with a delay.
        
        Args:
            meeting_id: Meeting ID in the database
            delay_minutes: Delay in minutes before retrying (if None, uses urgent/normal retry times)
            
        Returns:
            True if rescheduled successfully, False otherwise
        """
        with self._lock:
            if meeting_id not in self._meetings:
                logger.warning(f"Cannot reschedule meeting {meeting_id}: not found")
                return False
            
            # Get meeting details
            scheduled_time, url, retry_count, max_retries, is_urgent = self._meetings[meeting_id]
            
            # Check if we've exceeded max retries
            if retry_count >= max_retries:
                logger.warning(f"Meeting {meeting_id} has exceeded maximum retry attempts ({max_retries})")
                return False
            
            # Determine delay based on urgency if not specified
            if delay_minutes is None:
                delay_minutes = self._urgent_retry_minutes if is_urgent else self._normal_retry_minutes
            
            # Calculate new scheduled time
            new_time = datetime.now() + timedelta(minutes=delay_minutes)
            new_retry_count = retry_count + 1
            
            # Update meetings dict
            self._meetings[meeting_id] = (new_time, url, new_retry_count, max_retries, is_urgent)
            
            # Add to priority queue
            heapq.heappush(self._queue, (new_time, meeting_id, url, new_retry_count))
            
            retry_type = "urgent" if is_urgent else "normal"
            logger.info(f"Rescheduled {retry_type} meeting {meeting_id} for {new_time} (retry {new_retry_count}/{max_retries})")
            return True
    
    def cancel_meeting(self, meeting_id: int) -> bool:
        """Cancel a scheduled meeting.
        
        Args:
            meeting_id: Meeting ID in the database
            
        Returns:
            True if cancelled successfully, False if meeting not found
        """
        with self._lock:
            if meeting_id not in self._meetings:
                return False
            
            self._remove_meeting(meeting_id)
            logger.info(f"Cancelled meeting {meeting_id}")
            return True
    
    def _remove_meeting(self, meeting_id: int):
        """Remove a meeting from the meetings dict.
        
        Note: This doesn't remove from the priority queue, but the entry will be ignored
        when processed.
        
        Args:
            meeting_id: Meeting ID to remove
        """
        if meeting_id in self._meetings:
            del self._meetings[meeting_id]
    
    def _process_queue(self):
        """Process the meeting queue continuously."""
        logger.info("Meeting queue processor started")
        
        while self._running:
            try:
                self._process_next_meeting()
                time.sleep(1)  # Check every second
            except Exception as e:
                logger.error(f"Error in meeting queue processor: {str(e)}")
                time.sleep(5)  # Wait a bit longer after an error
    
    def _process_next_meeting(self):
        """Process the next meeting in the queue if it's time."""
        with self._lock:
            # Check if queue is empty
            if not self._queue:
                return
            
            # Peek at the next meeting
            next_time, meeting_id, url, retry_count = self._queue[0]
            
            # Check if it's time to join
            now = datetime.now()
            if next_time <= now:
                # Pop the meeting from the queue
                heapq.heappop(self._queue)
                
                # Check if the meeting is still in the meetings dict
                if meeting_id not in self._meetings:
                    logger.info(f"Meeting {meeting_id} was cancelled, skipping")
                    return
                
                # Check if retry count matches what's in the meetings dict
                stored_time, stored_url, stored_retry_count, max_retries, is_urgent = self._meetings[meeting_id]
                
                if stored_retry_count != retry_count:
                    logger.info(f"Meeting {meeting_id} retry count mismatch, skipping")
                    return
                
                # Join the meeting
                self._join_meeting(meeting_id, stored_url, stored_retry_count, max_retries, is_urgent)
    
    def _join_meeting(self, meeting_id: int, url: str, retry_count: int, max_retries: int, is_urgent: bool):
        """Join a meeting and handle retries if needed.
        
        Args:
            meeting_id: Meeting ID in the database
            url: Meeting URL
            retry_count: Current retry count
            max_retries: Maximum number of retry attempts
            is_urgent: Whether this is an urgent meeting (within 15 minutes)
        """
        try:
            # Try to join the meeting
            success = self._join_callback(meeting_id, url)
            
            if success:
                # If successful, remove from meetings dict
                self._remove_meeting(meeting_id)
                logger.info(f"Successfully joined meeting {meeting_id}")
            else:
                # If failed, reschedule with appropriate delay
                delay = self._urgent_retry_minutes if is_urgent else self._normal_retry_minutes
                self.reschedule_meeting(meeting_id, delay)
                
        except Exception as e:
            logger.error(f"Error joining meeting {meeting_id}: {str(e)}")
            # Reschedule with appropriate delay
            delay = self._urgent_retry_minutes if is_urgent else self._normal_retry_minutes
            self.reschedule_meeting(meeting_id, delay)
            
    def check_for_urgent_meetings(self):
        """Check if any scheduled meetings have become urgent (within 15 minutes).
        
        This should be called periodically to update the urgency status of meetings.
        """
        with self._lock:
            now = datetime.now()
            urgent_window = timedelta(minutes=15)
            
            for meeting_id, (scheduled_time, url, retry_count, max_retries, is_urgent) in list(self._meetings.items()):
                # If not already urgent and now within 15 minutes
                if not is_urgent and (scheduled_time - now) <= urgent_window:
                    logger.info(f"Meeting {meeting_id} is now within 15 minutes, marking as urgent")
                    # Update to urgent status
                    self._meetings[meeting_id] = (scheduled_time, url, retry_count, max_retries, True)
