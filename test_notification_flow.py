import logging
import os
import tempfile
import unittest
import warnings
from unittest.mock import patch

import config
import whatsapp_sender
from email_notification_sender import EmailNotificationSender
from email_monitor import EmailMonitor
from main import EmailToWhatsAppNotifier
from notification_state import NotificationState
from whatsapp_sender import WhatsAppSender

warnings.filterwarnings('ignore', category=ResourceWarning)


def build_raw_email(subject='Routine update', sender='other@example.com', body='Body'):
    return (
        f"Subject: {subject}\r\n"
        f"From: {sender}\r\n"
        "Date: Wed, 03 Jun 2026 09:00:00 +0000\r\n"
        "Content-Type: text/plain; charset=utf-8\r\n"
        "\r\n"
        f"{body}"
    ).encode()


class FakeEmailMonitor:
    def __init__(self, emails, mark_result=True):
        self.emails = emails
        self.mark_result = mark_result
        self.marked_seen = []

    def get_new_emails(self):
        return self.emails

    def mark_email_as_seen(self, email_id):
        self.marked_seen.append(email_id)
        return self.mark_result


class FakeWhatsAppSender:
    def __init__(self, send_results, events=None):
        self.send_results = (
            list(send_results) if isinstance(send_results, list) else [send_results]
        )
        self.sent_messages = []
        self.sent_recipients = []
        self.events = events if events is not None else []

    def format_email_message(self, email_data):
        return f"Message for {email_data['subject']}"

    def send_immediate_message(self, message, recipient=None):
        self.sent_messages.append(message)
        self.sent_recipients.append(recipient)
        self.events.append(f"whatsapp:{message}")
        return self.send_results.pop(0) if self.send_results else False


class FakeEmailNotificationSender:
    def __init__(self, send_result=True, events=None):
        self.send_result = send_result
        self.sent_email_ids = []
        self.events = events if events is not None else []

    def send_email_notification(self, email_data):
        self.sent_email_ids.append(str(email_data['id']))
        self.events.append(f"email:{email_data['id']}")
        return self.send_result


class FakeIMAPConnection:
    def __init__(
        self,
        store_status='OK',
        search_response=b'101',
        fetch_message=None,
        fetch_messages=None,
    ):
        self.store_status = store_status
        self.search_response = search_response
        self.fetch_message = fetch_message or build_raw_email(
            body='This email should not match the configured sender filter.'
        )
        self.fetch_messages = fetch_messages or {}
        self.uid_calls = []
        self.select_calls = []

    def select(self, mailbox):
        self.select_calls.append(mailbox)
        return 'OK', [b'']

    def uid(self, command, *args):
        self.uid_calls.append((command, args))

        if command == 'SEARCH':
            return 'OK', [self.search_response]
        if command == 'FETCH':
            email_uid = args[0].decode() if isinstance(args[0], bytes) else str(args[0])
            return 'OK', [
                (b'101 (BODY[] {123}', self.fetch_messages.get(email_uid, self.fetch_message))
            ]
        if command == 'STORE':
            return self.store_status, [b'']

        return 'NO', [b'Unsupported command']


class RuntimeConfigFakeEmailMonitor:
    def __init__(self, config):
        self.config = config
        self.disconnect_count = 0

    def disconnect_from_email(self):
        self.disconnect_count += 1


class RuntimeConfigFakeEmailSender:
    def __init__(self, config):
        self.config = config


class RuntimeConfigFakeWhatsAppSender:
    def __init__(self, config):
        self.config = config
        self.close_count = 0

    def close(self):
        self.close_count += 1


