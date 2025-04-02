"""
Report Generator for the Zoom Interview Analysis System.

This module handles the generation of comprehensive PDF reports
containing interview transcripts, analytics, and insights.
"""

import os
import logging
import json
import re
from datetime import datetime
from pathlib import Path

# Import ReportLab for PDF generation
try:
    from reportlab.lib.pagesizes import letter
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
    from reportlab.platypus import PageBreak, ListFlowable, ListItem
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False

logger = logging.getLogger(__name__)

class ReportGenerator:
    """Generates comprehensive PDF reports for interview analysis."""
    
    def __init__(self, config):
        """Initialize the report generator.
        
        Args:
            config: Application configuration object
        """
        self.config = config
        
        if not REPORTLAB_AVAILABLE:
            logger.warning("reportlab is not available, PDF generation will be skipped")
            return
        
        # Create reports directory if it doesn't exist
        self.reports_dir = Path(config.local_storage_path) / "reports"
        os.makedirs(self.reports_dir, exist_ok=True)
        
        logger.info(f"Initialized ReportGenerator with reports directory: {self.reports_dir}")
    
    def generate_report_from_files(self, meeting_dir, position=None, candidate_name=None):
        """Generate a comprehensive PDF report from meeting directory files.
        
        Args:
            meeting_dir: Path to the meeting directory containing transcript.txt and insights.json
            position: Position the candidate is interviewing for (optional)
            candidate_name: Name of the interview candidate (optional)
            
        Returns:
            str: Path to the generated PDF report or None if generation failed
        """
        meeting_dir = Path(meeting_dir)
        
        # Locate required files
        transcript_path = meeting_dir / "transcript.txt"
        
        # Find the insights.json file (could be in a subdirectory)
        insights_path = None
        insights_json_path = None
        
        # First look for the insights_raw.txt file which contains the Claude insights
        for path in meeting_dir.glob("**/*_insights.json"):
            insights_json_path = path
            break
            
        if not insights_json_path:
            # Fall back to looking for insights.json which contains emotion data
            for path in meeting_dir.glob("**/insights.json"):
                insights_path = path
                break
            
        if not transcript_path.exists():
            logger.error(f"Transcript file not found at {transcript_path}")
            return None
            
        if not (insights_json_path or insights_path):
            logger.error(f"No insights files found in {meeting_dir}")
            return None
            
        # Load transcript
        try:
            with open(transcript_path, 'r', encoding='utf-8') as f:
                transcript_text = f.read()
        except Exception as e:
            logger.error(f"Failed to read transcript file: {e}")
            return None
            
        # Load insights
        insights_data = {}
        emotion_data = []
        
        # First try to load the Claude insights
        if insights_json_path and insights_json_path.exists():
            try:
                with open(insights_json_path, 'r', encoding='utf-8') as f:
                    insights_data = json.load(f)
                logger.info(f"Loaded Claude insights from {insights_json_path}")
            except Exception as e:
                logger.error(f"Failed to read Claude insights file: {e}")
        
        # Then try to load the emotion data
        if insights_path and insights_path.exists():
            try:
                with open(insights_path, 'r', encoding='utf-8') as f:
                    emotion_data = json.load(f)
                logger.info(f"Loaded emotion data from {insights_path}")
            except Exception as e:
                logger.error(f"Failed to read emotion data file: {e}")
            
        # Extract meeting metadata if available
        metadata = {}
        metadata_path = meeting_dir / "recording_metadata.json"
        if metadata_path.exists():
            try:
                with open(metadata_path, 'r', encoding='utf-8') as f:
                    metadata = json.load(f)
            except Exception as e:
                logger.warning(f"Failed to read metadata file: {e}")
        
        # Extract meeting details from directory name if not provided
        if not candidate_name:
            # Try to extract from directory name (e.g., "meeting_12345_JohnDoe_20250313")
            dir_name = meeting_dir.name
            parts = dir_name.split('_')
            if len(parts) >= 3:
                # Use the bot ID as candidate identifier if nothing better is available
                candidate_name = parts[2]
        
        # Generate the report
        return self.generate_report(
            candidate_name=candidate_name or "Unknown Candidate",
            position=position or "Unspecified Position",
            transcript=transcript_text,
            analytics_data={},  # Raw analytics data not needed for PDF
            insights=insights_data,
            emotion_data=emotion_data,
            interview_date=self._extract_interview_date(metadata, meeting_dir)
        )
    
    def _extract_interview_date(self, metadata, meeting_dir):
        """Extract interview date from metadata or directory name."""
        if metadata and 'start_timestamp_ms' in metadata:
            try:
                # Convert milliseconds timestamp to datetime
                timestamp_ms = metadata['start_timestamp_ms']
                return datetime.fromtimestamp(timestamp_ms / 1000)
            except Exception as e:
                logger.warning(f"Failed to parse timestamp from metadata: {e}")
        
        # Try to extract date from directory name
        dir_name = meeting_dir.name
        date_match = re.search(r'(\d{8})_', dir_name)
        if date_match:
            date_str = date_match.group(1)
            try:
                return datetime.strptime(date_str, '%Y%m%d')
            except ValueError:
                pass
        
        # Default to current date if extraction fails
        return datetime.now()
    
    def generate_report(self, candidate_name, position, transcript, analytics_data, insights, emotion_data=None, interview_date=None):
        """Generate a comprehensive PDF report.
        
        Args:
            candidate_name: Name of the interview candidate
            position: Position the candidate is interviewing for
            transcript: Interview transcript
            analytics_data: Analytics data from Hume AI
            insights: Insights generated by Claude
            emotion_data: Emotion data extracted from Hume AI (optional)
            interview_date: Date of the interview (optional, defaults to now)
            
        Returns:
            str: Path to the generated PDF report
        """
        if not REPORTLAB_AVAILABLE:
            logger.warning("reportlab is not available, PDF generation will be skipped")
            return None
            
        logger.info(f"Generating report for candidate: {candidate_name}")
        
        # Create timestamp for file naming
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        sanitized_name = self._sanitize_filename(candidate_name)
        report_filename = f"{sanitized_name}_{timestamp}_report.pdf"
        report_path = self.reports_dir / report_filename
        
        # Create PDF document
        doc = SimpleDocTemplate(
            str(report_path),
            pagesize=letter,
            rightMargin=72,
            leftMargin=72,
            topMargin=72,
            bottomMargin=72
        )
        
        # Get styles and modify them instead of adding new ones
        styles = getSampleStyleSheet()
        
        # Modify existing styles
        styles['Heading1'].fontSize = 18
        styles['Heading1'].spaceAfter = 12
        
        styles['Heading2'].fontSize = 16
        styles['Heading2'].spaceAfter = 10
        
        styles['Heading3'].fontSize = 14
        styles['Heading3'].spaceAfter = 8
        
        styles['Normal'].fontSize = 11
        styles['Normal'].spaceAfter = 6
        
        # Create new styles that don't exist in the default stylesheet
        interviewer_style = ParagraphStyle(
            name='Interviewer',
            parent=styles['Normal'],
            fontSize=11,
            spaceAfter=6,
            textColor=colors.darkblue,
            fontName='Helvetica-Bold'
        )
        styles.add(interviewer_style)
        
        interviewee_style = ParagraphStyle(
            name='Interviewee',
            parent=styles['Normal'],
            fontSize=11,
            spaceAfter=6,
            textColor=colors.darkred,
            fontName='Helvetica'
        )
        styles.add(interviewee_style)
        
        # Build PDF content
        content = []
        
        # Add title
        content.append(Paragraph("INTERVIEW ANALYSIS REPORT", styles['Title']))
        content.append(Spacer(1, 0.25*inch))
        
        # Add candidate information in a table format
        data = [
            ["Candidate Name:", candidate_name],
            ["Position:", position],
        ]
        
        # Add interview date if available
        if interview_date:
            interview_date_str = interview_date.strftime('%B %d, %Y')
        else:
            interview_date_str = datetime.now().strftime('%B %d, %Y')
        
        data.append(["Interview Date:", interview_date_str])
        data.append(["Report Generated:", datetime.now().strftime('%B %d, %Y %H:%M')])
        
        # Create table for candidate info
        info_table = Table(data, colWidths=[2*inch, 4*inch])
        info_table.setStyle(TableStyle([
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('BACKGROUND', (0, 0), (0, -1), colors.lightgrey),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('PADDING', (0, 0), (-1, -1), 6),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ]))
        
        content.append(info_table)
        content.append(Spacer(1, 0.5*inch))
        
        # Add recommendation at the top for quick reference
        content.append(Paragraph("RECOMMENDATION", styles['Heading1']))
        if "recommendation" in insights:
            content.append(Paragraph(insights["recommendation"], styles['Normal']))
        else:
            content.append(Paragraph("Recommendation not available.", styles['Normal']))
        content.append(Spacer(1, 0.25*inch))
        
        # Add executive summary
        content.append(Paragraph("EXECUTIVE SUMMARY", styles['Heading1']))
        if "executive_summary" in insights:
            content.append(Paragraph(insights["executive_summary"], styles['Normal']))
        else:
            content.append(Paragraph("Executive summary not available.", styles['Normal']))
        content.append(Spacer(1, 0.25*inch))
        
        # Add strengths and development areas
        content.append(Paragraph("KEY STRENGTHS", styles['Heading2']))
        if "strengths" in insights:
            strengths = insights["strengths"]
            if isinstance(strengths, list):
                items = []
                for strength in strengths:
                    items.append(ListItem(Paragraph(strength, styles['Normal'])))
                content.append(ListFlowable(items, bulletType='bullet', leftIndent=20))
            else:
                content.append(Paragraph(str(strengths), styles['Normal']))
        else:
            content.append(Paragraph("Strengths not available.", styles['Normal']))
        content.append(Spacer(1, 0.25*inch))
        
        content.append(Paragraph("AREAS FOR DEVELOPMENT", styles['Heading2']))
        if "development_areas" in insights:
            areas = insights["development_areas"]
            if isinstance(areas, list):
                items = []
                for area in areas:
                    items.append(ListItem(Paragraph(area, styles['Normal'])))
                content.append(ListFlowable(items, bulletType='bullet', leftIndent=20))
            else:
                content.append(Paragraph(str(areas), styles['Normal']))
        else:
            content.append(Paragraph("Development areas not available.", styles['Normal']))
        content.append(Spacer(1, 0.25*inch))
        
        # Add page break
        content.append(PageBreak())
        
        # Add detailed analysis sections
        content.append(Paragraph("DETAILED ANALYSIS", styles['Heading1']))
        
        # Emotional Intelligence
        content.append(Paragraph("Emotional Intelligence Assessment", styles['Heading2']))
        if "emotional_intelligence" in insights:
            content.append(Paragraph(insights["emotional_intelligence"], styles['Normal']))
        else:
            content.append(Paragraph("Emotional intelligence assessment not available.", styles['Normal']))
        content.append(Spacer(1, 0.25*inch))
        
        # Emotional Response Analysis (new section)
        content.append(Paragraph("Emotional Response Analysis", styles['Heading2']))
        if "emotional_response_analysis" in insights:
            content.append(Paragraph(insights["emotional_response_analysis"], styles['Normal']))
        else:
            content.append(Paragraph("Emotional response analysis not available.", styles['Normal']))
        content.append(Spacer(1, 0.25*inch))
        
        # Communication Style
        content.append(Paragraph("Communication Style Analysis", styles['Heading2']))
        if "communication_style" in insights:
            content.append(Paragraph(insights["communication_style"], styles['Normal']))
        else:
            content.append(Paragraph("Communication style analysis not available.", styles['Normal']))
        content.append(Spacer(1, 0.25*inch))
        
        # Content Quality
        content.append(Paragraph("Question and Answer Analysis", styles['Heading2']))
        if "content_quality" in insights:
            content.append(Paragraph(insights["content_quality"], styles['Normal']))
        else:
            content.append(Paragraph("Question and answer analysis not available.", styles['Normal']))
        content.append(Spacer(1, 0.25*inch))
        
        # Add emotion data visualization if available
        if emotion_data and isinstance(emotion_data, list) and len(emotion_data) > 0:
            content.append(Paragraph("EMOTION ANALYSIS", styles['Heading1']))
            content.append(Spacer(1, 0.25*inch))
            
            # Check if we have filtered QA pairs from the new approach
            filtered_qa_pairs = insights.get("filtered_qa_pairs", []) if insights and isinstance(insights, dict) else []
            
            if filtered_qa_pairs:
                # Use the new filtered question-answer pairs approach
                content.append(Paragraph("The following analysis shows emotional patterns during key interview questions:", styles['Normal']))
                content.append(Spacer(1, 0.1*inch))
                
                # Create a table to display emotion data for key questions
                content.append(Paragraph("Key Interview Questions and Emotional Responses", styles['Heading2']))
                emotion_table_data = [["Question", "Candidate Response", "Emotional Insights"]]
                
                # Get question-specific insights if available
                question_specific_insights = insights.get("question_specific_insights", []) if insights and isinstance(insights, dict) else []
                question_insights_map = {}
                
                # Create a map of questions to their insights for easy lookup
                for insight in question_specific_insights:
                    question = insight.get("question", "")
                    analysis = insight.get("analysis", "")
                    question_insights_map[question] = analysis
                
                for qa_pair in filtered_qa_pairs:
                    question = qa_pair.get("question", "")
                    question_short = question[:100] + ("..." if len(question) > 100 else "")
                    response = qa_pair.get("response", {})
                    transcript_text = response.get("transcript", "")[:100] + ("..." if len(response.get("transcript", "")) > 100 else "")
                    
                    # Get emotions for this response
                    emotions = response.get("avg_emotions", {})
                    
                    # Get relevant emotions with scores above 0.3 (meaningful signal)
                    relevant_emotions = [
                        "Confidence", "Anxiety", "Interest", "Concentration", "Confusion", 
                        "Determination", "Enthusiasm", "Excitement", "Joy", "Calmness",
                        "Doubt", "Nervousness", "Pride", "Satisfaction", "Surprise (positive)",
                        "Surprise (negative)", "Disappointment", "Frustration"
                    ]
                    
                    relevant_top_emotions = [(emotion, score) for emotion, score in emotions.items() 
                                            if emotion in relevant_emotions and score > 0.3]
                    
                    # Sort by score
                    relevant_top_emotions.sort(key=lambda x: x[1], reverse=True)
                    
                    # Take top 3 relevant emotions
                    top_emotions = relevant_top_emotions[:3]
                    
                    # Generate insight text based on emotions
                    if question in question_insights_map:
                        # Use the pre-generated insight if available
                        insight_text = question_insights_map[question]
                        # Truncate if too long
                        if len(insight_text) > 100:
                            insight_text = insight_text[:97] + "..."
                    else:
                        # Generate a basic insight based on the emotions
                        if top_emotions:
                            emotion_names = [emotion for emotion, _ in top_emotions]
                            if len(emotion_names) == 1:
                                insight_text = f"During the response, the candidate showed {emotion_names[0]}."
                            elif len(emotion_names) == 2:
                                insight_text = f"During the response, the candidate showed {emotion_names[0]} and {emotion_names[1]}."
                            else:
                                insight_text = f"During the response, the candidate showed {', '.join(emotion_names[:-1])}, and {emotion_names[-1]}."
                        else:
                            insight_text = "No significant emotional patterns detected."
                        
                        # Truncate if too long
                        if len(insight_text) > 100:
                            insight_text = insight_text[:97] + "..."
                    
                    # Truncate question and transcript text to prevent overflow
                    question_short = question[:70] + ("..." if len(question) > 70 else "")
                    transcript_short = transcript_text[:70] + ("..." if len(transcript_text) > 70 else "")
                    
                    emotion_table_data.append([question_short, transcript_short, insight_text])
                
                if len(emotion_table_data) > 1:  # If we have data beyond the header
                    # Create the table with better column widths and styling for text wrapping
                    emotion_table = Table(emotion_table_data, colWidths=[1.8*inch, 2.2*inch, 2.5*inch])
                    emotion_table.setStyle(TableStyle([
                        ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
                        ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
                        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
                        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                        ('BACKGROUND', (0, 1), (-1, -1), colors.white),
                        ('GRID', (0, 0), (-1, -1), 1, colors.black),
                        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                        ('LEFTPADDING', (0, 0), (-1, -1), 6),
                        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
                        ('TOPPADDING', (0, 0), (-1, -1), 6),
                        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                        ('WORDWRAP', (0, 0), (-1, -1), True),
                    ]))
                    content.append(emotion_table)
                    content.append(Spacer(1, 0.25*inch))
                
                # Add word-emotion correlations if available
                word_emotion_correlations = insights.get("word_emotion_correlations", {}) if insights and isinstance(insights, dict) else {}
                
                if word_emotion_correlations:
                    content.append(Paragraph("Word-Emotion Correlations", styles['Heading2']))
                    content.append(Paragraph("The following words showed significant emotional correlations during the interview:", styles['Normal']))
                    content.append(Spacer(1, 0.1*inch))
                    
                    # Create a table for word-emotion correlations
                    word_table_data = [["Word", "Associated Emotions"]]
                    
                    # Sort words by the strength of their emotional correlations
                    def get_max_emotion_score(word_item):
                        word, emotions = word_item
                        return max(emotions.values()) if emotions else 0
                    
                    sorted_words = sorted(word_emotion_correlations.items(), key=get_max_emotion_score, reverse=True)
                    
                    # Take top 10 words with strongest emotional correlations
                    for word, emotions in sorted_words[:10]:
                        # Sort emotions by score
                        sorted_emotions = sorted(emotions.items(), key=lambda x: x[1], reverse=True)
                        
                        # Take top 3 emotions for this word
                        top_emotions = sorted_emotions[:3]
                        emotions_text = "\n".join([f"{emotion}: {score:.2f}" for emotion, score in top_emotions])
                        
                        word_table_data.append([word, emotions_text])
                    
                    if len(word_table_data) > 1:  # If we have data beyond the header
                        # Create the table
                        word_table = Table(word_table_data, colWidths=[2*inch, 4*inch])
                        word_table.setStyle(TableStyle([
                            ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
                            ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
                            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
                            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                            ('BACKGROUND', (0, 1), (-1, -1), colors.white),
                            ('GRID', (0, 0), (-1, -1), 1, colors.black),
                            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                        ]))
                        content.append(word_table)
                        content.append(Spacer(1, 0.25*inch))
                
                # Add question-specific insights if available
                question_specific_insights = insights.get("question_specific_insights", []) if insights and isinstance(insights, dict) else []
                
                if question_specific_insights:
                    content.append(Paragraph("Question-Specific Emotional Insights", styles['Heading2']))
                    
                    for i, insight in enumerate(question_specific_insights[:5]):  # Limit to top 5 insights
                        question = insight.get("question", f"Question {i+1}")
                        analysis = insight.get("analysis", "")
                        
                        content.append(Paragraph(f"Question: {question}", styles['Heading3']))
                        content.append(Paragraph(analysis, styles['Normal']))
                        content.append(Spacer(1, 0.1*inch))
            else:
                # Fall back to the original approach if no filtered QA pairs
                # Create a summary of emotion data
                emotion_summary = "The following emotions were detected during key interview responses:\n\n"
                content.append(Paragraph(emotion_summary, styles['Normal']))
                content.append(Spacer(1, 0.1*inch))
                
                # Create a table to display emotion data for key segments
                content.append(Paragraph("Key Interview Response Moments", styles['Heading2']))
                emotion_table_data = [["Timestamp", "Candidate Response", "Emotional Insights"]]
                
                # Filter for segments that are likely candidate responses to interview questions
                # Criteria: 
                # 1. Longer segments (likely substantive answers, not greetings)
                # 2. Not containing typical closing phrases
                # 3. Not containing interviewer phrases
                
                closing_phrases = ["take care", "see you", "goodbye", "bye", "thank you", "thanks"]
                interviewer_indicators = ["okay", "alright", "so,", "gotcha", "appreciate", "thank"]
                
                candidate_responses = []
                for segment in emotion_data:
                    transcript_text = segment.get("transcript", "").lower()
                    duration = segment.get("end", 0) - segment.get("start", 0)
                    
                    # Skip very short segments (likely not substantive answers)
                    if duration < 5:
                        continue
                    
                    # Skip segments that are likely closing remarks
                    if any(phrase in transcript_text for phrase in closing_phrases) and duration < 10:
                        continue
                    
                    # Skip segments that are likely from the interviewer
                    # Check if the segment starts with interviewer indicators and is relatively short
                    if any(transcript_text.startswith(indicator) for indicator in interviewer_indicators) and duration < 15:
                        continue
                    
                    # Skip segments with "pan" or "go for it" which are likely setup phrases
                    if "pan" in transcript_text and "go for it" in transcript_text:
                        continue
                    
                    # Keep segments that are likely candidate responses
                    candidate_responses.append(segment)
                
                # Sort candidate responses by emotional intensity (highest emotional scores first)
                def get_max_emotion_score(segment):
                    emotions = segment.get("avg_emotions", {})
                    return max(emotions.values()) if emotions else 0
                    
                sorted_responses = sorted(candidate_responses, key=get_max_emotion_score, reverse=True)
                
                # Take top 7 most emotionally significant responses
                significant_segments = sorted_responses[:7]
                
                # Sort them back by timestamp for chronological display
                significant_segments.sort(key=lambda x: x.get("start", 0))
                
                for segment in significant_segments:
                    timestamp = f"{segment.get('start', 0):.1f}s - {segment.get('end', 0):.1f}s"
                    transcript_text = segment.get("transcript", "")[:100] + ("..." if len(segment.get("transcript", "")) > 100 else "")
                    
                    # Get emotions that are relevant to interview performance
                    relevant_emotions = [
                        "Confidence", "Anxiety", "Interest", "Concentration", "Confusion", 
                        "Determination", "Enthusiasm", "Excitement", "Joy", "Calmness",
                        "Doubt", "Nervousness", "Pride", "Satisfaction", "Surprise (positive)",
                        "Surprise (negative)", "Disappointment", "Frustration"
                    ]
                    
                    # Get top emotions for this segment, prioritizing relevant emotions
                    emotions = segment.get("avg_emotions", {})
                    
                    # First get relevant emotions with scores above 0.3 (meaningful signal)
                    relevant_top_emotions = [(emotion, score) for emotion, score in emotions.items() 
                                            if emotion in relevant_emotions and score > 0.3]
                    
                    # Sort by score
                    relevant_top_emotions.sort(key=lambda x: x[1], reverse=True)
                    
                    # Take top 3 relevant emotions
                    top_emotions = relevant_top_emotions[:3]
                    
                    # Generate insight text based on emotions
                    if top_emotions:
                        emotion_names = [emotion for emotion, _ in top_emotions]
                        if len(emotion_names) == 1:
                            insight_text = f"During this response, the candidate showed {emotion_names[0]}."
                        elif len(emotion_names) == 2:
                            insight_text = f"During this response, the candidate showed {emotion_names[0]} and {emotion_names[1]}."
                        else:
                            insight_text = f"During this response, the candidate showed {', '.join(emotion_names[:-1])}, and {emotion_names[-1]}."
                    else:
                        insight_text = "No significant emotional patterns detected."
                    
                    # Truncate insight text if too long
                    if len(insight_text) > 80:
                        insight_text = insight_text[:77] + "..."
                    
                    # Truncate transcript text more aggressively to prevent overflow
                    short_transcript = transcript_text[:80] + ("..." if len(transcript_text) > 80 else "")
                    
                    emotion_table_data.append([timestamp, short_transcript, insight_text])
                
                if len(emotion_table_data) > 1:  # If we have data beyond the header
                    # Create the table with better column widths and styling for text wrapping
                    emotion_table = Table(emotion_table_data, colWidths=[0.8*inch, 3.2*inch, 2.5*inch])
                    emotion_table.setStyle(TableStyle([
                        ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
                        ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
                        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
                        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                        ('BACKGROUND', (0, 1), (-1, -1), colors.white),
                        ('GRID', (0, 0), (-1, -1), 1, colors.black),
                        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                        ('LEFTPADDING', (0, 0), (-1, -1), 6),
                        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
                        ('TOPPADDING', (0, 0), (-1, -1), 6),
                        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                        ('WORDWRAP', (0, 0), (-1, -1), True),
                    ]))
                    content.append(emotion_table)
                    content.append(Spacer(1, 0.25*inch))
        
        # Follow-up Questions
        content.append(Paragraph("Recommended Follow-up Questions", styles['Heading2']))
        if "followup_questions" in insights:
            questions = insights["followup_questions"]
            if isinstance(questions, list):
                items = []
                for question in questions:
                    items.append(ListItem(Paragraph(question, styles['Normal'])))
                content.append(ListFlowable(items, bulletType='bullet', leftIndent=20))
            else:
                content.append(Paragraph(str(questions), styles['Normal']))
        else:
            content.append(Paragraph("Follow-up questions not available.", styles['Normal']))
        content.append(Spacer(1, 0.25*inch))
        
        # Add page break before transcript
        content.append(PageBreak())
        
        # Add transcript with clear speaker distinction
        content.append(Paragraph("INTERVIEW TRANSCRIPT", styles['Heading1']))
        content.append(Spacer(1, 0.25*inch))
        
        # Format transcript with speaker labels and clear distinction
        formatted_transcript = self._format_transcript_with_speakers(transcript)
        for segment in formatted_transcript:
            if segment['is_interviewer']:
                content.append(Paragraph(f"<b>Interviewer:</b> {segment['text']}", styles['Interviewer']))
            else:
                content.append(Paragraph(f"<b>Candidate:</b> {segment['text']}", styles['Interviewee']))
        
        # Build the PDF
        doc.build(content)
        
        logger.info(f"Generated report at {report_path}")
        
        return str(report_path)
    
    def _format_transcript_with_speakers(self, transcript):
        """Format the transcript with clear speaker distinction.
        
        Args:
            transcript: Raw transcript text
            
        Returns:
            list: List of transcript segments with speaker identification
        """
        segments = []
        
        # Check if transcript is in JSON format with speaker IDs
        if transcript.startswith('{') or '[' in transcript:
            try:
                # Try to extract structured data from the transcript
                # This is a simplified approach and might need adjustment based on actual format
                speaker_pattern = r'\[(.*?)\]\s*(.*?)\s*\(ID:\s*(\d+)\):'
                matches = re.findall(speaker_pattern, transcript)
                
                current_speaker = None
                current_text = ""
                
                lines = transcript.split('\n')
                for line in lines:
                    # Skip header lines
                    if line.startswith('Interview Transcript') or line.startswith('=====') or not line.strip():
                        continue
                        
                    # Check if this is a new speaker
                    speaker_match = re.search(speaker_pattern, line)
                    if speaker_match:
                        # Save previous segment if exists
                        if current_speaker is not None and current_text:
                            segments.append({
                                'speaker': current_speaker,
                                'is_interviewer': 'interviewer' in current_speaker.lower(),
                                'text': current_text.strip()
                            })
                            current_text = ""
                        
                        # Extract new speaker
                        current_speaker = speaker_match.group(2).strip()
                        
                        # Extract text after speaker identification
                        text_start = line.find(':', line.find('ID:')) + 1
                        if text_start > 0:
                            json_part = line[text_start:].strip()
                            try:
                                # Try to parse JSON to extract transcript
                                data = json.loads(json_part)
                                if 'transcript' in data:
                                    current_text = data['transcript']
                            except:
                                # If JSON parsing fails, use the text as is
                                current_text = json_part
                    else:
                        # Continue with current speaker
                        current_text += " " + line
                
                # Add the last segment
                if current_speaker is not None and current_text:
                    segments.append({
                        'speaker': current_speaker,
                        'is_interviewer': 'interviewer' in current_speaker.lower(),
                        'text': current_text.strip()
                    })
            except Exception as e:
                logger.warning(f"Failed to parse structured transcript: {e}")
        
        # If no structured data was found or parsing failed, use a simple approach
        if not segments:
            # Simple approach: assume alternating speakers, starting with interviewer
            is_interviewer = True
            paragraphs = re.split(r'\n\s*\n', transcript)
            
            for paragraph in paragraphs:
                # Skip header lines
                if paragraph.startswith('Interview Transcript') or paragraph.startswith('=====') or not paragraph.strip():
                    continue
                
                segments.append({
                    'speaker': 'Interviewer' if is_interviewer else 'Candidate',
                    'is_interviewer': is_interviewer,
                    'text': paragraph.strip()
                })
                
                # Alternate speakers
                is_interviewer = not is_interviewer
        
        return segments
    
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
