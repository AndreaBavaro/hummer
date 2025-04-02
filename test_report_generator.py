"""
Test script to generate a comprehensive PDF report from interview data.

This script takes the Hume analysis, insights, and transcript files from a specific
meeting directory and generates a PDF report using the ReportGenerator class.
"""

import os
import sys
import json
import logging
from pathlib import Path
from types import SimpleNamespace
from datetime import datetime
from dotenv import load_dotenv

# Add the project root to the Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Import project modules
from src.reporting.generator import ReportGenerator
from src.analytics.processor import AnalyticsProcessor

# Configure logging
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class Config:
    """Configuration class for the test script."""
    
    def __init__(self):
        """Initialize configuration from environment variables."""
        # Load environment variables
        load_dotenv()
        
        # API keys
        self.anthropic_api_key = os.environ.get('ANTHROPIC_API_KEY', '')
        self.hume_api_key = os.environ.get('HUME_API_KEY', '')
        
        # Storage paths
        self.local_storage_path = os.environ.get('LOCAL_STORAGE_PATH', './data')
        self.reports_dir = os.path.join(self.local_storage_path, 'reports')
        
        # Create directories if they don't exist
        os.makedirs(self.reports_dir, exist_ok=True)
        
        # Log configuration status
        if self.anthropic_api_key:
            logger.info("Anthropic API key loaded")
        else:
            logger.warning("Anthropic API key not found in environment")
            
        if self.hume_api_key:
            logger.info("Hume API key loaded")
        else:
            logger.warning("Hume API key not found in environment")

def generate_report_from_files(hume_analysis_path, insights_path, transcript_path, output_dir=None):
    """
    Generate a comprehensive PDF report from the specified files.
    
    Args:
        hume_analysis_path: Path to the Hume AI analysis JSON file
        insights_path: Path to the insights JSON file
        transcript_path: Path to the transcript file (QA format)
        output_dir: Directory to save the PDF report (optional)
        
    Returns:
        str: Path to the generated PDF report
    """
    try:
        # Load the files
        with open(hume_analysis_path, 'r', encoding='utf-8') as f:
            hume_data = json.load(f)
        
        with open(transcript_path, 'r', encoding='utf-8') as f:
            transcript = f.read()
        
        # Initialize configuration
        config = Config()
        
        # Override local storage path if output directory is specified
        if output_dir:
            config.local_storage_path = output_dir
            config.reports_dir = os.path.join(output_dir, 'reports')
            os.makedirs(config.reports_dir, exist_ok=True)
        
        # Initialize the analytics processor
        processor = AnalyticsProcessor(config)
        
        # Initialize the report generator
        generator = ReportGenerator(config)
        
        # Extract candidate name from transcript
        candidate_name = "Candidate"
        for line in transcript.split('\n'):
            if '] Daniel Kraft' in line:
                candidate_name = "Daniel Kraft"
                break
        
        # Position being interviewed for
        position = "Account Executive"
        
        # Create analytics data structure
        analytics_data = {
            "result": hume_data,
            "result_path": hume_analysis_path
        }
        
        # Process the emotion data to extract insights
        insights = {}
        emotion_data = []  # Initialize empty emotion data
        
        # Try to extract insights from the emotion data
        try:
            # Check if we have a Claude insights file
            insights_json_path = os.path.splitext(hume_analysis_path)[0] + "_insights.json"
            if os.path.exists(insights_json_path):
                with open(insights_json_path, 'r', encoding='utf-8') as f:
                    insights = json.load(f)
                logger.info(f"Loaded Claude insights from {insights_json_path}")
                
                # Load emotion data from the insights.json file in the meeting directory
                emotion_data_path = os.path.join(os.path.dirname(hume_analysis_path), "insights.json")
                if os.path.exists(emotion_data_path):
                    with open(emotion_data_path, 'r', encoding='utf-8') as f:
                        emotion_data = json.load(f)
            else:
                # If no insights file exists, generate insights using the processor
                logger.info("No existing insights file found, generating insights...")
                if config.anthropic_api_key:
                    insights_result = processor.generate_insights(analytics_data, transcript_path, candidate_name)
                    if insights_result:
                        if "insights" in insights_result:
                            insights = insights_result["insights"]
                        if "emotion_data" in insights_result:
                            emotion_data = insights_result["emotion_data"]
                else:
                    logger.warning("Anthropic API key not available, skipping insights generation")
        except Exception as e:
            logger.error(f"Error processing insights: {e}")
        
        # Generate the report
        report_path = generator.generate_report(
            candidate_name=candidate_name,
            position=position,
            transcript=transcript,
            analytics_data=analytics_data,
            insights=insights,
            emotion_data=emotion_data,
            interview_date=datetime.now()
        )
        
        if report_path:
            logger.info(f"Report generated successfully: {report_path}")
            return report_path
        else:
            logger.error("Failed to generate report")
            return None
            
    except Exception as e:
        logger.exception(f"Error generating report: {e}")
        return None

if __name__ == "__main__":
    # File paths
    MEETING_DIR = r"C:\Users\Andre\CascadeProjects\finalcountdown\data\bot_bot_RSDBOKMPZsUZQOzw_2025-03-13_23-02-37"
    HUME_ANALYSIS_PATH = os.path.join(MEETING_DIR, "hume_analysis.json")
    INSIGHTS_PATH = os.path.join(MEETING_DIR, "insights.json")
    TRANSCRIPT_PATH = os.path.join(MEETING_DIR, "transcript_conversation_qa.txt")
    
    # Override output directory to be in the meeting directory
    OUTPUT_DIR = os.path.join(MEETING_DIR)
    
    # Generate the report
    report_path = generate_report_from_files(
        HUME_ANALYSIS_PATH,
        INSIGHTS_PATH,
        TRANSCRIPT_PATH,
        OUTPUT_DIR
    )
    
    if report_path:
        print(f"\nReport generated successfully: {report_path}")
        print(f"You can open this PDF file to view the comprehensive interview report.")
    else:
        print("\nFailed to generate report. Check the logs for details.")