class TestNotificationFlow(unittest.TestCase):
    def setUp(self):
        logging.disable(logging.CRITICAL)

    def tearDown(self):
        logging.disable(logging.NOTSET)

    def make_state(self):
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        return NotificationState(os.path.join(temp_dir.name, 'notification_state.json'))

    def make_notifier(
        self,
        email_monitor,
        whatsapp_sender,
        email_sender=None,
        notification_state=None,
        config=None,
    ):
        notifier = EmailToWhatsAppNotifier.__new__(EmailToWhatsAppNotifier)
        notifier.email_monitor = email_monitor
        notifier.email_sender = email_sender or FakeEmailNotificationSender()
        notifier.whatsapp_sender = whatsapp_sender
        notifier.notification_state = notification_state or self.make_state()
        notifier.config = config or type(
            'TestConfig',
            (),
            {
                'WHATSAPP_MAX_RETRIES': 3,
                'WHATSAPP_RETRY_DELAY_SECONDS': 0,
                'NOTIFICATION_DELAY_SECONDS': 0,
            },
        )
        notifier.logger = logging.getLogger('test_notification_flow')
        return notifier

    def make_email_monitor(self, connection):
        monitor = EmailMonitor.__new__(EmailMonitor)
        monitor.connection = connection
        monitor.last_check_time = None
        monitor.logger = logging.getLogger('test_email_monitor')
        return monitor

    def make_email_notification_sender(self):
        sender = EmailNotificationSender.__new__(EmailNotificationSender)
        sender.config = type(
            'TestEmailConfig',
            (),
            {
                'SMTP_FROM': 'alerts@example.com',
                'NOTIFY_EMAIL_RECIPIENTS': ['recipient@example.com'],
                'EMAIL_NOTIFICATION_SUBJECT_PREFIX': 'Upwork Alert',
                'EMAIL_NOTIFICATION_BODY_INTRO': (
                    'New Upwork alert matched your notification rule.'
                ),
            },
        )
        sender.logger = logging.getLogger('test_email_notification_sender')
        return sender

    def write_runtime_env(self, env_path, **overrides):
        values = {
            'EMAIL_HOST': 'imap.gmail.com',
            'EMAIL_PORT': '993',
            'EMAIL_USERNAME': 'source@example.com',
            'EMAIL_PASSWORD': 'email-password',
            'NOTIFY_EMAIL_RECIPIENTS': 'recipient@example.com',
            'WHATSAPP_PHONE_NUMBER': '+1234567890',
            'WHATSAPP_GROUP_INVITE_CODE': '',
            'WHATSAPP_MESSAGE_HEADER': 'Upwork Alert',
            'EMAIL_NOTIFICATION_SUBJECT_PREFIX': 'Upwork Alert',
            'EMAIL_NOTIFICATION_BODY_INTRO': (
                'New Upwork alert matched your notification rule.'
            ),
            'CHECK_INTERVAL_MINUTES': '5',
            'CONFIG_RELOAD_INTERVAL_SECONDS': '60',
            'MAX_EMAILS_PER_CHECK': '3',
            'KEYWORDS_JOB_ALERT': '',
            'KEYWORDS_MESSAGE_ALERT': '',
            'WHATSAPP_JOB_ALERT_RECIPIENT': '',
            'WHATSAPP_MESSAGE_ALERT_RECIPIENT': '',
            'KEYWORDS_TO_MONITOR': 'alert,message',
            'MONITOR_SPECIFIC_SENDERS': '',
            'NOTIFICATION_STATE_FILE': os.path.join(
                os.path.dirname(env_path),
                'notification_state.json',
            ),
        }
        values.update(overrides)
        with open(env_path, 'w', encoding='utf-8') as env_file:
            for key, value in values.items():
                env_file.write(f"{key}={value}\n")

    def make_runtime_notifier(self, runtime_config):
        notifier = EmailToWhatsAppNotifier.__new__(EmailToWhatsAppNotifier)
        notifier.config = runtime_config
        notifier.email_monitor = RuntimeConfigFakeEmailMonitor(runtime_config)
        notifier.email_sender = RuntimeConfigFakeEmailSender(runtime_config)
        notifier.whatsapp_sender = RuntimeConfigFakeWhatsAppSender(runtime_config)
        notifier.notification_state = self.make_state()
        notifier.logger = logging.getLogger('test_runtime_config_reload')
        return notifier

    def test_runtime_config_reads_env_file_values(self):
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        env_path = os.path.join(temp_dir.name, '.env')
        self.write_runtime_env(
            env_path,
            WHATSAPP_MESSAGE_HEADER='Initial Alert',
            CONFIG_RELOAD_INTERVAL_SECONDS='90',
            KEYWORDS_JOB_ALERT='job,invite',
            KEYWORDS_MESSAGE_ALERT='message,chat',
            WHATSAPP_JOB_ALERT_RECIPIENT='JobGroupCode',
            WHATSAPP_MESSAGE_ALERT_RECIPIENT='+15551234567',
            KEYWORDS_TO_MONITOR='alpha,beta',
        )

        with patch.dict(os.environ, {}, clear=True):
            runtime_config = config.Config(env_path=env_path)

        self.assertEqual(runtime_config.WHATSAPP_MESSAGE_HEADER, 'Initial Alert')
        self.assertEqual(runtime_config.CONFIG_RELOAD_INTERVAL_SECONDS, 90)
        self.assertEqual(runtime_config.KEYWORDS_JOB_ALERT, ['job', 'invite'])
        self.assertEqual(runtime_config.KEYWORDS_MESSAGE_ALERT, ['message', 'chat'])
        self.assertEqual(runtime_config.WHATSAPP_JOB_ALERT_RECIPIENT, 'JobGroupCode')
        self.assertEqual(runtime_config.WHATSAPP_MESSAGE_ALERT_RECIPIENT, '+15551234567')
        self.assertEqual(runtime_config.KEYWORDS_TO_MONITOR, ['alpha', 'beta'])

    def test_runtime_config_reload_applies_changed_live_values(self):
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        env_path = os.path.join(temp_dir.name, '.env')
        self.write_runtime_env(env_path)

        with patch.dict(os.environ, {}, clear=True):
            runtime_config = config.Config(env_path=env_path)
            notifier = self.make_runtime_notifier(runtime_config)
            self.write_runtime_env(
                env_path,
                WHATSAPP_MESSAGE_HEADER='Updated Alert',
                EMAIL_NOTIFICATION_SUBJECT_PREFIX='Updated Subject',
                EMAIL_NOTIFICATION_BODY_INTRO='Updated intro.',
                NOTIFY_EMAIL_RECIPIENTS='one@example.com,two@example.com',
                CHECK_INTERVAL_MINUTES='2',
                CONFIG_RELOAD_INTERVAL_SECONDS='120',
                MAX_EMAILS_PER_CHECK='7',
                KEYWORDS_JOB_ALERT='job,alert',
                KEYWORDS_MESSAGE_ALERT='client message',
                WHATSAPP_JOB_ALERT_RECIPIENT='JobRouteGroup',
                WHATSAPP_MESSAGE_ALERT_RECIPIENT='MessageRouteGroup',
                KEYWORDS_TO_MONITOR='upwork,proposal',
            )

            changed_keys = notifier.reload_runtime_config(force=True)

        self.assertIn('WHATSAPP_MESSAGE_HEADER', changed_keys)
        self.assertIn('EMAIL_NOTIFICATION_SUBJECT_PREFIX', changed_keys)
        self.assertIn('NOTIFY_EMAIL_RECIPIENTS', changed_keys)
        self.assertEqual(notifier.config.WHATSAPP_MESSAGE_HEADER, 'Updated Alert')
        self.assertEqual(notifier.config.EMAIL_NOTIFICATION_SUBJECT_PREFIX, 'Updated Subject')
        self.assertEqual(notifier.config.EMAIL_NOTIFICATION_BODY_INTRO, 'Updated intro.')
        self.assertEqual(
            notifier.config.NOTIFY_EMAIL_RECIPIENTS,
            ['one@example.com', 'two@example.com'],
        )
        self.assertEqual(notifier.config.CHECK_INTERVAL_MINUTES, 2)
        self.assertEqual(notifier.config.CONFIG_RELOAD_INTERVAL_SECONDS, 120)
        self.assertEqual(notifier.config.MAX_EMAILS_PER_CHECK, 7)
        self.assertEqual(notifier.config.KEYWORDS_JOB_ALERT, ['job', 'alert'])
        self.assertEqual(notifier.config.KEYWORDS_MESSAGE_ALERT, ['client message'])
        self.assertEqual(notifier.config.WHATSAPP_JOB_ALERT_RECIPIENT, 'JobRouteGroup')
        self.assertEqual(
            notifier.config.WHATSAPP_MESSAGE_ALERT_RECIPIENT,
            'MessageRouteGroup',
        )
        self.assertEqual(notifier.config.KEYWORDS_TO_MONITOR, ['upwork', 'proposal'])
        self.assertIs(notifier.email_monitor.config, notifier.config)
        self.assertIs(notifier.email_sender.config, notifier.config)
        self.assertIs(notifier.whatsapp_sender.config, notifier.config)

    def test_runtime_config_reload_keeps_previous_config_when_invalid(self):
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        env_path = os.path.join(temp_dir.name, '.env')
        self.write_runtime_env(env_path, WHATSAPP_MESSAGE_HEADER='Stable Alert')

        with patch.dict(os.environ, {}, clear=True):
            runtime_config = config.Config(env_path=env_path)
            notifier = self.make_runtime_notifier(runtime_config)
            self.write_runtime_env(
                env_path,
                EMAIL_PASSWORD='',
                WHATSAPP_MESSAGE_HEADER='Broken Alert',
            )

            changed_keys = notifier.reload_runtime_config(force=True)

        self.assertEqual(changed_keys, set())
        self.assertEqual(notifier.config.WHATSAPP_MESSAGE_HEADER, 'Stable Alert')
        self.assertEqual(notifier.config.EMAIL_PASSWORD, 'email-password')

    def test_runtime_config_reload_resets_affected_connections(self):
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        env_path = os.path.join(temp_dir.name, '.env')
        self.write_runtime_env(env_path)

        with patch.dict(os.environ, {}, clear=True):
            runtime_config = config.Config(env_path=env_path)
            notifier = self.make_runtime_notifier(runtime_config)
            self.write_runtime_env(
                env_path,
                EMAIL_HOST='imap2.example.com',
                WHATSAPP_HEADLESS='true',
            )

            changed_keys = notifier.reload_runtime_config(force=True)

        self.assertIn('EMAIL_HOST', changed_keys)
        self.assertIn('WHATSAPP_HEADLESS', changed_keys)
        self.assertEqual(notifier.email_monitor.disconnect_count, 1)
        self.assertEqual(notifier.whatsapp_sender.close_count, 1)

    def test_runtime_config_reload_defers_state_file_changes_until_restart(self):
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        env_path = os.path.join(temp_dir.name, '.env')
        original_state_path = os.path.join(temp_dir.name, 'state-one.json')
        next_state_path = os.path.join(temp_dir.name, 'state-two.json')
        self.write_runtime_env(env_path, NOTIFICATION_STATE_FILE=original_state_path)

        with patch.dict(os.environ, {}, clear=True):
            runtime_config = config.Config(env_path=env_path)
            notifier = self.make_runtime_notifier(runtime_config)
            self.write_runtime_env(env_path, NOTIFICATION_STATE_FILE=next_state_path)

            changed_keys = notifier.reload_runtime_config(force=True)

        self.assertNotIn('NOTIFICATION_STATE_FILE', changed_keys)
        self.assertEqual(notifier.config.NOTIFICATION_STATE_FILE, original_state_path)

    def test_scheduler_interval_helpers_use_current_config_values(self):
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        env_path = os.path.join(temp_dir.name, '.env')
        self.write_runtime_env(env_path, CHECK_INTERVAL_MINUTES='0.5')

        with patch.dict(os.environ, {}, clear=True):
            runtime_config = config.Config(env_path=env_path)
            notifier = self.make_runtime_notifier(runtime_config)

        self.assertEqual(notifier._check_interval_seconds(), 30)

    def test_email_notification_is_sent_before_whatsapp(self):
        email = {
            'id': '123',
            'subject': 'Important',
            'sender': 'sender@example.com',
            'date': 'Wed, 03 Jun 2026 09:00:00 +0000',
            'body': 'Body',
        }
        events = []
        email_monitor = FakeEmailMonitor([email])
        email_sender = FakeEmailNotificationSender(events=events)
        whatsapp_sender = FakeWhatsAppSender(send_results=True, events=events)
        notifier = self.make_notifier(email_monitor, whatsapp_sender, email_sender)

        with patch('main.time.sleep', return_value=None):
            notifier.check_emails_and_notify()

        self.assertEqual(events, ['email:123', 'whatsapp:Message for Important'])
        self.assertEqual(email_monitor.marked_seen, ['123'])
        self.assertEqual(email_sender.sent_email_ids, ['123'])
        self.assertEqual(whatsapp_sender.sent_messages, ['Message for Important'])

    def test_message_alert_match_wins_over_job_alert_match(self):
        route_config = type(
            'RouteConfig',
            (),
            {
                'KEYWORDS_MESSAGE_ALERT': ['message', 'sent you a message'],
                'KEYWORDS_JOB_ALERT': ['alert', 'message', 'sent you a message'],
                'KEYWORDS_TO_MONITOR': [],
                'MONITOR_SPECIFIC_SENDERS': [],
            },
        )

        alert_type = EmailMonitor.determine_alert_type(
            {
                'subject': 'A client sent you a message',
                'body': 'New Upwork alert',
                'sender': 'upwork@example.com',
            },
            route_config,
        )

        self.assertEqual(alert_type, 'message_alert')

    def test_job_alert_skips_email_and_sends_whatsapp_only_to_job_recipient(self):
        email = {
            'id': 'job-1',
            'subject': 'New alert matched',
            'sender': 'upwork@example.com',
            'date': 'Wed, 03 Jun 2026 09:00:00 +0000',
            'body': 'A project alert is ready',
        }
        route_config = type(
            'RouteConfig',
            (),
            {
                'WHATSAPP_MAX_RETRIES': 3,
                'WHATSAPP_RETRY_DELAY_SECONDS': 0,
                'NOTIFICATION_DELAY_SECONDS': 0,
                'KEYWORDS_MESSAGE_ALERT': [],
                'KEYWORDS_JOB_ALERT': ['alert'],
                'KEYWORDS_TO_MONITOR': [],
                'MONITOR_SPECIFIC_SENDERS': [],
                'WHATSAPP_JOB_ALERT_RECIPIENT': 'JobGroupCode',
                'WHATSAPP_MESSAGE_ALERT_RECIPIENT': '',
                'WHATSAPP_GROUP_INVITE_CODE': 'GlobalGroupCode',
                'WHATSAPP_PHONE_NUMBER': '+1234567890',
            },
        )
        email_monitor = FakeEmailMonitor([email])
        email_sender = FakeEmailNotificationSender()
        whatsapp_sender = FakeWhatsAppSender(send_results=True)
        state = self.make_state()
        notifier = self.make_notifier(
            email_monitor,
            whatsapp_sender,
            email_sender,
            state,
            route_config,
        )

        notifier.check_emails_and_notify()

        self.assertEqual(email_sender.sent_email_ids, [])
        self.assertEqual(whatsapp_sender.sent_messages, ['Message for New alert matched'])
        self.assertEqual(whatsapp_sender.sent_recipients, ['JobGroupCode'])
        self.assertEqual(email_monitor.marked_seen, ['job-1'])
        self.assertFalse(state.has_email_sent('job-1'))
        self.assertEqual(state.get('job-1')['alert_type'], 'job_alert')
        self.assertEqual(state.get('job-1')['whatsapp_recipient'], 'JobGroupCode')

    def test_message_alert_sends_email_first_and_whatsapp_to_message_recipient(self):
        email = {
            'id': 'msg-1',
            'subject': 'Client sent you a message',
            'sender': 'upwork@example.com',
            'date': 'Wed, 03 Jun 2026 09:00:00 +0000',
            'body': 'Please review this message',
        }
        events = []
        route_config = type(
            'RouteConfig',
            (),
            {
                'WHATSAPP_MAX_RETRIES': 3,
                'WHATSAPP_RETRY_DELAY_SECONDS': 0,
                'NOTIFICATION_DELAY_SECONDS': 0,
                'KEYWORDS_MESSAGE_ALERT': ['message'],
                'KEYWORDS_JOB_ALERT': ['alert', 'message'],
                'KEYWORDS_TO_MONITOR': [],
                'MONITOR_SPECIFIC_SENDERS': [],
                'WHATSAPP_JOB_ALERT_RECIPIENT': 'JobGroupCode',
                'WHATSAPP_MESSAGE_ALERT_RECIPIENT': 'MessageGroupCode',
                'WHATSAPP_GROUP_INVITE_CODE': 'GlobalGroupCode',
                'WHATSAPP_PHONE_NUMBER': '+1234567890',
            },
        )
        email_sender = FakeEmailNotificationSender(events=events)
        whatsapp_sender = FakeWhatsAppSender(send_results=True, events=events)
        notifier = self.make_notifier(
            FakeEmailMonitor([email]),
            whatsapp_sender,
            email_sender,
            config=route_config,
        )

        notifier.check_emails_and_notify()

        self.assertEqual(events, ['email:msg-1', 'whatsapp:Message for Client sent you a message'])
        self.assertEqual(email_sender.sent_email_ids, ['msg-1'])
        self.assertEqual(whatsapp_sender.sent_recipients, ['MessageGroupCode'])

    def test_empty_route_recipient_falls_back_to_global_whatsapp_target(self):
        email = {
            'id': 'job-2',
            'subject': 'Project alert',
            'sender': 'upwork@example.com',
            'date': 'Wed, 03 Jun 2026 09:00:00 +0000',
            'body': 'Body',
        }
        route_config = type(
            'RouteConfig',
            (),
            {
                'WHATSAPP_MAX_RETRIES': 3,
                'WHATSAPP_RETRY_DELAY_SECONDS': 0,
                'NOTIFICATION_DELAY_SECONDS': 0,
                'KEYWORDS_MESSAGE_ALERT': [],
                'KEYWORDS_JOB_ALERT': ['alert'],
                'KEYWORDS_TO_MONITOR': [],
                'MONITOR_SPECIFIC_SENDERS': [],
                'WHATSAPP_JOB_ALERT_RECIPIENT': '',
                'WHATSAPP_MESSAGE_ALERT_RECIPIENT': '',
                'WHATSAPP_GROUP_INVITE_CODE': 'GlobalGroupCode',
                'WHATSAPP_PHONE_NUMBER': '+1234567890',
            },
        )
        whatsapp_sender = FakeWhatsAppSender(send_results=True)
        notifier = self.make_notifier(
            FakeEmailMonitor([email]),
            whatsapp_sender,
            FakeEmailNotificationSender(),
            config=route_config,
        )

        notifier.check_emails_and_notify()

        self.assertEqual(whatsapp_sender.sent_recipients, ['GlobalGroupCode'])

    def test_whatsapp_only_job_alert_failure_queues_retry_without_email_state(self):
        email = {
            'id': 'job-3',
            'subject': 'Project alert',
            'sender': 'upwork@example.com',
            'date': 'Wed, 03 Jun 2026 09:00:00 +0000',
            'body': 'Body',
        }
        route_config = type(
            'RouteConfig',
            (),
            {
                'WHATSAPP_MAX_RETRIES': 3,
                'WHATSAPP_RETRY_DELAY_SECONDS': 0,
                'NOTIFICATION_DELAY_SECONDS': 0,
                'KEYWORDS_MESSAGE_ALERT': [],
                'KEYWORDS_JOB_ALERT': ['alert'],
                'KEYWORDS_TO_MONITOR': [],
                'MONITOR_SPECIFIC_SENDERS': [],
                'WHATSAPP_JOB_ALERT_RECIPIENT': 'JobGroupCode',
                'WHATSAPP_MESSAGE_ALERT_RECIPIENT': '',
                'WHATSAPP_GROUP_INVITE_CODE': 'GlobalGroupCode',
                'WHATSAPP_PHONE_NUMBER': '+1234567890',
            },
        )
        email_sender = FakeEmailNotificationSender()
        whatsapp_sender = FakeWhatsAppSender(send_results=False)
        state = self.make_state()
        notifier = self.make_notifier(
            FakeEmailMonitor([email]),
            whatsapp_sender,
            email_sender,
            state,
            route_config,
        )

        notifier.check_emails_and_notify()

        entry = state.get('job-3')
        due_entries = state.get_due_whatsapp_notifications(max_retries=3)

        self.assertEqual(email_sender.sent_email_ids, [])
        self.assertEqual(entry['status'], 'queued')
        self.assertFalse(entry.get('email_sent', False))
        self.assertFalse(entry['email_required'])
        self.assertEqual(entry['whatsapp_recipient'], 'JobGroupCode')
        self.assertEqual([item['email_data']['id'] for item in due_entries], ['job-3'])

    def test_email_notification_message_uses_configured_subject_and_intro(self):
        sender = self.make_email_notification_sender()
        email = {
            'subject': 'Testing Email Automation',
            'sender': 'sender@example.com',
            'date': 'Wed, 03 Jun 2026 09:00:00 +0000',
            'body': 'Preview body',
        }

        message = sender._build_message(email)

        self.assertEqual(
            message['Subject'],
            'Upwork Alert: Testing Email Automation',
        )
        self.assertTrue(
            message.get_content().startswith(
                'New Upwork alert matched your notification rule.\n\n'
            )
        )

    def test_email_notification_message_allows_custom_subject_and_intro(self):
        sender = self.make_email_notification_sender()
        sender.config.EMAIL_NOTIFICATION_SUBJECT_PREFIX = 'Custom Alert'
        sender.config.EMAIL_NOTIFICATION_BODY_INTRO = 'Custom intro text.'

        message = sender._build_message(
            {
                'subject': 'Project Match',
                'sender': 'sender@example.com',
                'date': 'Wed, 03 Jun 2026 09:00:00 +0000',
                'body': 'Preview body',
            }
        )

        self.assertEqual(message['Subject'], 'Custom Alert: Project Match')
        self.assertTrue(message.get_content().startswith('Custom intro text.\n\n'))

    def test_email_notification_flattens_newlines_in_headers(self):
        sender = self.make_email_notification_sender()
        sender.config.EMAIL_NOTIFICATION_SUBJECT_PREFIX = 'Upwork\nAlert'
        sender.config.NOTIFY_EMAIL_RECIPIENTS = ['recipient@example.com\r\n']
        email = {
            'subject': 'Great news! Your client approved java spring\n boot APIs',
            'sender': 'Sender Name\n<sender@example.com>',
            'date': 'Wed,\n 04 Jun 2026 03:52:00 +0500',
            'body': 'Preview body',
        }

        message = sender._build_message(email)
        content = message.get_content()

        self.assertEqual(
            message['Subject'],
            'Upwork Alert: Great news! Your client approved java spring boot APIs',
        )
        self.assertNotIn('\n', message['Subject'])
        self.assertNotIn('\r', message['Subject'])
        self.assertEqual(message['To'], 'recipient@example.com')
        self.assertIn('From: Sender Name <sender@example.com>', content)
        self.assertIn(
            'Subject: Great news! Your client approved java spring boot APIs',
            content,
        )

    def test_email_success_and_whatsapp_failure_queues_retry_without_resending_email(self):
        email = {
            'id': '456',
            'subject': 'Retry later',
            'sender': 'sender@example.com',
            'date': 'Wed, 03 Jun 2026 09:00:00 +0000',
            'body': 'Body',
        }
        email_monitor = FakeEmailMonitor([email])
        email_sender = FakeEmailNotificationSender()
        whatsapp_sender = FakeWhatsAppSender(send_results=[False, False])
        state = self.make_state()
        notifier = self.make_notifier(email_monitor, whatsapp_sender, email_sender, state)

        with patch('main.time.sleep', return_value=None):
            notifier.check_emails_and_notify()
            notifier.check_emails_and_notify()

        self.assertEqual(email_monitor.marked_seen, [])
        self.assertEqual(email_sender.sent_email_ids, ['456'])
        self.assertEqual(
            whatsapp_sender.sent_messages,
            ['Message for Retry later', 'Message for Retry later'],
        )
        self.assertTrue(state.has_email_sent('456'))
        self.assertEqual(state.get('456')['status'], 'queued')
        self.assertEqual(state.get('456')['attempt_count'], 2)

    def test_due_whatsapp_retry_uses_current_message_formatter(self):
        email = {
            'id': '654',
            'subject': 'Pending retry',
            'sender': 'sender@example.com',
            'date': 'Wed, 03 Jun 2026 09:00:00 +0000',
            'body': 'Body',
        }
        state = self.make_state()
        state.record_email_sent(email, 'Old Header: Pending retry')

        class DynamicWhatsAppSender(FakeWhatsAppSender):
            def __init__(self):
                super().__init__(send_results=True)
                self.config = type(
                    'DynamicConfig',
                    (),
                    {'WHATSAPP_MESSAGE_HEADER': 'Current Header'},
                )

            def format_email_message(self, email_data):
                return (
                    f"{self.config.WHATSAPP_MESSAGE_HEADER}: "
                    f"{email_data['subject']}"
                )

        notifier = self.make_notifier(
            FakeEmailMonitor([]),
            DynamicWhatsAppSender(),
            notification_state=state,
            config=type(
                'TestConfig',
                (),
                {
                    'WHATSAPP_MAX_RETRIES': 3,
                    'WHATSAPP_RETRY_DELAY_SECONDS': 0,
                    'NOTIFICATION_DELAY_SECONDS': 0,
                },
            ),
        )

        notifier.process_due_whatsapp_retries()

        self.assertEqual(
            notifier.whatsapp_sender.sent_messages,
            ['Current Header: Pending retry'],
        )

    def test_whatsapp_success_marks_email_as_seen(self):
        email = {
            'id': '777',
            'subject': 'Done',
            'sender': 'sender@example.com',
            'date': 'Wed, 03 Jun 2026 09:00:00 +0000',
            'body': 'Body',
        }
        email_monitor = FakeEmailMonitor([email])
        whatsapp_sender = FakeWhatsAppSender(send_results=True)
        state = self.make_state()
        notifier = self.make_notifier(
            email_monitor,
            whatsapp_sender,
            FakeEmailNotificationSender(),
            state,
        )

        notifier.check_emails_and_notify()

        self.assertEqual(email_monitor.marked_seen, ['777'])
        self.assertEqual(state.get('777')['status'], 'sent')

    def test_exhausted_whatsapp_retries_mark_email_as_seen_after_email_delivery(self):
        email = {
            'id': '888',
            'subject': 'Exhaust retries',
            'sender': 'sender@example.com',
            'date': 'Wed, 03 Jun 2026 09:00:00 +0000',
            'body': 'Body',
        }
        config = type(
            'TestConfig',
            (),
            {
                'WHATSAPP_MAX_RETRIES': 1,
                'WHATSAPP_RETRY_DELAY_SECONDS': 0,
                'NOTIFICATION_DELAY_SECONDS': 0,
            },
        )
        email_monitor = FakeEmailMonitor([email])
        whatsapp_sender = FakeWhatsAppSender(send_results=False)
        state = self.make_state()
        notifier = self.make_notifier(
            email_monitor,
            whatsapp_sender,
            FakeEmailNotificationSender(),
            state,
            config,
        )

        notifier.check_emails_and_notify()

        self.assertEqual(email_monitor.marked_seen, ['888'])
        self.assertEqual(state.get('888')['status'], 'exhausted')

    def test_email_failure_does_not_attempt_whatsapp_or_mark_seen(self):
        email = {
            'id': '999',
            'subject': 'SMTP down',
            'sender': 'sender@example.com',
            'date': 'Wed, 03 Jun 2026 09:00:00 +0000',
            'body': 'Body',
        }
        email_monitor = FakeEmailMonitor([email])
        email_sender = FakeEmailNotificationSender(send_result=False)
        whatsapp_sender = FakeWhatsAppSender(send_results=True)
        notifier = self.make_notifier(email_monitor, whatsapp_sender, email_sender)

        notifier.check_emails_and_notify()

        self.assertEqual(email_monitor.marked_seen, [])
        self.assertEqual(whatsapp_sender.sent_messages, [])

    def test_filtered_out_email_is_not_marked_seen_during_fetch(self):
        monitor = self.make_email_monitor(FakeIMAPConnection())
        monitor.config = type(
            'TestConfig',
            (),
            {
                'MONITOR_SPECIFIC_SENDERS': ['boss@example.com'],
                'KEYWORDS_TO_MONITOR': [],
                'MAX_EMAILS_PER_CHECK': 3,
                'EMAIL_SCAN_MULTIPLIER': 5,
            },
        )

        emails = monitor.get_new_emails()

        self.assertEqual(emails, [])
        self.assertNotIn(
            'STORE',
            [command for command, _ in monitor.connection.uid_calls],
        )

    def test_email_monitor_respects_max_emails_per_check(self):
        connection = FakeIMAPConnection(search_response=b'101 102 103 104 105')
        monitor = self.make_email_monitor(connection)
        monitor.config = type(
            'TestConfig',
            (),
            {
                'MONITOR_SPECIFIC_SENDERS': [],
                'KEYWORDS_TO_MONITOR': [],
                'MAX_EMAILS_PER_CHECK': 2,
                'EMAIL_SCAN_MULTIPLIER': 5,
            },
        )

        emails = monitor.get_new_emails()
        fetched_uids = [
            args[0]
            for command, args in connection.uid_calls
            if command == 'FETCH'
        ]

        self.assertEqual(len(emails), 2)
        self.assertEqual(fetched_uids, ['105', '104'])

    def test_email_monitor_can_fetch_more_than_default_limit_when_configured(self):
        connection = FakeIMAPConnection(search_response=b'101 102 103 104 105')
        monitor = self.make_email_monitor(connection)
        monitor.config = type(
            'TestConfig',
            (),
            {
                'MONITOR_SPECIFIC_SENDERS': [],
                'KEYWORDS_TO_MONITOR': [],
                'MAX_EMAILS_PER_CHECK': 5,
                'EMAIL_SCAN_MULTIPLIER': 5,
            },
        )

        emails = monitor.get_new_emails()
        fetched_uids = [
            args[0]
            for command, args in connection.uid_calls
            if command == 'FETCH'
        ]

        self.assertEqual(len(emails), 5)
        self.assertEqual(fetched_uids, ['105', '104', '103', '102', '101'])

    def test_email_monitor_scans_past_batch_limit_for_matching_email(self):
        connection = FakeIMAPConnection(
            search_response=b'101 102 103 104 105',
            fetch_messages={
                '105': build_raw_email(subject='Noise 5', sender='other@example.com'),
                '104': build_raw_email(subject='Noise 4', sender='other@example.com'),
                '103': build_raw_email(subject='Important', sender='Boss <boss@example.com>'),
            },
        )
        monitor = self.make_email_monitor(connection)
        monitor.config = type(
            'TestConfig',
            (),
            {
                'MONITOR_SPECIFIC_SENDERS': ['boss@example.com'],
                'KEYWORDS_TO_MONITOR': [],
                'MAX_EMAILS_PER_CHECK': 1,
                'EMAIL_SCAN_MULTIPLIER': 5,
            },
        )

        emails = monitor.get_new_emails()
        fetched_uids = [
            args[0]
            for command, args in connection.uid_calls
            if command == 'FETCH'
        ]
        search_args = [
            args
            for command, args in connection.uid_calls
            if command == 'SEARCH'
        ][0]

        self.assertEqual([email['id'] for email in emails], ['103'])
        self.assertEqual(fetched_uids, ['105', '104', '103'])
        self.assertIn('UNSEEN', search_args)
        self.assertIn('SINCE', search_args)

    def test_mark_email_as_seen_returns_true_for_ok_store(self):
        monitor = self.make_email_monitor(FakeIMAPConnection(store_status='OK'))

        result = monitor.mark_email_as_seen('789')

        self.assertTrue(result)
        self.assertIn(
            ('STORE', ('789', '+FLAGS.SILENT', r'(\Seen)')),
            monitor.connection.uid_calls,
        )

    def test_mark_email_as_seen_returns_false_for_non_ok_store(self):
        monitor = self.make_email_monitor(FakeIMAPConnection(store_status='NO'))

        result = monitor.mark_email_as_seen('789')

        self.assertFalse(result)
        self.assertIn(
            ('STORE', ('789', '+FLAGS.SILENT', r'(\Seen)')),
            monitor.connection.uid_calls,
        )

    def make_whatsapp_sender(self):
        sender = WhatsAppSender.__new__(WhatsAppSender)
        sender.config = type(
            'TestConfig',
            (),
            {
                'WHATSAPP_PHONE_NUMBER': '+1234567890',
                'WHATSAPP_GROUP_INVITE_CODE': '',
                'WHATSAPP_JOB_ALERT_RECIPIENT': '',
                'WHATSAPP_MESSAGE_ALERT_RECIPIENT': '',
                'WHATSAPP_CHROME_PROFILE_DIR': '.whatsapp_chrome_profile',
                'WHATSAPP_WAIT_SECONDS': 1,
                'WHATSAPP_HEADLESS': False,
                'WHATSAPP_HEADLESS_WINDOW_SIZE': '1280,900',
                'WHATSAPP_DEBUG_SCREENSHOT_DIR': 'debug_screenshots',
                'WHATSAPP_MESSAGE_HEADER': 'Upwork Alert',
                'CHROME_BINARY_PATH': None,
            },
        )
        sender.logger = logging.getLogger('test_whatsapp_sender')
        sender.driver = None
        return sender

    def test_chrome_options_use_configured_profile_dir(self):
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        sender = self.make_whatsapp_sender()
        sender.config.WHATSAPP_CHROME_PROFILE_DIR = temp_dir.name

        options = sender._build_chrome_options()

        self.assertIn(f"--user-data-dir={os.path.abspath(temp_dir.name)}", options.arguments)

    def test_bool_env_parsing_accepts_true_and_false_values(self):
        with patch.dict(os.environ, {'TEST_BOOL': 'yes'}):
            self.assertTrue(config.get_bool_env('TEST_BOOL'))

        with patch.dict(os.environ, {'TEST_BOOL': 'off'}):
            self.assertFalse(config.get_bool_env('TEST_BOOL', default=True))

        with patch.dict(os.environ, {'TEST_BOOL': 'not-a-bool'}):
            self.assertTrue(config.get_bool_env('TEST_BOOL', default=True))

    def test_headed_chrome_options_do_not_include_headless_flags(self):
        sender = self.make_whatsapp_sender()

        options = sender._build_chrome_options()

        self.assertNotIn('--headless=new', options.arguments)
        self.assertNotIn('--window-size=1280,900', options.arguments)
        self.assertIn('--start-maximized', options.arguments)
        self.assertIn('--profile-directory=Default', options.arguments)

    def test_headless_chrome_options_include_headless_window_and_profile(self):
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        sender = self.make_whatsapp_sender()
        sender.config.WHATSAPP_HEADLESS = True
        sender.config.WHATSAPP_HEADLESS_WINDOW_SIZE = '1440,1000'
        sender.config.WHATSAPP_CHROME_PROFILE_DIR = temp_dir.name

        options = sender._build_chrome_options()

        self.assertIn('--headless=new', options.arguments)
        self.assertIn('--window-size=1440,1000', options.arguments)
        self.assertNotIn('--start-maximized', options.arguments)
        self.assertIn(f"--user-data-dir={os.path.abspath(temp_dir.name)}", options.arguments)
        self.assertIn('--profile-directory=Default', options.arguments)

    def test_invalid_headless_window_size_uses_default(self):
        sender = self.make_whatsapp_sender()
        sender.config.WHATSAPP_HEADLESS_WINDOW_SIZE = 'wide,tall'

        self.assertEqual(sender._headless_window_size(), '1280,900')

    def test_debug_screenshot_is_saved_only_in_headless_mode(self):
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        sender = self.make_whatsapp_sender()
        sender.config.WHATSAPP_DEBUG_SCREENSHOT_DIR = temp_dir.name
        screenshot_calls = []

        class FakeDriver:
            def save_screenshot(self, path):
                screenshot_calls.append(path)
                with open(path, 'wb') as screenshot:
                    screenshot.write(b'fake image')
                return True

        headed_result = sender._capture_debug_screenshot(FakeDriver(), 'headed-failure')
        sender.config.WHATSAPP_HEADLESS = True
        headless_result = sender._capture_debug_screenshot(FakeDriver(), 'headless-failure')

        self.assertIsNone(headed_result)
        self.assertIsNotNone(headless_result)
        self.assertEqual(len(screenshot_calls), 1)
        self.assertTrue(os.path.exists(screenshot_calls[0]))

    def test_debug_screenshot_skips_empty_directory(self):
        sender = self.make_whatsapp_sender()
        sender.config.WHATSAPP_HEADLESS = True
        sender.config.WHATSAPP_DEBUG_SCREENSHOT_DIR = ''

        class FakeDriver:
            def save_screenshot(self, path):
                raise AssertionError('save_screenshot should not be called')

        self.assertIsNone(sender._capture_debug_screenshot(FakeDriver(), 'failure'))

    def test_click_send_button_clicks_real_button(self):
        sender = self.make_whatsapp_sender()
        clicked = []

        class FakeButton:
            def click(self):
                clicked.append(True)

        class FakeWait:
            def __init__(self, *args, **kwargs):
                pass

            def until(self, condition):
                return FakeButton()

        with patch.object(whatsapp_sender, 'WebDriverWait', FakeWait):
            sender._click_send_button(driver=object())

        self.assertEqual(clicked, [True])

    def test_group_invite_url_overrides_phone_chat_url(self):
        sender = self.make_whatsapp_sender()
        sender.config.WHATSAPP_GROUP_INVITE_CODE = (
            'https://web.whatsapp.com/accept?code=GroupInvite123&utm_campaign=wa_chat_v2'
        )

        url = sender._build_chat_url('hello group')

        self.assertEqual(
            url,
            'https://web.whatsapp.com/accept?code=GroupInvite123',
        )

    def test_recipient_override_builds_group_or_phone_chat_url(self):
        sender = self.make_whatsapp_sender()

        group_url = sender._build_chat_url(
            'hello group',
            recipient='https://web.whatsapp.com/accept?code=RouteGroup123&utm_campaign=wa_chat_v2',
        )
        phone_url = sender._build_chat_url('hello phone', recipient='+1 555 123 4567')

        self.assertEqual(
            group_url,
            'https://web.whatsapp.com/accept?code=RouteGroup123',
        )
        self.assertEqual(
            phone_url,
            'https://web.whatsapp.com/send?phone=15551234567&text=hello%20phone',
        )

    def test_group_invite_code_allows_whatsapp_validation_without_phone(self):
        sender = self.make_whatsapp_sender()
        sender.config.WHATSAPP_PHONE_NUMBER = ''
        sender.config.WHATSAPP_GROUP_INVITE_CODE = 'GroupInvite123'

        self.assertTrue(sender.validate_phone_number())

    def test_draft_keyboard_fallback_strips_non_bmp_characters(self):
        sender = self.make_whatsapp_sender()
        test_case = self

        class FakeComposeBox:
            text = ''

            def __init__(self):
                self.sent_keys = []

            def click(self):
                pass

            def get_attribute(self, name):
                return self.text if name == 'innerText' else ''

            def send_keys(self, *keys):
                self.sent_keys.extend(keys)
                for key in keys:
                    if isinstance(key, str):
                        test_case.assertTrue(all(ord(char) <= 0xFFFF for char in key))

        class FakeDriver:
            def execute_script(self, *args):
                pass

        compose_box = FakeComposeBox()
        draft_message = sender._ensure_draft_message(
            FakeDriver(),
            compose_box,
            '📧 New Email\nPreview',
        )

        self.assertEqual(draft_message, 'New Email\nPreview')
        self.assertNotIn('📧', ''.join(compose_box.sent_keys))

    def test_format_email_message_removes_non_bmp_characters(self):
        sender = self.make_whatsapp_sender()

        message = sender.format_email_message(
            {
                'subject': 'Testing 🚀',
                'sender': 'Sender 😀 <sender@example.com>',
                'body': 'Body with 📧 emoji',
            }
        )

        self.assertIn('Upwork Alert', message)
        self.assertIn('Testing', message)
        self.assertIn('Sender  <sender@example.com>', message)
        self.assertIn('Body with emoji', message)
        self.assertNotIn('📧', message)
        self.assertTrue(all(ord(char) <= 0xFFFF for char in message))

    def test_format_email_message_uses_configured_header(self):
        sender = self.make_whatsapp_sender()
        sender.config.WHATSAPP_MESSAGE_HEADER = 'Custom Header 🚀'

        message = sender.format_email_message(
            {
                'subject': 'Testing',
                'sender': 'sender@example.com',
                'body': 'Body',
            }
        )

        self.assertTrue(message.startswith('Custom Header\n\n'))
        self.assertNotIn('🚀', message)

    def test_sanitize_message_for_whatsapp_removes_non_bmp_characters(self):
        sender = self.make_whatsapp_sender()

        self.assertEqual(
            sender._sanitize_message_for_whatsapp('Hello 📧 there 🚀'),
            'Hello  there',
        )

    def test_bmp_chromedriver_error_is_not_treated_as_fatal(self):
        error = whatsapp_sender.WebDriverException(
            'unknown error: ChromeDriver only supports characters in the BMP'
        )

        self.assertFalse(WhatsAppSender._is_fatal_driver_error(error))

    def test_dead_browser_error_is_treated_as_fatal(self):
        error = whatsapp_sender.WebDriverException('chrome not reachable')

        self.assertTrue(WhatsAppSender._is_fatal_driver_error(error))


if __name__ == '__main__':
    unittest.main()
