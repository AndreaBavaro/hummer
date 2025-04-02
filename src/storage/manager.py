"""
Storage Manager for the Zoom Interview Analysis System.

This module handles storage of interview recordings, transcripts, and other data
in both local filesystem and AWS S3.
"""

import os
import logging
import shutil
import json
from datetime import datetime
from pathlib import Path

# Import boto3 for AWS S3 integration
try:
    import boto3
    from botocore.exceptions import ClientError
    BOTO3_AVAILABLE = True
except ImportError:
    BOTO3_AVAILABLE = False

logger = logging.getLogger(__name__)

class StorageManager:
    """Manages storage of interview data in local filesystem and AWS S3."""
    
    def __init__(self, config):
        """Initialize the storage manager.
        
        Args:
            config: Application configuration object
        """
        self.config = config
        self.local_storage_path = Path(config.local_storage_path)
        
        # Create local storage directory if it doesn't exist
        os.makedirs(self.local_storage_path, exist_ok=True)
        
        # Initialize S3 client if in cloud mode
        self.s3_client = None
        if config.storage_mode == "cloud":
            if not BOTO3_AVAILABLE:
                raise ImportError("boto3 is required for cloud storage mode")
            
            self.s3_client = boto3.client(
                's3',
                aws_access_key_id=config.aws_access_key_id,
                aws_secret_access_key=config.aws_secret_access_key,
                region_name=config.aws_region
            )
            logger.info(f"Initialized S3 client for bucket: {config.s3_bucket_name}")
    
    def store_interview_data(self, recording_path, transcript_path, candidate_name):
        """Store interview recording and transcript.
        
        Args:
            recording_path: Path to the recording file
            transcript_path: Path to the transcript file
            candidate_name: Name of the interview candidate
            
        Returns:
            dict: Storage information including paths and content
        """
        # Create a directory for this interview
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        sanitized_name = self._sanitize_filename(candidate_name)
        interview_dir = self.local_storage_path / f"{sanitized_name}_{timestamp}"
        os.makedirs(interview_dir, exist_ok=True)
        
        # Copy files to the interview directory
        recording_filename = os.path.basename(recording_path)
        transcript_filename = os.path.basename(transcript_path)
        
        local_recording_path = interview_dir / recording_filename
        local_transcript_path = interview_dir / transcript_filename
        
        shutil.copy2(recording_path, local_recording_path)
        shutil.copy2(transcript_path, local_transcript_path)
        
        logger.info(f"Copied recording to {local_recording_path}")
        logger.info(f"Copied transcript to {local_transcript_path}")
        
        # Read transcript content
        with open(local_transcript_path, 'r', encoding='utf-8') as f:
            transcript_content = f.read()
        
        # Create metadata file
        metadata = {
            "candidate_name": candidate_name,
            "timestamp": timestamp,
            "recording_file": recording_filename,
            "transcript_file": transcript_filename,
            "storage_mode": self.config.storage_mode
        }
        
        metadata_path = interview_dir / "metadata.json"
        with open(metadata_path, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=2)
        
        # Upload to S3 if in cloud mode
        s3_recording_path = None
        s3_transcript_path = None
        
        if self.config.storage_mode == "cloud" and self.s3_client:
            s3_prefix = f"interviews/{sanitized_name}_{timestamp}"
            
            # Upload recording
            s3_recording_key = f"{s3_prefix}/{recording_filename}"
            self.s3_client.upload_file(
                str(local_recording_path),
                self.config.s3_bucket_name,
                s3_recording_key
            )
            s3_recording_path = f"s3://{self.config.s3_bucket_name}/{s3_recording_key}"
            
            # Upload transcript
            s3_transcript_key = f"{s3_prefix}/{transcript_filename}"
            self.s3_client.upload_file(
                str(local_transcript_path),
                self.config.s3_bucket_name,
                s3_transcript_key
            )
            s3_transcript_path = f"s3://{self.config.s3_bucket_name}/{s3_transcript_key}"
            
            # Upload metadata
            s3_metadata_key = f"{s3_prefix}/metadata.json"
            self.s3_client.upload_file(
                str(metadata_path),
                self.config.s3_bucket_name,
                s3_metadata_key
            )
            
            logger.info(f"Uploaded recording to {s3_recording_path}")
            logger.info(f"Uploaded transcript to {s3_transcript_path}")
            
            # Update metadata with S3 paths
            metadata["s3_recording_path"] = s3_recording_path
            metadata["s3_transcript_path"] = s3_transcript_path
            
            with open(metadata_path, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, indent=2)
        
        # Return storage information
        return {
            "local_dir": str(interview_dir),
            "recording_path": str(local_recording_path),
            "transcript_path": str(local_transcript_path),
            "s3_recording_path": s3_recording_path,
            "s3_transcript_path": s3_transcript_path,
            "metadata_path": str(metadata_path),
            "transcript_content": transcript_content
        }
    
    def retrieve_interview_data(self, interview_id):
        """Retrieve interview data by ID.
        
        Args:
            interview_id: ID of the interview (directory name)
            
        Returns:
            dict: Interview data
        """
        interview_dir = self.local_storage_path / interview_id
        
        if not os.path.exists(interview_dir):
            raise FileNotFoundError(f"Interview directory not found: {interview_dir}")
        
        # Read metadata
        metadata_path = interview_dir / "metadata.json"
        with open(metadata_path, 'r', encoding='utf-8') as f:
            metadata = json.load(f)
        
        # Get file paths
        recording_path = interview_dir / metadata["recording_file"]
        transcript_path = interview_dir / metadata["transcript_file"]
        
        # Read transcript content
        with open(transcript_path, 'r', encoding='utf-8') as f:
            transcript_content = f.read()
        
        return {
            "metadata": metadata,
            "recording_path": str(recording_path),
            "transcript_path": str(transcript_path),
            "transcript_content": transcript_content
        }
    
    def list_interviews(self):
        """List all stored interviews.
        
        Returns:
            list: List of interview metadata
        """
        interviews = []
        
        for item in os.listdir(self.local_storage_path):
            item_path = self.local_storage_path / item
            
            if os.path.isdir(item_path):
                metadata_path = item_path / "metadata.json"
                
                if os.path.exists(metadata_path):
                    with open(metadata_path, 'r', encoding='utf-8') as f:
                        metadata = json.load(f)
                    
                    interviews.append({
                        "id": item,
                        "metadata": metadata
                    })
        
        return interviews
    
    def _sanitize_filename(self, filename):
        """Sanitize a filename to be safe for filesystem use.
        
        Args:
            filename: The filename to sanitize
            
        Returns:
            str: Sanitized filename
        """
        # Replace spaces with underscores and remove special characters
        sanitized = "".join(c if c.isalnum() or c in "_- " else "_" for c in filename)
        sanitized = sanitized.replace(" ", "_")
        return sanitized
