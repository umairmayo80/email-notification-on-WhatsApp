# Email to WhatsApp Notification System

A Python application that monitors your Gmail inbox and sends instant WhatsApp notifications when new emails arrive. Get real-time alerts on your phone for important emails without constantly checking your inbox.

## Features

- 📧 **Real-time Email Monitoring**: Connects to Gmail via IMAP and monitors for new unread emails
- 📱 **Instant WhatsApp Notifications**: Sends immediate WhatsApp messages using pywhatkit
- 🔍 **Smart Filtering**: Filter emails by keywords, specific senders, or monitor all emails
- ⚡ **Fast Detection**: Checks for new emails every 5 seconds by default
- 📝 **Clean Message Format**: Well-formatted WhatsApp messages with sender, subject, and preview
- 🛡️ **Non-intrusive**: Uses BODY.PEEK to avoid marking emails as read during monitoring
- ⚙️ **Easy Configuration**: Environment-based configuration with .env file

## Prerequisites

- Python 3.7 or higher
- Gmail account with App Password enabled (or other IMAP-enabled email)
- WhatsApp Web access on your computer
- Chrome browser (required by pywhatkit)

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

   # WhatsApp Configuration
   WHATSAPP_PHONE_NUMBER=+1234567890

   # Monitoring Settings
   CHECK_INTERVAL_MINUTES=0.083  # 5 seconds for real-time monitoring
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
| `WHATSAPP_PHONE_NUMBER` | WhatsApp number with country code | `+1234567890` |
| `CHECK_INTERVAL_MINUTES` | How often to check for emails (supports decimals) | `0.083` (5 seconds) |
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
2. **Non-intrusive Fetching**: Uses BODY.PEEK to read email content without marking as read
3. **Smart Filtering**: Processes emails based on your criteria:
   - Keywords in subject or body (optional)
   - Specific sender addresses (optional)
   - Leave filters empty to monitor ALL emails
4. **Instant WhatsApp Notifications**: Sends clean, formatted messages with:
   - 📧 Email icon
   - Sender name and email
   - Subject line
   - Body preview (first 150 characters)
5. **Continuous Monitoring**: Repeats every 5 seconds (configurable) for real-time alerts

## WhatsApp Integration Notes

- **First Run**: WhatsApp Web will open in Chrome browser for authentication
- **QR Code**: Scan the QR code with your phone to link WhatsApp Web
- **Stay Logged In**: Keep WhatsApp Web logged in for automatic sending
- **Instant Delivery**: Uses `sendwhatmsg_instantly` for immediate message delivery
- **Auto-close**: Browser tab closes automatically after sending
- **Rate Limiting**: 30-second delay between messages to avoid spam

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

3. **No Notifications Received**
   - Check if filters are too restrictive (try leaving them empty)
   - Verify emails are from today (system only checks today's emails)
   - Ensure emails are marked as "unread" in Gmail
   - Review logs for connection or filtering errors

### Debug Mode

For detailed debugging:
- Check `email_monitor.log` for email detection issues
- Check `notifier.log` for WhatsApp sending issues
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
📧 New Email

From: John Doe <john@example.com>
Subject: Important Meeting Tomorrow

Preview: Hi there, just wanted to remind you about our meeting scheduled for tomorrow at 2 PM. Please bring the quarterly reports...
```

## File Structure

```
email-notification-on-WhatsApp/
├── main.py                 # Main application entry point
├── email_monitor.py        # Email monitoring and IMAP handling
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
- 30-second delay between messages to prevent WhatsApp rate limiting

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
