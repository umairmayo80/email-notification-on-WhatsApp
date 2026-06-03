# Email to WhatsApp Notification System

A Python application that monitors your Gmail inbox, sends email notifications first, and then sends WhatsApp notifications for new emails.

## Features

- 📧 **Real-time Email Monitoring**: Connects to Gmail via IMAP and monitors for new unread emails
- ✉️ **Email-First Notifications**: Sends notification emails to configured recipients before WhatsApp is attempted
- 📱 **Reliable WhatsApp Notifications**: Sends WhatsApp Web messages with Selenium, a dedicated Chrome profile, and an explicit send-button click
- 🔍 **Smart Filtering**: Filter emails by keywords, specific senders, or monitor all emails
- ⚡ **Fast Detection**: Checks for new emails every 5 seconds by default
- 📝 **Clean Message Format**: Well-formatted WhatsApp messages with sender, subject, and preview
- 🛡️ **Delivery-aware Read Handling**: Uses BODY.PEEK while checking emails, then marks matching emails as read after WhatsApp succeeds or exhausts retries
- 🔁 **Retry State**: Stores WhatsApp retry state in `notification_state.json` so notification emails are not duplicated
- ⚙️ **Easy Configuration**: Environment-based configuration with .env file

## Prerequisites

- Python 3.7 or higher
- Gmail account with App Password enabled (or other IMAP-enabled email)
- WhatsApp Web access on your computer
- Chrome browser (required by Selenium WhatsApp Web automation)

## Installation

1. **Clone or download the project**
   ```bash
   cd email-notification-on-WhatsApp
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Set up configuration**
   ```bash
   cp .env.example .env
   ```
   
   Edit the `.env` file with your credentials:
   ```env
   # Email Configuration
   EMAIL_HOST=imap.gmail.com
   EMAIL_PORT=993
   EMAIL_USERNAME=your_email@gmail.com
   EMAIL_PASSWORD=your_app_password

   # Outbound Email Notification Configuration
   NOTIFY_EMAIL_RECIPIENTS=alert_recipient@example.com
   SMTP_HOST=smtp.gmail.com
   SMTP_PORT=465
   SMTP_USERNAME=  # Optional; defaults to EMAIL_USERNAME
   SMTP_PASSWORD=  # Optional; defaults to EMAIL_PASSWORD
   SMTP_FROM=      # Optional; defaults to SMTP_USERNAME/EMAIL_USERNAME
   EMAIL_NOTIFICATION_SUBJECT_PREFIX=Upwork Alert
   EMAIL_NOTIFICATION_BODY_INTRO=New Upwork alert matched your notification rule.

   # WhatsApp Configuration
   WHATSAPP_PHONE_NUMBER=+1234567890
   WHATSAPP_GROUP_INVITE_CODE=  # Optional; full group invite URL or code overrides phone number
   WHATSAPP_CHROME_PROFILE_DIR=.whatsapp_chrome_profile
   WHATSAPP_WAIT_SECONDS=90
   WHATSAPP_MAX_RETRIES=3
   WHATSAPP_RETRY_DELAY_SECONDS=300
   WHATSAPP_HEADLESS=false
   WHATSAPP_HEADLESS_WINDOW_SIZE=1280,900
   WHATSAPP_DEBUG_SCREENSHOT_DIR=debug_screenshots
   WHATSAPP_MESSAGE_HEADER=Upwork Alert

   # Monitoring Settings
   CHECK_INTERVAL_MINUTES=0.083  # 5 seconds for real-time monitoring
   MAX_EMAILS_PER_CHECK=3  # Maximum unread emails to process per check
   EMAIL_SCAN_MULTIPLIER=5  # Scan a wider unread window before applying filters
   NOTIFICATION_DELAY_SECONDS=2
   KEYWORDS_TO_MONITOR=  # Leave empty to monitor all emails
   MONITOR_SPECIFIC_SENDERS=  # Leave empty to monitor all senders
   ```

## Gmail Setup

For Gmail users, you need to:

1. **Enable 2-Factor Authentication** on your Google account
2. **Generate an App Password**:
   - Go to Google Account settings
   - Security → 2-Step Verification → App passwords
   - Generate a password for "Mail"
   - Use this password in the `EMAIL_PASSWORD` field

## Configuration Options

| Variable | Description | Example |
|----------|-------------|---------|
| `EMAIL_HOST` | IMAP server hostname | `imap.gmail.com` |
| `EMAIL_PORT` | IMAP server port | `993` |
| `EMAIL_USERNAME` | Your email address | `user@gmail.com` |
| `EMAIL_PASSWORD` | Email password or app password | `abcd efgh ijkl mnop` |
| `NOTIFY_EMAIL_RECIPIENTS` | Comma-separated email notification recipients | `alerts@example.com,me@example.com` |
| `SMTP_HOST` | Outbound SMTP host | `smtp.gmail.com` |
| `SMTP_PORT` | Outbound SMTP SSL port | `465` |
| `SMTP_USERNAME` | SMTP username; defaults to `EMAIL_USERNAME` | `user@gmail.com` |
| `SMTP_PASSWORD` | SMTP password; defaults to `EMAIL_PASSWORD` | `abcd efgh ijkl mnop` |
| `SMTP_FROM` | From address for notification emails | `user@gmail.com` |
| `EMAIL_NOTIFICATION_SUBJECT_PREFIX` | Prefix used for outbound notification email subjects | `Upwork Alert` |
| `EMAIL_NOTIFICATION_BODY_INTRO` | First sentence in outbound notification email bodies | `New Upwork alert matched your notification rule.` |
| `WHATSAPP_PHONE_NUMBER` | WhatsApp number with country code | `+1234567890` |
| `WHATSAPP_GROUP_INVITE_CODE` | Optional group invite URL/code; when set, WhatsApp sends to the group instead of the phone number | `https://web.whatsapp.com/accept?code=...` |
| `WHATSAPP_CHROME_PROFILE_DIR` | Dedicated Chrome profile for WhatsApp automation | `.whatsapp_chrome_profile` |
| `WHATSAPP_WAIT_SECONDS` | Wait time for WhatsApp Web elements | `90` |
| `WHATSAPP_MAX_RETRIES` | WhatsApp retry attempts after email notification succeeds | `3` |
| `WHATSAPP_RETRY_DELAY_SECONDS` | Delay before retrying WhatsApp | `300` |
| `WHATSAPP_HEADLESS` | Run Chrome without a visible browser window after WhatsApp Web is already authenticated | `false` |
| `WHATSAPP_HEADLESS_WINDOW_SIZE` | Browser viewport size used in headless mode | `1280,900` |
| `WHATSAPP_DEBUG_SCREENSHOT_DIR` | Directory for headless failure screenshots; leave empty to disable | `debug_screenshots` |
| `WHATSAPP_MESSAGE_HEADER` | First line/title of each WhatsApp notification | `Upwork Alert` |
| `CHECK_INTERVAL_MINUTES` | How often to check for emails (supports decimals) | `0.083` (5 seconds) |
| `MAX_EMAILS_PER_CHECK` | Maximum number of unread emails to process in one check | `3` |
| `EMAIL_SCAN_MULTIPLIER` | How many more unread candidates to scan before filtering | `5` |
| `NOTIFICATION_DELAY_SECONDS` | Delay between notification attempts | `2` |
| `KEYWORDS_TO_MONITOR` | Comma-separated keywords (leave empty for all emails) | `urgent,important` or empty |
| `MONITOR_SPECIFIC_SENDERS` | Comma-separated email addresses (leave empty for all) | `boss@company.com` or empty |

