"""
Email Sender for the Zoom Interview Analysis System.

This module handles the automated sending of interview reports to interviewers
using various email services (AWS SES, Mailjet, SMTP).
"""

import os
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from pathlib import Path

logger = logging.getLogger(__name__)

class EmailSender:
    """Sends interview reports via email using various email services."""
    
    def __init__(self, config):
        """Initialize the email sender.
        
        Args:
            config: Application configuration object
        """
        self.config = config
        self.email_service = config.email_service
        self.from_email = config.email_from
        self.from_name = config.email_from_name
        
        logger.info(f"Initialized EmailSender using {self.email_service} service")
    
    def send_report(self, recipient_email, report_path, candidate_name, position=None):
        """Send an interview report via email.
        
        Args:
            recipient_email: Email address of the recipient (interviewer)
            report_path: Path to the PDF report file
            candidate_name: Name of the interview candidate
            position: Position the candidate is interviewing for (optional)
            
        Returns:
            bool: True if the email was sent successfully, False otherwise
        """
        logger.info(f"Sending report for {candidate_name} to {recipient_email}")
        
        # Validate inputs
        if not os.path.exists(report_path):
            raise FileNotFoundError(f"Report file not found: {report_path}")
        
        if not recipient_email:
            raise ValueError("Recipient email is required")
        
        # Prepare email content
        subject = f"Interview Report: {candidate_name}"
        if position:
            subject += f" - {position}"
        
        body = self._prepare_email_body(candidate_name, position)
        
        # Send email using the configured service
        if self.email_service == "ses":
            return self._send_via_ses(recipient_email, subject, body, report_path)
        elif self.email_service == "mailjet":
            return self._send_via_mailjet(recipient_email, subject, body, report_path)
        elif self.email_service == "smtp":
            return self._send_via_smtp(recipient_email, subject, body, report_path)
        else:
            logger.error(f"Unsupported email service: {self.email_service}")
            return False
    
    def _prepare_email_body(self, candidate_name, position=None):
        """Prepare the email body.
        
        Args:
            candidate_name: Name of the interview candidate
            position: Position the candidate is interviewing for (optional)
            
        Returns:
            str: Email body HTML
        """
        position_text = f" for the {position} position" if position else ""
        
        body = f"""
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                h1 {{ color: #2c3e50; font-size: 24px; margin-bottom: 20px; }}
                p {{ margin-bottom: 15px; }}
                .footer {{ margin-top: 30px; font-size: 12px; color: #777; }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1>Interview Analysis Report</h1>
                
                <p>Dear Interviewer,</p>
                
                <p>Attached is the comprehensive analysis report for your recent interview with <strong>{candidate_name}</strong>{position_text}.</p>
                
                <p>This report includes:</p>
                <ul>
                    <li>Executive summary and recommendation</li>
                    <li>Candidate strengths and areas for development</li>
                    <li>Emotional intelligence assessment</li>
                    <li>Communication style analysis</li>
                    <li>Content quality assessment</li>
                    <li>Cultural fit indicators</li>
                    <li>Recommended follow-up questions</li>
                    <li>Complete interview transcript</li>
                </ul>
                
                <p>Please review the attached PDF for the detailed analysis. If you have any questions or need further information, please contact the HR department.</p>
                
                <p>Best regards,<br>
                {self.from_name}</p>
                
                <div class="footer">
                    <p>This is an automated message from the Zoom Interview Analysis System. Please do not reply to this email.</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        return body
    
    def _send_via_ses(self, recipient_email, subject, body, attachment_path):
        """Send email using AWS SES.
        
        Args:
            recipient_email: Email address of the recipient
            subject: Email subject
            body: Email body HTML
            attachment_path: Path to the attachment file
            
        Returns:
            bool: True if the email was sent successfully, False otherwise
        """
        try:
            import boto3
            from botocore.exceptions import ClientError
            
            # Create SES client
            ses_client = boto3.client(
                'ses',
                region_name=self.config.ses_region,
                aws_access_key_id=self.config.aws_access_key_id,
                aws_secret_access_key=self.config.aws_secret_access_key
            )
            
            # Create message container
            message = MIMEMultipart()
            message['Subject'] = subject
            message['From'] = f"{self.from_name} <{self.from_email}>"
            message['To'] = recipient_email
            
            # Attach HTML body
            html_part = MIMEText(body, 'html')
            message.attach(html_part)
            
            # Attach PDF report
            with open(attachment_path, 'rb') as file:
                attachment = MIMEApplication(file.read())
                attachment.add_header(
                    'Content-Disposition',
                    'attachment',
                    filename=os.path.basename(attachment_path)
                )
                message.attach(attachment)
            
            # Send email
            response = ses_client.send_raw_email(
                Source=f"{self.from_name} <{self.from_email}>",
                Destinations=[recipient_email],
                RawMessage={'Data': message.as_string()}
            )
            
            logger.info(f"Email sent via SES: {response['MessageId']}")
            return True
            
        except Exception as e:
            logger.exception(f"Error sending email via SES: {e}")
            return False
    
    def _send_via_mailjet(self, recipient_email, subject, body, attachment_path):
        """Send email using Mailjet.
        
        Args:
            recipient_email: Email address of the recipient
            subject: Email subject
            body: Email body HTML
            attachment_path: Path to the attachment file
            
        Returns:
            bool: True if the email was sent successfully, False otherwise
        """
        try:
            from mailjet_rest import Client
            import base64
            
            # Create Mailjet client
            mailjet = Client(
                auth=(self.config.mailjet_api_key, self.config.mailjet_secret_key),
                version='v3.1'
            )
            
            # Read attachment file
            with open(attachment_path, 'rb') as file:
                attachment_content = base64.b64encode(file.read()).decode('utf-8')
            
            # Prepare data
            data = {
                'Messages': [
                    {
                        'From': {
                            'Email': self.from_email,
                            'Name': self.from_name
                        },
                        'To': [
                            {
                                'Email': recipient_email
                            }
                        ],
                        'Subject': subject,
                        'HTMLPart': body,
                        'Attachments': [
                            {
                                'ContentType': 'application/pdf',
                                'Filename': os.path.basename(attachment_path),
                                'Base64Content': attachment_content
                            }
                        ]
                    }
                ]
            }
            
            # Send email
            result = mailjet.send.create(data=data)
            
            if result.status_code == 200:
                logger.info(f"Email sent via Mailjet: {result.json()}")
                return True
            else:
                logger.error(f"Error sending email via Mailjet: {result.json()}")
                return False
            
        except Exception as e:
            logger.exception(f"Error sending email via Mailjet: {e}")
            return False
    
    def _send_via_smtp(self, recipient_email, subject, body, attachment_path):
        """Send email using SMTP.
        
        Args:
            recipient_email: Email address of the recipient
            subject: Email subject
            body: Email body HTML
            attachment_path: Path to the attachment file
            
        Returns:
            bool: True if the email was sent successfully, False otherwise
        """
        try:
            # Create message container
            message = MIMEMultipart()
            message['Subject'] = subject
            message['From'] = f"{self.from_name} <{self.from_email}>"
            message['To'] = recipient_email
            
            # Attach HTML body
            html_part = MIMEText(body, 'html')
            message.attach(html_part)
            
            # Attach PDF report
            with open(attachment_path, 'rb') as file:
                attachment = MIMEApplication(file.read())
                attachment.add_header(
                    'Content-Disposition',
                    'attachment',
                    filename=os.path.basename(attachment_path)
                )
                message.attach(attachment)
            
            # Connect to SMTP server
            smtp = smtplib.SMTP(self.config.smtp_server, self.config.smtp_port)
            
            if self.config.smtp_use_tls:
                smtp.starttls()
            
            # Login to SMTP server
            smtp.login(self.config.smtp_username, self.config.smtp_password)
            
            # Send email
            smtp.sendmail(self.from_email, recipient_email, message.as_string())
            
            # Close connection
            smtp.quit()
            
            logger.info(f"Email sent via SMTP to {recipient_email}")
            return True
            
        except Exception as e:
            logger.exception(f"Error sending email via SMTP: {e}")
            return False
