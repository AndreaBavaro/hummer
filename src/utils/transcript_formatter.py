"""
Transcript Formatter for the Zoom Interview Analysis System.

This module provides utilities for formatting raw transcript data into
human-readable formats with proper speaker identification.
"""

import os
import json
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

def format_timestamp(timestamp_ms):
    """Format a timestamp in milliseconds to a human-readable format.
    
    Args:
        timestamp_ms: Timestamp in milliseconds
        
    Returns:
        str: Formatted timestamp (HH:MM:SS)
    """
    if not timestamp_ms:
        return "00:00:00"
    
    # Convert milliseconds to seconds
    total_seconds = timestamp_ms / 1000
    
    # Calculate hours, minutes, seconds
    hours = int(total_seconds // 3600)
    minutes = int((total_seconds % 3600) // 60)
    seconds = int(total_seconds % 60)
    
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

def format_timestamp_relative(start_ms, current_ms):
    """Format a relative timestamp in minutes:seconds format.
    
    Args:
        start_ms: Start timestamp in milliseconds
        current_ms: Current timestamp in milliseconds
        
    Returns:
        str: Formatted timestamp (MM:SS)
    """
    if not start_ms or not current_ms:
        return "00:00"
    
    # Calculate relative time in seconds
    relative_seconds = (current_ms - start_ms) / 1000
    
    # Calculate minutes and seconds
    minutes = int(relative_seconds // 60)
    seconds = int(relative_seconds % 60)
    
    return f"{minutes:02d}:{seconds:02d}"

def extract_full_text(transcription):
    """Extract full text from a transcription object.
    
    Args:
        transcription: Transcription object from the raw transcript
        
    Returns:
        str: Full text of the transcription
    """
    if not transcription:
        return ""
    
    # Check if it's already a string
    if isinstance(transcription, str):
        return transcription
    
    # Check if transcript field is available directly
    if isinstance(transcription, dict) and "transcript" in transcription:
        return transcription["transcript"]
    
    # If it has paragraphs, extract text from the transcript field there
    if isinstance(transcription, dict) and "paragraphs" in transcription:
        if "transcript" in transcription["paragraphs"]:
            return transcription["paragraphs"]["transcript"]
        
        # Otherwise try to extract from sentences
        paragraphs = transcription.get("paragraphs", {}).get("paragraphs", [])
        if paragraphs:
            all_text = []
            for paragraph in paragraphs:
                sentences = paragraph.get("sentences", [])
                for sentence in sentences:
                    if "text" in sentence:
                        all_text.append(sentence["text"])
            return " ".join(all_text)
    
    # If it has words, reconstruct text from punctuated words
    if isinstance(transcription, dict) and "words" in transcription:
        words = transcription.get("words", [])
        if words:
            # First try to use punctuated_word if available
            text = ""
            for word in words:
                if "punctuated_word" in word:
                    text += word["punctuated_word"] + " "
                elif "word" in word:
                    text += word["word"] + " "
            
            # Remove extra spaces before punctuation
            text = text.replace(" .", ".").replace(" ,", ",").replace(" ?", "?").replace(" !", "!")
            return text.strip()
    
    return ""

def format_transcript(raw_transcript_path, output_path, format_type="conversation"):
    """Format a raw transcript into a human-readable format.
    
    Args:
        raw_transcript_path: Path to the raw transcript JSON file
        output_path: Path to save the formatted transcript
        format_type: Type of formatting to use (conversation, timestamped, or detailed)
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # Load raw transcript data
        with open(raw_transcript_path, 'r', encoding='utf-8') as f:
            transcript_data = json.load(f)
        
        # Get the first timestamp as the start time
        start_timestamp_ms = transcript_data[0]["timestamp_ms"] if transcript_data else 0
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(f"Interview Transcript\n")
            f.write(f"===================\n\n")
            
            current_speaker = None
            
            for entry in transcript_data:
                speaker = entry.get("speaker_name", "Unknown")
                timestamp_ms = entry.get("timestamp_ms", 0)
                duration_ms = entry.get("duration_ms", 0)
                
                # Extract text from transcription
                transcription = entry.get("transcription", {})
                text = extract_full_text(transcription)
                
                if not text:
                    continue
                
                # Format based on the requested type
                if format_type == "conversation":
                    # Format like a conversation with timestamps at speaker changes
                    if speaker != current_speaker:
                        timestamp = format_timestamp_relative(start_timestamp_ms, timestamp_ms)
                        f.write(f"{timestamp} | {speaker}\n")
                        current_speaker = speaker
                    
                    f.write(f"{text}\n\n")
                
                elif format_type == "timestamped":
                    # Format with timestamps for each entry
                    timestamp = format_timestamp_relative(start_timestamp_ms, timestamp_ms)
                    f.write(f"{timestamp} | {speaker}: {text}\n\n")
                
                elif format_type == "detailed":
                    # Format with absolute timestamps and duration
                    abs_timestamp = format_timestamp(timestamp_ms)
                    f.write(f"[{abs_timestamp}] {speaker}:\n")
                    f.write(f"{text}\n")
                    f.write(f"Duration: {duration_ms/1000:.2f}s\n\n")
        
        logger.info(f"Formatted transcript saved to {output_path}")
        return True
    
    except Exception as e:
        logger.exception(f"Error formatting transcript: {e}")
        return False