## Usage

### Run Continuously
Monitor emails continuously with scheduled checks:
```bash
python main.py
```

### Run Once
Check for emails once and exit:
```bash
python main.py --once
```

## How It Works

1. **Email Monitoring**: Connects to Gmail via IMAP and searches for unread emails from today
2. **Delivery-aware Fetching**: Uses BODY.PEEK to read email content without marking as read before delivery
3. **Smart Filtering**: Processes emails based on your criteria:
   - Keywords in subject or body (optional)
   - Specific sender addresses (optional)
   - Leave filters empty to monitor ALL emails
4. **Wider Candidate Scan**: Scans up to `MAX_EMAILS_PER_CHECK * EMAIL_SCAN_MULTIPLIER` recent unread messages, then notifies up to `MAX_EMAILS_PER_CHECK`
5. **Email Notification First**: Sends a notification email to `NOTIFY_EMAIL_RECIPIENTS`
6. **WhatsApp Notification Second**: Sends clean, formatted WhatsApp messages with:
   - 📧 Email icon
   - Sender name and email
   - Subject line
   - Body preview (first 150 characters)
7. **Retry-aware Read-state Update**: Marks matching emails as read after WhatsApp succeeds or exhausts configured retries
8. **Continuous Monitoring**: Repeats every 5 seconds (configurable) for real-time alerts

## WhatsApp Integration Notes

