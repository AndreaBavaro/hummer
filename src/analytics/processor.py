"""
Analytics Processor for the Zoom Interview Analysis System.

This module handles the processing of interview recordings using Hume AI
and generates insights using an LLM (Claude Sonnet 3.7).
"""

import os
import logging
import json
import time
import re
from pathlib import Path
import asyncio
import tempfile
import zipfile
import pandas as pd
import requests
from io import BytesIO

# Import Hume AI client
try:
    from hume import AsyncHumeClient
    from hume.expression_measurement.batch import Language, Prosody, Face, Models
    from hume.expression_measurement.batch.types import InferenceBaseRequest
    HUME_AVAILABLE = True
except ImportError:
    HUME_AVAILABLE = False

# Import Anthropic client for Claude
try:
    from anthropic import Anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False

logger = logging.getLogger(__name__)

class AnalyticsProcessor:
    """Processes interview recordings using Hume AI and generates insights using an LLM."""
    
    def __init__(self, config):
        """Initialize the analytics processor.
        
        Args:
            config: Application configuration object
        """
        self.config = config
        self.hume_client = None
        self.anthropic_client = None
        
        # Initialize Hume AI client if available
        if HUME_AVAILABLE and config.hume_api_key:
            self.hume_client = AsyncHumeClient(api_key=config.hume_api_key)
            logger.info("Initialized Hume AI client")
        else:
            logger.warning("Hume AI not available or API key not provided")
        
        # Initialize Anthropic client for Claude if available
        if ANTHROPIC_AVAILABLE and config.anthropic_api_key:
            self.anthropic_client = Anthropic(api_key=config.anthropic_api_key)
            logger.info("Initialized Anthropic client for Claude")
        else:
            logger.warning("Anthropic client not available or API key not provided")

    async def process_recording(self, recording_path, transcript_path=None):
        """Process an interview recording using Hume AI Expression Measurement API.
        
        Args:
            recording_path: Path to the recording file
            transcript_path: Path to the transcript file (optional)
            
        Returns:
            dict: Analytics data from Hume AI
        """
        logger.info(f"Processing recording: {recording_path}")
        
        if not self.hume_client:
            logger.warning("Hume AI client not available, skipping processing")
            return {}
        
        try:
            # Create configurations for each model
            language_config = Language()
            prosody_config = Prosody()
            face_config = Face()
            
            # Create a Models object
            models_chosen = Models(
                language=language_config,
                prosody=prosody_config,
                face=face_config
            )
            
            # Open the recording file
            with open(recording_path, mode="rb") as file:
                # Create a stringified object containing the configuration
                stringified_configs = InferenceBaseRequest(models=models_chosen)
                
                # Start an inference job
                logger.info(f"Starting Hume AI inference job for: {recording_path}")
                job_id = await self.hume_client.expression_measurement.batch.start_inference_job_from_local_file(
                    json=stringified_configs, 
                    file=[file]
                )
                
                logger.info(f"Submitted job to Hume AI: {job_id}")
                
                # Wait for job to complete (not recommended to poll, but we need the results)
                # In production, we should use webhooks
                job_complete = False
                max_retries = 30  # Maximum number of retries
                retry_count = 0
                
                while not job_complete and retry_count < max_retries:
                    try:
                        # Get job details
                        job_details = await self.hume_client.expression_measurement.batch.get_job_details(id=job_id)
                        
                        # Check job status - the structure depends on the actual API response
                        if hasattr(job_details, "state") and hasattr(job_details.state, "status"):
                            status = job_details.state.status
                        elif hasattr(job_details, "status"):
                            status = job_details.status
                        elif isinstance(job_details, dict):
                            status = job_details.get("status")
                        else:
                            # Log the actual structure for debugging
                            logger.info(f"Job details type: {type(job_details)}")
                            logger.info(f"Job details: {job_details}")
                            status = str(job_details)
                        
                        logger.info(f"Job status: {status}")
                        
                        if status == "COMPLETED":
                            job_complete = True
                        elif status == "FAILED":
                            raise Exception(f"Hume AI job failed: {job_details}")
                        else:
                            # Wait before checking again
                            retry_count += 1
                            logger.info(f"Job in progress, waiting... (attempt {retry_count}/{max_retries})")
                            await asyncio.sleep(10)  # Wait 10 seconds before checking again
                    except Exception as e:
                        logger.exception(f"Error checking job status: {e}")
                        retry_count += 1
                        await asyncio.sleep(10)  # Wait 10 seconds before trying again
                
                if not job_complete:
                    raise Exception(f"Hume AI job timed out after {max_retries} retries")
                
                # Get the output directory (same as where the recording is stored)
                output_dir = os.path.dirname(recording_path)
                
                # Create artifacts directory inside the meeting directory
                artifacts_dir = os.path.join(output_dir, "hume_artifacts")
                os.makedirs(artifacts_dir, exist_ok=True)
                
                # Download job artifacts (ZIP file with CSVs)
                logger.info(f"Downloading artifacts for job: {job_id}")
                
                # Direct API call to get artifacts (ZIP file)
                api_key = self.config.hume_api_key
                artifacts_url = f"https://api.hume.ai/v0/batch/jobs/{job_id}/artifacts"
                
                headers = {
                    "X-Hume-Api-Key": api_key
                }
                
                try:
                    artifacts_response = requests.get(artifacts_url, headers=headers)
                    artifacts_response.raise_for_status()
                    
                    # Save the zip file
                    zip_path = os.path.join(artifacts_dir, "artifacts.zip")
                    with open(zip_path, 'wb') as f:
                        f.write(artifacts_response.content)
                    
                    logger.info(f"Downloaded artifacts to: {zip_path}")
                    
                    # Extract the zip file
                    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                        zip_ref.extractall(artifacts_dir)
                    
                    logger.info(f"Extracted artifacts to: {artifacts_dir}")
                    
                    # Process each CSV file and combine data
                    combined_data = self._process_artifact_csvs(artifacts_dir, metadata={"transcript_path": transcript_path})
                    
                    # Save combined data to JSON in the same directory as the recording
                    combined_path = os.path.join(output_dir, "hume_analysis.json")
                    with open(combined_path, 'w', encoding='utf-8') as f:
                        json.dump(combined_data, f, indent=2)
                    
                    logger.info(f"Saved combined Hume AI analysis to {combined_path}")
                    
                    # Also get the predictions for backward compatibility
                    result = await self.hume_client.expression_measurement.batch.get_job_predictions(id=job_id)
                    
                    # Convert to serializable format if needed
                    if hasattr(result, "model_dump"):
                        result_dict = result.model_dump()
                    elif hasattr(result, "dict"):
                        result_dict = result.dict()
                    elif not isinstance(result, dict):
                        # Try to convert to dict using __dict__ if available
                        if hasattr(result, "__dict__"):
                            result_dict = result.__dict__
                        else:
                            # Fallback to string representation
                            result_dict = {"raw_result": str(result)}
                    else:
                        result_dict = result
                    
                    # Save predictions to file
                    predictions_path = os.path.join(output_dir, "hume_predictions.json")
                    with open(predictions_path, 'w', encoding='utf-8') as f:
                        json.dump(result_dict, f, indent=2)
                    
                    logger.info(f"Saved Hume AI predictions to {predictions_path}")
                    
                    # Merge predictions with combined data
                    combined_data["predictions"] = result_dict
                    
                    return {
                        "result": combined_data,
                        "result_path": combined_path,
                        "artifacts_dir": artifacts_dir
                    }
                    
                except Exception as e:
                    logger.exception(f"Error downloading or processing artifacts: {e}")
                    # Fall back to just getting predictions
                    logger.info("Falling back to getting predictions only")
                    result = await self.hume_client.expression_measurement.batch.get_job_predictions(id=job_id)
                    
                    # Convert to serializable format if needed
                    if hasattr(result, "model_dump"):
                        result_dict = result.model_dump()
                    elif hasattr(result, "dict"):
                        result_dict = result.dict()
                    elif not isinstance(result, dict):
                        # Try to convert to dict using __dict__ if available
                        if hasattr(result, "__dict__"):
                            result_dict = result.__dict__
                        else:
                            # Fallback to string representation
                            result_dict = {"raw_result": str(result)}
                    else:
                        result_dict = result
                    
                    # Save result to file
                    result_path = os.path.join(output_dir, "hume_analysis.json")
                    with open(result_path, 'w', encoding='utf-8') as f:
                        json.dump(result_dict, f, indent=2)
                    
                    logger.info(f"Saved Hume AI analysis to {result_path}")
                    
                    return {
                        "result": result_dict,
                        "result_path": result_path
                    }
                
        except Exception as e:
            logger.exception(f"Error processing recording with Hume AI: {e}")
            # Create a mock result for testing purposes
            mock_result = self._create_mock_hume_result()
            result_path = os.path.join(os.path.dirname(recording_path), "hume_analysis_mock.json")
            with open(result_path, 'w', encoding='utf-8') as f:
                json.dump(mock_result, f, indent=2)
            
            logger.info(f"Saved mock Hume AI analysis to {result_path}")
            
            return {
                "result": mock_result,
                "result_path": result_path
            }
    
    def _process_artifact_csvs(self, artifact_dir, metadata=None):
        """Process CSV files from the artifacts directory.
        
        Args:
            artifact_dir: Directory containing the artifacts
            metadata: Meeting metadata (optional)
            
        Returns:
            dict: Combined data from all CSV files
        """
        try:
            # Find all CSV files in the artifacts directory
            csv_files = []
            for root, _, files in os.walk(artifact_dir):
                for file in files:
                    if file.endswith(".csv"):
                        csv_files.append(os.path.join(root, file))
            
            # Initialize combined data structure
            combined_data = {
                "metadata": metadata or {},
                "face": {},
                "prosody": {},
                "language": {},
                "summary": {},
                "user_response_analysis": {}
            }
            
            logger.info(f"Found {len(csv_files)} CSV files")
            
            # Process each CSV file
            for csv_file in csv_files:
                file_name = os.path.basename(csv_file)
                logger.info(f"Processing CSV file: {file_name}")
                
                try:
                    # Read CSV file
                    df = pd.read_csv(csv_file)
                    
                    # Determine which model this CSV belongs to
                    if "face" in file_name.lower():
                        model_type = "face"
                    elif "prosody" in file_name.lower():
                        model_type = "prosody"
                    elif "language" in file_name.lower():
                        model_type = "language"
                    else:
                        model_type = "other"
                    
                    # Extract key information based on model type
                    if model_type == "face":
                        # Process face data
                        if "frame" in df.columns and "emotion" in df.columns and "score" in df.columns:
                            # Group by emotion and calculate average score
                            emotion_scores = df.groupby("emotion")["score"].mean().to_dict()
                            # Get top emotions
                            top_emotions = sorted(emotion_scores.items(), key=lambda x: x[1], reverse=True)
                            
                            combined_data["face"]["emotion_scores"] = emotion_scores
                            combined_data["face"]["top_emotions"] = top_emotions[:5]  # Top 5 emotions
                            
                            # Add time series data
                            if "time" in df.columns:
                                time_series = {}
                                for emotion in df["emotion"].unique():
                                    emotion_df = df[df["emotion"] == emotion]
                                    time_series[emotion] = list(zip(emotion_df["time"].tolist(), emotion_df["score"].tolist()))
                                combined_data["face"]["time_series"] = time_series
                    
                    elif model_type == "prosody":
                        # Process prosody data
                        if "time" in df.columns and "emotion" in df.columns and "score" in df.columns:
                            # Group by emotion and calculate average score
                            emotion_scores = df.groupby("emotion")["score"].mean().to_dict()
                            # Get top emotions
                            top_emotions = sorted(emotion_scores.items(), key=lambda x: x[1], reverse=True)
                            
                            combined_data["prosody"]["emotion_scores"] = emotion_scores
                            combined_data["prosody"]["top_emotions"] = top_emotions[:5]  # Top 5 emotions
                            
                            # Add time series data
                            time_series = {}
                            for emotion in df["emotion"].unique():
                                emotion_df = df[df["emotion"] == emotion]
                                time_series[emotion] = list(zip(emotion_df["time"].tolist(), emotion_df["score"].tolist()))
                            combined_data["prosody"]["time_series"] = time_series
                    
                    elif model_type == "language":
                        # Process language data
                        if "text" in df.columns and "emotion" in df.columns and "score" in df.columns:
                            # Group by emotion and calculate average score
                            emotion_scores = df.groupby("emotion")["score"].mean().to_dict()
                            # Get top emotions
                            top_emotions = sorted(emotion_scores.items(), key=lambda x: x[1], reverse=True)
                            
                            combined_data["language"]["emotion_scores"] = emotion_scores
                            combined_data["language"]["top_emotions"] = top_emotions[:5]  # Top 5 emotions
                            
                            # Add text segments with emotions
                            text_segments = []
                            for _, row in df.iterrows():
                                if "text" in row and "emotion" in row and "score" in row:
                                    text_segments.append({
                                        "text": row["text"],
                                        "emotion": row["emotion"],
                                        "score": row["score"]
                                    })
                            combined_data["language"]["text_segments"] = text_segments
                    
                    # Save the raw data as well
                    combined_data[model_type][file_name] = df.to_dict(orient="records")
                    
                except Exception as e:
                    logger.exception(f"Error processing CSV file {file_name}: {e}")
            
            # Generate summary across all models
            self._generate_summary(combined_data)
            
            # If transcript path is available in metadata, analyze user responses
            if metadata and "transcript_path" in metadata and os.path.exists(metadata["transcript_path"]):
                user_response_analysis = self.analyze_user_responses(combined_data, metadata["transcript_path"])
                combined_data["user_response_analysis"] = user_response_analysis
            
            return combined_data
            
        except Exception as e:
            logger.exception(f"Error processing artifact CSVs: {e}")
            return {"error": str(e)}
    
    def _generate_summary(self, combined_data):
        """Generate a summary of the combined data.
        
        Args:
            combined_data: Combined data from all CSV files
        """
        summary = {}
        
        try:
            # Collect all emotions across models
            all_emotions = set()
            for model in ["face", "prosody", "language"]:
                if model in combined_data and "emotion_scores" in combined_data[model]:
                    all_emotions.update(combined_data[model]["emotion_scores"].keys())
            
            # Calculate average score for each emotion across models
            emotion_scores = {}
            for emotion in all_emotions:
                scores = []
                for model in ["face", "prosody", "language"]:
                    if model in combined_data and "emotion_scores" in combined_data[model]:
                        if emotion in combined_data[model]["emotion_scores"]:
                            scores.append(combined_data[model]["emotion_scores"][emotion])
                
                if scores:
                    emotion_scores[emotion] = sum(scores) / len(scores)
            
            # Get top emotions
            top_emotions = sorted(emotion_scores.items(), key=lambda x: x[1], reverse=True)
            
            summary["emotion_scores"] = emotion_scores
            summary["top_emotions"] = top_emotions[:5]  # Top 5 emotions
            
            # Add model-specific summaries
            model_summaries = {}
            for model in ["face", "prosody", "language"]:
                if model in combined_data and "top_emotions" in combined_data[model]:
                    model_summaries[model] = {
                        "top_emotions": combined_data[model]["top_emotions"]
                    }
            
            summary["model_summaries"] = model_summaries
            
            # Add to combined data
            combined_data["summary"] = summary
            
            # Extract emotion frames from raw result if available
            if "raw_result" in combined_data:
                emotion_frames = self._extract_emotion_frames_from_raw(combined_data)
                if emotion_frames:
                    combined_data["emotion_frames"] = emotion_frames
            
        except Exception as e:
            logger.exception(f"Error generating summary: {e}")
            combined_data["summary"] = {"error": str(e)}
    
    def _extract_emotion_frames_from_raw(self, hume_data):
        """Extract emotion frames from the raw_result string.
        
        Args:
            hume_data: Hume AI analysis data
            
        Returns:
            list: List of emotion frames
        """
        try:
            # First check if the raw_result is directly in hume_data
            raw = hume_data.get("raw_result", "")
            
            # If not, check if it's nested under 'result'
            if not raw and "result" in hume_data:
                raw = hume_data.get("result", {}).get("raw_result", "")
            
            if not raw:
                logger.warning("No raw_result field found in Hume data.")
                return []
            
            # Pattern to capture FacePrediction blocks with time and emotions
            pattern = r"FacePrediction\(frame=\d+,\s*time=([0-9.]+).*?emotions=\[(.*?)\]"
            matches = re.findall(pattern, raw, re.DOTALL)
            
            frames = []
            for time_str, emotions_str in matches:
                try:
                    time_val = float(time_str)
                except ValueError:
                    continue

                # Pattern to capture individual emotion entries
                emotion_pattern = r"EmotionScore\(name=['\"]([^'\"]+)['\"],\s*score=([0-9.]+)"
                emotion_matches = re.findall(emotion_pattern, emotions_str)
                
                emotions = []
                for name, score_str in emotion_matches:
                    try:
                        score_val = float(score_str)
                    except ValueError:
                        score_val = 0.0
                    emotions.append({"name": name, "score": score_val})
                
                if emotions:  # Only add frames that have emotion data
                    frames.append({"time": time_val, "emotions": emotions})
            
            logger.info(f"Extracted {len(frames)} frames with emotion data")
            return frames
            
        except Exception as e:
            logger.exception(f"Error extracting emotion frames: {e}")
            return []
    
    def _process_transcript_with_emotions(self, transcript_path, emotion_frames):
        """Process transcript and map emotion data to transcript segments.
        
        Args:
            transcript_path: Path to the transcript file
            emotion_frames: List of emotion frames extracted from Hume data
            
        Returns:
            list: List of transcript segments with emotion data
        """
        try:
            # Load transcript data
            with open(transcript_path, 'r', encoding='utf-8') as f:
                transcript_data = json.load(f)
            
            # Determine a baseline timestamp from the transcript data (in seconds)
            if transcript_data:
                baseline = min(segment.get("timestamp_ms", 0) for segment in transcript_data) / 1000.0
            else:
                baseline = 0
            
            insights = []
            for segment in transcript_data:
                # Convert transcript timestamps from milliseconds to seconds and make them relative to the baseline
                seg_start = (segment.get("timestamp_ms", 0) / 1000.0) - baseline
                seg_duration = segment.get("duration_ms", 0) / 1000.0
                seg_end = seg_start + seg_duration
                
                # Compute average emotion scores for frames within the segment window
                avg_emotions = self._average_emotions_for_segment(emotion_frames, seg_start, seg_end)
                insights.append({
                    "transcript": segment.get("transcription", {}).get("transcript", ""),
                    "start": seg_start,
                    "end": seg_end,
                    "avg_emotions": avg_emotions
                })
            
            return insights
            
        except Exception as e:
            logger.exception(f"Error processing transcript with emotions: {e}")
            return []
    
    def _average_emotions_for_segment(self, frames, start_time, end_time):
        """Calculate average emotion scores for frames within a time window.
        
        Args:
            frames: List of emotion frames
            start_time: Start time of the segment (in seconds)
            end_time: End time of the segment (in seconds)
            
        Returns:
            dict: Average emotion scores for the segment
        """
        # Filter frames that fall within the provided time window
        selected = [frame for frame in frames if start_time <= frame.get("time", 0) <= end_time]
        if not selected:
            return {}
        
        emotion_totals = {}
        count = 0
        for frame in selected:
            for emotion in frame.get("emotions", []):
                name = emotion.get("name")
                score = emotion.get("score", 0)
                emotion_totals[name] = emotion_totals.get(name, 0) + score
            count += 1
        
        avg_emotions = {name: total / count for name, total in emotion_totals.items()}
        return avg_emotions

    async def generate_insights(self, analytics_data, transcript_path=None, candidate_name="Candidate"):
        """Generate insights from Hume AI analytics data using Claude.
        
        Args:
            analytics_data: Analytics data from Hume AI
            transcript_path: Path to the transcript file (optional)
            candidate_name: Name of the interview candidate
            
        Returns:
            dict: Insights and emotional data
        """
        logger.info(f"Generating insights for {candidate_name}")
        
        if not self.anthropic_client:
            logger.warning("Claude not available, skipping insights generation")
            return {}
        
        # Load transcript if path provided
        transcript = ""
        if transcript_path and os.path.exists(transcript_path):
            with open(transcript_path, 'r', encoding='utf-8') as f:
                transcript = f.read()
        
        # Extract emotion data from analytics
        transcript_with_emotions = self._extract_emotion_data(analytics_data)
        
        # Step 1: Generate primary insights using Claude 3.7 Sonnet
        primary_insights = await self._generate_primary_insights(transcript_with_emotions, transcript, candidate_name)
        
        # Step 2: Generate emotional analysis using Claude 3.7 Sonnet
        emotional_analysis = await self._generate_emotional_analysis(transcript_with_emotions, transcript, candidate_name)
        
        # Step 3: Combine insights into a comprehensive package
        combined_insights = self._combine_insights(primary_insights, emotional_analysis)
        
        # Return combined insights and emotional data for the PDF generator
        return {
            "insights": combined_insights,
            "emotion_data": transcript_with_emotions,
            "filtered_qa_pairs": self._filter_relevant_questions(transcript_with_emotions, transcript)
        }
    
    def _combine_insights(self, primary_insights, emotional_analysis):
        """Combine primary insights and emotional analysis into a comprehensive package.
        
        Args:
            primary_insights: Insights from Claude 3.7 Sonnet
            emotional_analysis: Emotional analysis from Claude 3.7 Sonnet
            
        Returns:
            dict: Combined insights
        """
        logger.info("Combining primary insights and emotional analysis")
        
        # Start with primary insights
        combined = primary_insights.copy() if primary_insights else {}
        
        # Add emotional analysis
        if emotional_analysis:
            # Add emotional_response_analysis if not already present
            if "emotional_response_analysis" not in combined and "emotional_response_analysis" in emotional_analysis:
                combined["emotional_response_analysis"] = emotional_analysis["emotional_response_analysis"]
            
            # Add question_specific_insights if available
            if "question_specific_insights" in emotional_analysis:
                combined["question_specific_insights"] = emotional_analysis["question_specific_insights"]
            
            # Merge strengths
            if "strengths" in emotional_analysis:
                if "strengths" not in combined:
                    combined["strengths"] = []
                
                # Add unique strengths from emotional analysis
                for strength in emotional_analysis.get("strengths", []):
                    if strength not in combined["strengths"]:
                        combined["strengths"].append(strength)
            
            # Merge development areas
            if "development_areas" in emotional_analysis:
                if "development_areas" not in combined:
                    combined["development_areas"] = []
                
                # Add unique development areas from emotional analysis
                for area in emotional_analysis.get("development_areas", []):
                    if area not in combined["development_areas"]:
                        combined["development_areas"].append(area)
            
            # Add word_emotion_correlations if available
            if "word_emotion_correlations" in emotional_analysis:
                combined["word_emotion_correlations"] = emotional_analysis["word_emotion_correlations"]
        
        return combined
    
    def _extract_emotion_data(self, analytics_data):
        """Extract emotion data from analytics.
        
        Args:
            analytics_data: Analytics data from Hume AI
            
        Returns:
            list: List of transcript segments with emotion data
        """
        # Extract emotion frames from analytics data
        emotion_frames = []
        if "emotion_frames" in analytics_data:
            emotion_frames = analytics_data["emotion_frames"]
        else:
            emotion_frames = self._extract_emotion_frames_from_raw(analytics_data)
        
        # Process transcript with emotions if raw transcript is available
        transcript_raw_path = os.path.join(os.path.dirname(analytics_data["result_path"]), "transcript_raw.json")
        transcript_with_emotions = []
        if os.path.exists(transcript_raw_path) and emotion_frames:
            transcript_with_emotions = self._process_transcript_with_emotions(transcript_raw_path, emotion_frames)
        
        return transcript_with_emotions
    
    def _filter_relevant_questions(self, transcript_with_emotions, full_transcript):
        """
        Filter out irrelevant questions and identify question-answer pairs.
        
        Args:
            transcript_with_emotions: List of transcript segments with emotion data
            full_transcript: Complete interview transcript text
            
        Returns:
            list: List of relevant question-answer pairs with emotional data
        """
        logger.info("Filtering relevant interview questions")
        
        # Extract lines from the full transcript
        transcript_lines = full_transcript.split('\n')
        
        # Identify potential questions (lines ending with question marks or containing question indicators)
        questions = []
        for i, line in enumerate(transcript_lines):
            if '|' not in line:
                continue
                
            # Extract speaker and text
            parts = line.split('|', 1)
            if len(parts) < 2:
                continue
                
            speaker = parts[1].strip().split('\n')[0]
            text = parts[1].strip()
            
            # Skip if the speaker is the candidate
            if "Daniel Kraft" in speaker:
                continue
                
            # Check if this is likely a question
            is_question = ('?' in text or 
                          any(q in text.lower() for q in [
                              "tell me about", "what is", "how would", "describe", 
                              "explain", "can you", "do you", "have you"
                          ]))
            
            if is_question:
                # Find the timestamp
                timestamp = parts[0].strip() if parts[0].strip() else "00:00"
                
                # Convert timestamp to seconds
                try:
                    minutes, seconds = timestamp.split(':')
                    time_seconds = int(minutes) * 60 + int(seconds)
                except:
                    time_seconds = 0
                
                questions.append({
                    "timestamp": timestamp,
                    "time_seconds": time_seconds,
                    "text": text,
                    "index": i
                })
        
        # Filter out irrelevant questions (small talk, name queries, etc.)
        irrelevant_patterns = [
            "how are you", "nice to meet", "your name", "introduce yourself",
            "weather", "doing today", "go for it", "pan", "testing", "hear me",
            "can you see", "technical", "connection"
        ]
        
        relevant_questions = []
        for q in questions:
            if not any(pattern in q["text"].lower() for pattern in irrelevant_patterns):
                relevant_questions.append(q)
        
        # Match questions with candidate responses in the transcript_with_emotions
        qa_pairs = []
        for i, question in enumerate(relevant_questions):
            # Determine the time range for the answer
            start_time = question["time_seconds"]
            end_time = relevant_questions[i+1]["time_seconds"] if i < len(relevant_questions) - 1 else float('inf')
            
            # Find the response segments that fall within this time range
            response_segments = []
            for segment in transcript_with_emotions:
                seg_start = segment["start"]
                # Convert to seconds if it's not already
                if isinstance(seg_start, float) and seg_start < 1000:  # Likely already in seconds
                    pass
                elif isinstance(seg_start, (int, float)):  # Likely in milliseconds
                    seg_start = seg_start / 1000.0
                
                # Check if this segment falls within the expected response time range
                if start_time <= seg_start and seg_start < end_time:
                    response_segments.append(segment)
            
            # If we found response segments, add this as a Q&A pair
            if response_segments:
                # Find the segment with the strongest emotional response
                strongest_segment = max(response_segments, 
                                       key=lambda s: max(s.get("avg_emotions", {}).values()) if s.get("avg_emotions") else 0)
                
                qa_pairs.append({
                    "question": question["text"],
                    "question_timestamp": question["timestamp"],
                    "response": strongest_segment,
                    "all_response_segments": response_segments
                })
        
        logger.info(f"Identified {len(qa_pairs)} relevant question-answer pairs")
        return qa_pairs
    
    async def _generate_primary_insights(self, analytics_data, transcript, candidate_name):
        """Generate primary insights using Claude 3.7 Sonnet.
        
        Args:
            analytics_data: Analytics data from Hume AI
            transcript: Interview transcript
            candidate_name: Name of the interview candidate
            
        Returns:
            dict: Primary insights
        """
        logger.info("Generating primary insights using Claude 3.7 Sonnet")
        
        # Create system prompt with clear instructions
        system_prompt = """
You are an expert interview analyst with deep knowledge of:
- Human behavior and emotional intelligence
- Communication patterns and linguistic analysis
- Technical skills assessment
- Sales and business development roles and competencies

Your objective is to:
1. Analyze interview transcripts to provide comprehensive insights.
2. Provide detailed analysis of communication style and question-answer quality.
3. Help hiring managers make informed decisions by addressing strengths, weaknesses, red flags, and overall fit.
4. Cite concrete evidence from the transcript to support your conclusions.
5. ONLY comment on topics that were actually discussed in the interview.
6. NEVER speculate about skills or knowledge not directly addressed in the interview questions.
7. If a particular skill or competency was not discussed, do not include it in strengths or development areas.

Structure your response as a JSON object with the following sections:
- executive_summary: A concise overview of the candidate's performance
- communication_style: Analysis of language patterns, clarity, and effectiveness
- content_quality: Evaluation of the substance and relevance of responses
- strengths: Array of specific strengths demonstrated (ONLY based on topics actually discussed)
- development_areas: Array of areas needing improvement (ONLY based on topics actually discussed)
- cultural_fit: Assessment of alignment with organizational culture
- followup_questions: Suggested questions for further evaluation
- recommendation: Clear hiring recommendation with rationale
"""
        
        # Create user prompt for primary insights
        user_prompt = f"""
Below is an interview transcript. Please analyze it following the guidelines above and provide actionable insights:

## Candidate Information
- Name: {candidate_name}
- Position: Account Executive (Sales role)

## Interview Transcript
```
{transcript[:10000]}  # Limit transcript length for prompt
```

## Hume AI Analytics Data
```json
{json.dumps(analytics_data, indent=2)}
```

## Task
Based on the interview transcript and Hume AI analytics data provided above, please analyze this interview and provide a comprehensive assessment of the candidate. Your analysis should include:

1. **Question and Answer Analysis**:
   - For each question asked in the interview, analyze how the candidate responded
   - Assess whether the candidate answered confidently and correctly
   - Identify instances where the candidate may have avoided directly answering a question
   - Correlate the candidate's emotional state with their responses

2. **Speech Pattern Analysis**:
   - Analyze the candidate's diction and vocabulary
   - Identify repeated words, phrases, or filler words (um, uh, like, etc.)
   - Assess the clarity and coherence of their speech

3. **Emotional Intelligence Assessment**:
   - Analysis of the candidate's emotional patterns during the interview
   - Key emotional strengths and areas for improvement
   - How emotions influenced their communication
   - Identify any emotional shifts when discussing specific topics

4. **Emotional Response Analysis**:
   - Analyze how the candidate's emotions changed throughout the interview
   - Identify which questions or topics triggered strong emotional responses
   - Assess how well the candidate regulated their emotions during challenging questions

5. **Structured Q&A Transcript**:
   - Generate a clean transcript that clearly shows questions and answers
   - Format it in a way that makes it easy to follow the conversation flow
   - Include timestamps at the beginning of each speaker's turn

6. **Candidate Strengths**: 3-5 key strengths with specific examples from the interview
   - IMPORTANT: Only include strengths that are directly evidenced in the interview transcript
   - Do NOT speculate about skills that weren't demonstrated or discussed

7. **Areas for Development**: 3-5 areas where the candidate could improve with specific examples
   - IMPORTANT: Only include development areas related to topics actually discussed in the interview
   - Do NOT mention skills gaps for topics that weren't addressed in the interview questions

8. **Final Recommendation**: Clear hiring recommendation (Strongly Recommend, Recommend, Neutral, Do Not Recommend) with justification

Please structure your response in a clear, organized format that would be helpful for hiring managers and HR professionals. Support your assessments with specific examples from the transcript and analytics data.

Format your response as a structured JSON object with the following keys:
- question_answer_analysis
- speech_pattern_analysis
- emotional_intelligence
- emotional_response_analysis
- qa_transcript
- strengths (array)
- development_areas (array)
- recommendation
"""
        
        # Call Claude 3.7 Sonnet API
        response = self.anthropic_client.messages.create(
            model="claude-3-7-sonnet-20240229",
            max_tokens=4000,
            temperature=0.2,
            system=system_prompt.strip(),
            messages=[
                {"role": "user", "content": user_prompt.strip()}
            ]
        )
        
        # Get insights text from Claude's response
        insights_text = response.content[0].text
        
        # Parse structured insights
        return self._parse_insights(insights_text)
    
    async def _generate_emotional_analysis(self, transcript_with_emotions, transcript, candidate_name):
        """Generate emotional analysis using Claude 3.7 Sonnet.
        
        Args:
            transcript_with_emotions: List of transcript segments with emotion data
            transcript: Interview transcript
            candidate_name: Name of the interview candidate
            
        Returns:
            dict: Emotional analysis insights
        """
        logger.info("Generating emotional analysis using Claude 3.7 Sonnet")
        
        if not transcript_with_emotions:
            logger.warning("No transcript with emotions available, skipping emotional analysis")
            return {}
        
        # Step 1: Filter relevant questions and responses
        relevant_qa_pairs = self._filter_relevant_questions(transcript_with_emotions, transcript)
        
        # Step 2: Analyze emotional responses tied to specific words
        word_emotion_analysis = self._analyze_word_emotions(relevant_qa_pairs)
        
        # Prepare emotion data for the user prompt
        emotion_analysis = ""
        if relevant_qa_pairs:
            emotion_analysis = "## Key Interview Questions and Emotional Responses\n\n"
            for i, qa_pair in enumerate(relevant_qa_pairs):
                emotion_analysis += f"### Question {i+1}: {qa_pair['question']}\n"
                emotion_analysis += f"**Candidate Response:** {qa_pair['response']['transcript']}\n\n"
                emotion_analysis += "**Emotions:**\n"
                
                if qa_pair['response']['avg_emotions']:
                    # Sort emotions by score (highest first) and show top 8
                    top_emotions = sorted(qa_pair['response']['avg_emotions'].items(), key=lambda x: x[1], reverse=True)[:8]
                    for emotion, score in top_emotions:
                        emotion_analysis += f"- {emotion}: {score:.2f}\n"
                else:
                    emotion_analysis += "- No emotion data available for this response.\n"
                
                if 'key_phrases' in qa_pair and qa_pair['key_phrases']:
                    emotion_analysis += "\n**Key Phrases and Associated Emotions:**\n"
                    for phrase, emotions in qa_pair['key_phrases'].items():
                        emotion_analysis += f"- \"{phrase}\": {', '.join([f'{e}: {s:.2f}' for e, s in emotions[:3]])}\n"
                
                emotion_analysis += "\n"
        
        # Create system prompt for emotional analysis
        system_prompt = """You are an expert in analyzing emotional patterns in interview contexts.
Your task is to:
1. Analyze the emotional data from interview questions and responses
2. Identify which specific words or phrases correlate with higher or lower emotional scores
3. Interpret what these emotions reveal about the candidate's comfort, confidence, and stress levels
4. Focus only on meaningful patterns that provide genuine insight (ignore trivial correlations)
5. ONLY comment on topics that were actually discussed in the interview
6. NEVER speculate about skills or knowledge not directly addressed in the interview questions

For each question and response:
1. Identify the emotional state of the candidate when answering
2. Determine which specific words or phrases triggered emotional shifts
3. Explain what this reveals about the candidate's relationship to the topic

Structure your analysis in JSON format with these fields:
- emotional_response_analysis: Detailed interpretation of emotional patterns throughout the interview
- question_specific_insights: Array of objects with question-specific emotional analysis
- strengths: Array of strengths revealed by emotional patterns (ONLY based on topics actually discussed)
- development_areas: Array of development areas revealed by emotional patterns (ONLY based on topics actually discussed)
"""

        # Create user prompt for emotional analysis
        user_prompt = f"""
## Candidate Information
- Name: {candidate_name}
- Position: Account Executive (Sales role)

## Interview Transcript
```
{transcript[:10000]}  # Limit transcript length for prompt
```

## Emotional Analysis Data
The following data shows the candidate's emotional responses to specific interview questions:

{emotion_analysis}

## Word-Emotion Correlations
```json
{json.dumps(word_emotion_analysis, indent=2)}
```

## Task
Based on the emotional data provided above, please analyze the candidate's emotional patterns during the interview. Your analysis should include:

1. **Overall Emotional Pattern Analysis**:
   - Identify the dominant emotions throughout the interview
   - Note any significant shifts in emotional state
   - Interpret what these patterns reveal about the candidate's comfort with different topics

2. **Question-Specific Emotional Insights**:
   - For each interview question, provide insights about the candidate's emotional response
   - Explain what the emotional response reveals about the candidate's relationship to the topic
   - Connect specific words or phrases to emotional reactions

3. **Emotional Strengths**:
   - Identify 2-3 strengths revealed by the candidate's emotional patterns
   - IMPORTANT: Only include strengths related to topics actually discussed in the interview
   - Support with specific examples from the emotional data

4. **Emotional Development Areas**:
   - Identify 2-3 areas for development based on emotional patterns
   - IMPORTANT: Only include development areas related to topics actually discussed in the interview
   - Do NOT mention skills gaps for topics that weren't addressed in the interview questions
   - Support with specific examples from the emotional data

Please structure your response as a JSON object with the following keys:
- emotional_response_analysis
- question_specific_insights (array of objects with question and insight)
- strengths (array)
- development_areas (array)
"""
{{ ... }}