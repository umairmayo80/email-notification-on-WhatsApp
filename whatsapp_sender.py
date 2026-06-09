from __future__ import annotations

import logging
import os
import time
from datetime import datetime
from typing import Dict, Optional
from urllib.parse import parse_qs, quote, urlparse

from config import Config

try:
    from selenium import webdriver
    from selenium.common.exceptions import (
        StaleElementReferenceException,
        TimeoutException,
        WebDriverException,
    )
    from selenium.webdriver import ChromeOptions
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import WebDriverWait

    SELENIUM_AVAILABLE = True
except Exception as e:
    print(f"Warning: selenium not available: {e}")
    SELENIUM_AVAILABLE = False


class WhatsAppSender:
    SEND_BUTTON_XPATH = (
        "//button[@aria-label='Send' or @data-testid='compose-btn-send' "
        "or .//span[@data-icon='send']]"
    )
    COMPOSE_BOX_XPATH = "//footer//div[@contenteditable='true']"

    def __init__(self, config=None):
        self.config = config or Config()
        self.logger = logging.getLogger(__name__)
        self.driver = None

    def send_message(
        self,
        message: str,
        instant: bool = True,
        recipient: Optional[str] = None,
    ) -> bool:
        """
        Send a WhatsApp message with Selenium and a dedicated Chrome profile.

        The instant argument is kept for compatibility with the old PyWhatKit
        interface; Selenium always sends as soon as WhatsApp Web is ready.
        """
        if not instant:
            self.logger.info("Scheduled mode is no longer needed; sending immediately")

        if not SELENIUM_AVAILABLE:
            self.logger.error("selenium is not available")
            return False

        message = self._sanitize_message_for_whatsapp(message)
        if not message:
            self.logger.error("WhatsApp message is empty after removing unsupported characters")
            return False

        try:
            self.logger.info("Sending WhatsApp message through WhatsApp Web...")
            driver = self._get_driver()
            driver.get(self._build_chat_url(message, recipient=recipient))

            compose_box = self._wait_for_compose_box(driver)
            draft_message = self._ensure_draft_message(driver, compose_box, message)

            for attempt in range(2):
                self._click_send_button(driver)
                time.sleep(1)
                if self._message_left_draft(driver, draft_message):
                    self.logger.info("WhatsApp message sent and draft cleared")
                    return True
                self.logger.warning("WhatsApp draft still present after send click; retrying click")

            self.logger.error("WhatsApp message appears to be stuck in the draft box")
            self._capture_debug_screenshot(driver, 'draft-stuck')
            return False

        except TimeoutException:
            self.logger.error("Timed out waiting for WhatsApp Web to become ready")
            self._capture_debug_screenshot(self.driver, 'timeout')
            return False
        except WebDriverException as e:
            self.logger.error("WhatsApp browser automation failed: %s", str(e))
            self._capture_debug_screenshot(self.driver, 'webdriver-error')
            if self._is_fatal_driver_error(e):
                self.close()
            return False
        except Exception as e:
            self.logger.error("Failed to send WhatsApp message: %s", str(e))
            self._capture_debug_screenshot(self.driver, 'unexpected-error')
            return False

    def send_immediate_message(self, message: str, recipient: Optional[str] = None) -> bool:
        """Send a WhatsApp message immediately."""
        return self.send_message(message, instant=True, recipient=recipient)

    def close(self):
        """Close the Selenium browser when the application stops."""
        if self.driver:
            try:
                self.driver.quit()
            except Exception as e:
                self.logger.warning("Error closing WhatsApp browser: %s", str(e))
            finally:
                self.driver = None

    def _get_driver(self):
        if self.driver:
            try:
                _ = self.driver.current_url
                return self.driver
            except WebDriverException:
                self.driver = None

        self.driver = webdriver.Chrome(options=self._build_chrome_options())
        return self.driver

    def _build_chrome_options(self) -> ChromeOptions:
        options = ChromeOptions()
        profile_dir = os.path.abspath(self.config.WHATSAPP_CHROME_PROFILE_DIR)
        os.makedirs(profile_dir, exist_ok=True)

        options.add_argument(f"--user-data-dir={profile_dir}")
        options.add_argument("--profile-directory=Default")
        options.add_argument("--no-first-run")
        options.add_argument("--disable-popup-blocking")

        if self.config.WHATSAPP_HEADLESS:
            options.add_argument("--headless=new")
            options.add_argument(f"--window-size={self._headless_window_size()}")
        else:
            options.add_argument("--start-maximized")

        if self.config.CHROME_BINARY_PATH:
            options.binary_location = self.config.CHROME_BINARY_PATH

        return options

    def _headless_window_size(self) -> str:
        configured_size = getattr(self.config, 'WHATSAPP_HEADLESS_WINDOW_SIZE', '')
        normalized = configured_size.lower().replace('x', ',')
        parts = [part.strip() for part in normalized.split(',') if part.strip()]

        if len(parts) != 2:
            return '1280,900'

        try:
            width, height = (int(parts[0]), int(parts[1]))
        except ValueError:
            return '1280,900'

        if width <= 0 or height <= 0:
            return '1280,900'

        return f"{width},{height}"

    def _capture_debug_screenshot(self, driver, reason: str) -> Optional[str]:
        if not getattr(self.config, 'WHATSAPP_HEADLESS', False):
            return None

        screenshot_dir = getattr(self.config, 'WHATSAPP_DEBUG_SCREENSHOT_DIR', '').strip()
        if not screenshot_dir or not driver:
            return None

        try:
            os.makedirs(screenshot_dir, exist_ok=True)
            timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
            safe_reason = ''.join(
                char if char.isalnum() or char in ('-', '_') else '-'
                for char in reason
            ).strip('-') or 'failure'
            screenshot_path = os.path.join(
                screenshot_dir,
                f"whatsapp-{safe_reason}-{timestamp}.png",
            )
            driver.save_screenshot(screenshot_path)
            self.logger.info("Saved WhatsApp debug screenshot: %s", screenshot_path)
            return screenshot_path
        except Exception as e:
            self.logger.warning("Could not save WhatsApp debug screenshot: %s", str(e))
            return None

    def _build_chat_url(self, message: str, recipient: Optional[str] = None) -> str:
        recipient = (recipient or '').strip()
        if recipient:
            if self._is_phone_recipient(recipient):
                phone = self._phone_digits(recipient)
                return f"https://web.whatsapp.com/send?phone={phone}&text={quote(message)}"

            group_code = self._get_group_invite_code(recipient)
            return f"https://web.whatsapp.com/accept?code={quote(group_code)}"

        group_code = self._get_group_invite_code()
        if group_code:
            return f"https://web.whatsapp.com/accept?code={quote(group_code)}"

        phone = self._phone_digits(self.config.WHATSAPP_PHONE_NUMBER or '')
        return f"https://web.whatsapp.com/send?phone={phone}&text={quote(message)}"

    def _get_group_invite_code(self, raw_code: Optional[str] = None) -> str:
        if raw_code is None:
            raw_code = getattr(self.config, 'WHATSAPP_GROUP_INVITE_CODE', '')
        raw_code = (raw_code or '').strip()
        if not raw_code:
            return ''

        parsed = urlparse(raw_code)
        query_code = parse_qs(parsed.query).get('code', [''])[0]
        if query_code:
            return query_code.strip()

        path_parts = [part for part in parsed.path.split('/') if part]
        if path_parts:
            return path_parts[-1].strip()

        return raw_code.rstrip('/').split('/')[-1].strip()

    @staticmethod
    def _phone_digits(recipient: str) -> str:
        return ''.join(char for char in (recipient or '') if char.isdigit())

    @classmethod
    def _is_phone_recipient(cls, recipient: str) -> bool:
        normalized = (recipient or '').strip().replace(' ', '')
        if not normalized:
            return False
        if normalized.startswith('+'):
            return normalized[1:].isdigit()
        return normalized.isdigit()

    @classmethod
    def is_valid_recipient(cls, recipient: Optional[str]) -> bool:
        recipient = (recipient or '').strip()
        if not recipient:
            return False
        if recipient.startswith('+'):
            return cls._is_phone_recipient(recipient)
        return True

    def _wait_for_compose_box(self, driver):
        wait = WebDriverWait(driver, self.config.WHATSAPP_WAIT_SECONDS)
        return wait.until(lambda current_driver: self._find_visible_compose_box(current_driver))

    def _find_visible_compose_box(self, driver):
        boxes = driver.find_elements(By.XPATH, self.COMPOSE_BOX_XPATH)
        visible_boxes = [box for box in boxes if box.is_displayed()]
        return visible_boxes[-1] if visible_boxes else False

    def _ensure_draft_message(self, driver, compose_box, message: str) -> str:
        draft_text = self._element_text(compose_box)
        if self._normalize(message) in self._normalize(draft_text):
            return message

        self.logger.info("WhatsApp URL did not populate the full draft; typing message")
        compose_box.click()
        driver.execute_script(
            """
            const box = arguments[0];
            const text = arguments[1];
            box.focus();
            const selection = window.getSelection();
            const range = document.createRange();
            range.selectNodeContents(box);
            selection.removeAllRanges();
            selection.addRange(range);
            document.execCommand('insertText', false, text);
            box.dispatchEvent(new Event('input', { bubbles: true }));
            """,
            compose_box,
            message,
        )

        draft_text = self._element_text(compose_box)
        if self._normalize(message) in self._normalize(draft_text):
            return message

        safe_message = self._chromedriver_safe_text(message)
        if safe_message != message:
            self.logger.warning(
                "Message contains characters ChromeDriver cannot type; "
                "using keyboard-safe fallback text"
            )

        if not safe_message:
            raise WebDriverException("Message cannot be typed by ChromeDriver")

        compose_box.send_keys(Keys.CONTROL, 'a')
        compose_box.send_keys(Keys.BACKSPACE)
        lines = safe_message.splitlines() or ['']
        for index, line in enumerate(lines):
            if line:
                compose_box.send_keys(line)
            if index < len(lines) - 1:
                compose_box.send_keys(Keys.SHIFT, Keys.ENTER)

        return safe_message

    def _click_send_button(self, driver):
        wait = WebDriverWait(driver, self.config.WHATSAPP_WAIT_SECONDS)
        send_button = wait.until(
            EC.element_to_be_clickable((By.XPATH, self.SEND_BUTTON_XPATH))
        )

        try:
            send_button.click()
        except WebDriverException:
            driver.execute_script("arguments[0].click();", send_button)

    def _message_left_draft(self, driver, message: str) -> bool:
        end_time = time.time() + 10
        expected = self._normalize(message)

        while time.time() < end_time:
            try:
                compose_box = self._find_visible_compose_box(driver)
                draft_text = self._element_text(compose_box) if compose_box else ''
                if expected not in self._normalize(draft_text):
                    return True
            except StaleElementReferenceException:
                return True
            time.sleep(0.5)

        return False

    @staticmethod
    def _element_text(element) -> str:
        if not element:
            return ''
        return element.get_attribute('innerText') or element.text or ''

    @staticmethod
    def _normalize(value: Optional[str]) -> str:
        return ' '.join((value or '').split())

    @staticmethod
    def _chromedriver_safe_text(value: str) -> str:
        """Remove non-BMP characters because ChromeDriver cannot send_keys them."""
        return ''.join(char for char in value if ord(char) <= 0xFFFF).strip()

    @classmethod
    def _sanitize_message_for_whatsapp(cls, value: str) -> str:
        """Remove characters that ChromeDriver cannot type in fallback mode."""
        return cls._chromedriver_safe_text(value)

    @staticmethod
    def _is_fatal_driver_error(error: WebDriverException) -> bool:
        message = str(error).lower()
        fatal_markers = (
            'chrome not reachable',
            'disconnected',
            'invalid session id',
            'no such window',
            'target window already closed',
        )
        return any(marker in message for marker in fatal_markers)

    def validate_phone_number(self) -> bool:
        """
        Validate that the phone number is in the correct format.

        Returns:
            bool: True if phone number is valid, False otherwise
        """
        recipients = self._configured_recipients()
        if not recipients:
            self.logger.error("WhatsApp recipient is not configured")
            return False

        for recipient in recipients:
            if not self.is_valid_recipient(recipient):
                self.logger.error(f"Invalid WhatsApp recipient format: {recipient}")
                self.logger.info(
                    "Recipients should be a phone number, group invite URL, or group code"
                )
                return False

        return True

    def _configured_recipients(self):
        recipients = []
        global_recipient = (
            (getattr(self.config, 'WHATSAPP_GROUP_INVITE_CODE', '') or '').strip()
            or getattr(self.config, 'WHATSAPP_PHONE_NUMBER', '')
        )
        if global_recipient:
            recipients.append(global_recipient)

        for field in (
            'WHATSAPP_JOB_ALERT_RECIPIENT',
            'WHATSAPP_MESSAGE_ALERT_RECIPIENT',
        ):
            recipient = (getattr(self.config, field, '') or '').strip()
            if recipient:
                recipients.append(recipient)

        return recipients

    def format_email_message(self, email_data: Dict, alert_type: Optional[str] = None) -> str:
        """Format email data into a clean WhatsApp message."""
        subject = self._sanitize_message_for_whatsapp(
            email_data.get('subject', 'No Subject')
        ) or 'No Subject'
        sender = self._sanitize_message_for_whatsapp(
            email_data.get('sender', 'Unknown Sender')
        ) or 'Unknown Sender'
        body = self._sanitize_message_for_whatsapp(email_data.get('body', ''))

        if body:
            body = ' '.join(body.split())
            if len(body) > 150:
                body = body[:150] + "..."

        header = self._message_header_for_alert(alert_type)

        message = f"{header}\n\n"
        message += f"From: {sender}\n"
        message += f"Subject: {subject}\n"
        if body:
            message += f"\nPreview: {body}"

        return self._sanitize_message_for_whatsapp(message)

    def _message_header_for_alert(self, alert_type: Optional[str]) -> str:
        if alert_type == 'message_alert':
            return 'Message Alert'
        if alert_type == 'job_alert':
            return 'Job Alert'

        return (
            self._sanitize_message_for_whatsapp(
                getattr(self.config, 'WHATSAPP_MESSAGE_HEADER', 'Upwork Alert')
            )
            or 'Upwork Alert'
        )