- **First Run**: WhatsApp Web will open in a dedicated Chrome profile for authentication
- **QR Code**: Scan the QR code with your phone to link WhatsApp Web
- **Stay Logged In**: Keep WhatsApp Web logged in for automatic sending
- **Profile Isolation**: The default profile directory is `.whatsapp_chrome_profile`, separate from your normal Chrome profile
- **Headless Mode**: Keep `WHATSAPP_HEADLESS=false` until WhatsApp Web is linked, then set it to `true` for unattended runs
- **Debug Screenshots**: In headless mode, WhatsApp failures save screenshots to `WHATSAPP_DEBUG_SCREENSHOT_DIR`
- **Send Button Click**: The script waits for WhatsApp Web, verifies the draft, clicks the real send button, and checks that the draft cleared
- **Rate Limiting**: `NOTIFICATION_DELAY_SECONDS` controls the delay between messages

## Logging

The application creates detailed logs in:
- `email_monitor.log` - Email monitoring activities
- `notifier.log` - General application logs
- Console output for real-time monitoring

## Troubleshooting

### Common Issues

1. **Email Connection Failed**
   - Verify email credentials
   - Check if 2FA/App Password is required
   - Ensure IMAP is enabled

2. **WhatsApp Messages Not Sending**
   - Verify phone number format (+countrycode + number)
   - Ensure WhatsApp Web is logged in
   - Check Chrome browser is installed
   - Close other Chrome windows using the same `WHATSAPP_CHROME_PROFILE_DIR`
   - Increase `WHATSAPP_WAIT_SECONDS` if WhatsApp Web loads slowly
   - If headless mode fails, check `WHATSAPP_DEBUG_SCREENSHOT_DIR`, then switch `WHATSAPP_HEADLESS=false` to re-authenticate

3. **No Notifications Received**
   - Check if filters are too restrictive (try leaving them empty)
   - Verify emails are from today (system only checks today's emails)
   - Ensure emails are marked as "unread" in Gmail
   - Review logs for connection or filtering errors

4. **Notification Emails Not Sending**
   - Set `NOTIFY_EMAIL_RECIPIENTS`
   - Confirm the Gmail app password works for SMTP
   - Override `SMTP_USERNAME` and `SMTP_PASSWORD` if outbound SMTP differs from IMAP

### Debug Mode

For detailed debugging:
- Check `email_monitor.log` for email detection issues
- Check `notifier.log` for WhatsApp sending issues
- Check headless WhatsApp screenshots in `debug_screenshots/` when enabled
- Use `python test_email_only.py` to test email detection without WhatsApp
- Run `python main.py --once` for single-run testing

## Security Considerations

- Store sensitive credentials in `.env` file (never commit to version control)
- Use App Passwords instead of main email password
- Regularly rotate credentials
- Monitor log files for unauthorized access attempts

## Example WhatsApp Message Format

When a new email is detected, you'll receive a WhatsApp message like this:

```
Upwork Alert

From: John Doe <john@example.com>
Subject: Important Meeting Tomorrow

Preview: Hi there, just wanted to remind you about our meeting scheduled for tomorrow at 2 PM. Please bring the quarterly reports...
```

## File Structure

```
email-notification-on-WhatsApp/
├── main.py                 # Main application entry point
├── email_monitor.py        # Email monitoring and IMAP handling
├── email_notification_sender.py # Outbound notification email handling
├── notification_state.py    # Retry state persistence
├── whatsapp_sender.py      # WhatsApp message sending
├── config.py              # Configuration management
├── test_email_only.py     # Email detection testing script
├── requirements.txt       # Python dependencies
├── .env                   # Your configuration (create from .env.example)
├── .env.example          # Configuration template
├── email_monitor.log     # Email monitoring logs
├── notifier.log          # Application logs
└── README.md             # This file
```

## Customization

You can extend the application by:
- **Email Providers**: Modify `email_monitor.py` for other IMAP servers (Outlook, Yahoo, etc.)
- **Notification Channels**: Add Telegram, Slack, or SMS notifications
- **Advanced Filtering**: Implement regex patterns or AI-based email classification
- **Web Interface**: Create a Flask/Django web UI for easier configuration
- **Database Storage**: Add SQLite to track processed emails and avoid duplicates

## Known Limitations

- Only works with IMAP-enabled email accounts
- Requires Chrome browser for WhatsApp Web integration
- WhatsApp Web must stay logged in for automatic sending
- Limited to today's emails only (by design to avoid spam)
- WhatsApp automation depends on WhatsApp Web's current page structure

## Contributing

Feel free to submit issues, feature requests, or pull requests to improve this project.

## License

This project is open source and available under the MIT License.

## Support

If you encounter issues:
1. Check the troubleshooting section above
2. Review log files (`email_monitor.log` and `notifier.log`) for error details
3. Test email detection with `python test_email_only.py`
4. Ensure all prerequisites are met and configuration is correct
5. Verify WhatsApp Web is logged in and accessible
