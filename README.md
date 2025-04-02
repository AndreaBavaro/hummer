# Zoom Interview Analysis System

## Overview
This application streamlines HR and interviewer workflows by automating the extraction, analysis, and reporting of Zoom interview data. The system leverages the Attendee API to join scheduled meetings, captures recordings and transcriptions, processes them through Hume AI for emotional and conversational analytics, uses an LLM to derive insights, and compiles everything into a comprehensive PDF report sent to the interviewer.

## Features
- **Zoom Meeting Automation**: Automatically joins meetings, records, and transcribes using the Attendee API
- **Email Monitoring**: Continuously monitors an email inbox for Zoom meeting invitations
- **Meeting Scheduling**: Schedules meetings for future dates or joins immediately
- **Database Management**: Stores user information, meeting details, and analysis results
- **Storage**: Local storage for testing, AWS S3 for production
- **Analytics**: Hume AI integration for emotional and conversational analysis
- **Insight Generation**: LLM processing of analytics data to extract meaningful insights
- **PDF Reporting**: Comprehensive reports with transcriptions, analytics, and insights
- **Email Automation**: Automatic delivery of reports to interviewers
- **Client Onboarding**: Onboards clients with unique hash keys for identification

## Technical Stack
- **Python**: Core application language
- **Attendee API**: For meeting automation
- **SQLite**: Local database for user and meeting management
- **AWS S3**: Cloud storage for production
- **Hume AI API**: Emotional and conversational analytics
- **Claude Sonnet 3.7**: LLM for insights extraction
- **ReportLab**: PDF generation
- **AWS SES**: Email automation

## Workflow
1. Monitor email for Zoom meeting invitations or manually input meeting details
2. Schedule bot attendance for future meetings or join immediately
3. Automatically join and record Zoom meetings
4. Retrieve and store recordings/transcriptions
5. Submit recordings to Hume API for analytics
6. Process analytics with LLM to extract insights
7. Generate structured PDF report
8. Forward report to interviewers/HR
9. Store all data and results in the database for future reference

## Setup and Installation
1. Clone this repository
2. Run the setup script to create a virtual environment and install dependencies:
   ```
   python setup.py
   ```
   This will:
   - Create a virtual environment in the `venv` directory
   - Install all required dependencies
   - Create the `.env` file from the template (if it doesn't exist)
   - Initialize the database
   - Create batch scripts for running the application
3. Fill in your API keys and credentials in the `.env` file:
   - Attendee API Key (create an account in your Attendee instance and navigate to 'API Keys' section)
   - Note: Zoom OAuth Credentials and Deepgram API Key should be configured directly on the Attendee dashboard
   - Hume AI API Key
   - Anthropic API Key (for Claude)
   - Email credentials (for monitoring and sending)
   - AWS credentials (if using cloud storage or SES)

## Running the Application
The setup script creates several batch files to make running the application easier:

- `run.bat` - Run the application with custom arguments
- `run_manual.bat` - Run in manual mode
- `run_monitor.bat` - Run in monitor mode
- `run_manage.bat` - Run in manage mode
- `init_db.bat` - Initialize the database

These batch files automatically activate the virtual environment, run the application, and deactivate the environment when done.

## Setting Up Email Monitoring

To use the email monitoring functionality, you need to configure your email credentials in the `.env` file:

1. **Gmail Configuration**:
   - Set `EMAIL_ADDRESS` to your Gmail address
   - For `EMAIL_PASSWORD`, you need to use an App Password instead of your regular password
   - To create an App Password:
     1. Go to your Google Account: https://myaccount.google.com/
     2. Select Security
     3. Under "Signing in to Google," select 2-Step Verification (you must have this enabled)
     4. At the bottom of the page, select App passwords
     5. Select "Mail" as the app and "Windows Computer" as the device
     6. Click "Generate" and copy the 16-character password
     7. Enter it in the `.env` file WITHOUT SPACES

2. **Testing Email Monitoring**:
   - Run `send_test_invitation.bat` to send a test Zoom meeting invitation to your configured email
   - Run `run_monitor.bat` to start the email monitoring
   - The application should detect the test invitation and schedule the bot to join the meeting

## Configuration
The application is configured using environment variables, which can be set in the `.env` file. See `config_template.env` for a list of available configuration options.

Key configuration sections include:
- Attendee API credentials
- Zoom OAuth credentials
- Email monitoring settings
- Database configuration
- Storage settings (local or AWS S3)
- Analytics API keys (Hume AI, Anthropic)
- Email delivery settings

## Usage
To use the application, you can run it in one of two modes:

### Manual Mode: Join a single meeting
```
python main.py --mode manual
```
This will prompt you for meeting details and then join the meeting.

### Monitor Mode: Continuously monitor email for meeting invitations
```
python main.py --mode monitor
```
This will start monitoring the configured email address for Zoom meeting invitations and automatically join meetings as they are received.

### Using a custom configuration file
```
python main.py --mode [manual|monitor] --config /path/to/config.env
```

## Database Structure
The application uses SQLite to store the following information:

### Users
- Email address
- Name
- Company
- Role
- Hash key (unique identifier for each user)
- Onboarded at timestamp
- Created at timestamp

### Meetings
- Hash key (references the user)
- URL
- Title
- Scheduled time
- Actual start and end times
- Status (scheduled, joining, completed, failed)
- File paths (recording, transcript, analytics, insights, report)

### Analysis Results
- Meeting ID
- Result type (hume_analysis, insights)
- Result data (JSON)

## Client Onboarding
The system allows for onboarding clients with their email addresses. Each client is assigned a unique hash key that is used to identify them in the system.

### Onboarding a New Client
To onboard a new client, use the `onboard_client.py` script:

```
python onboard_client.py --email client@example.com --name "Client Name" --company "Client Company" --role "Client Role"
```

This will:
1. Generate a unique hash key for the client based on their email address
2. Add the client to the database with their email, name, company, role, and hash key
3. Set the onboarded_at timestamp to the current time

### Checking Existing Users
To check if a user exists in the database, use the `check_users.py` script:

```
python check_users.py --email client@example.com
```

To verify a hash key for a specific email:

```
python check_users.py --email client@example.com --hash-key <hash_key>
```

### Listing Meetings for a User
To list all meetings for a user, use the `list_meetings.py` script:

```
python list_meetings.py --email client@example.com
```

Or by hash key:

```
python list_meetings.py --hash-key <hash_key>
```

### Adding a User Manually
To add a user manually (without onboarding), use the `add_user.py` script:

```
python add_user.py --email user@example.com --name "User Name" --company "User Company" --role "User Role"
```

### Reinitializing the Database
If you need to reinitialize the database with the updated schema, use the `reinit_database.py` script:

```
python reinit_database.py
```

**Warning**: This will delete all existing data in the database.

## Development
[Development guidelines will be added here]

## License
[License information will be added here]
