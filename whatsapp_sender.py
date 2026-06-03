from __future__ import annotations

import logging
import os
import time
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

    def __init__(self):
        self.config = Config()
        self.logger = logging.getLogger(__name__)
        self.driver = None

    def send_message(self, message: str, instant: bool = True) -> bool:
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

        try:
            self.logger.info("Sending WhatsApp message through WhatsApp Web...")
            driver = self._get_driver()
            driver.get(self._build_chat_url(message))

            compose_box = self._wait_for_compose_box(driver)
            self._ensure_draft_message(driver, compose_box, message)

            for attempt in range(2):
                self._click_send_button(driver)
                time.sleep(1)
                if self._message_left_draft(driver, message):
                    self.logger.info("WhatsApp message sent and draft cleared")
                    return True
                self.logger.warning("WhatsApp draft still present after send click; retrying click")

            self.logger.error("WhatsApp message appears to be stuck in the draft box")
            return False

        except TimeoutException:
            self.logger.error("Timed out waiting for WhatsApp Web to become ready")
            return False
        except WebDriverException as e:
            self.logger.error("WhatsApp browser automation failed: %s", str(e))
            self.close()
            return False
        except Exception as e:
            self.logger.error("Failed to send WhatsApp message: %s", str(e))
            return False

    def send_immediate_message(self, message: str) -> bool:
        """Send a WhatsApp message immediately."""
        return self.send_message(message, instant=True)

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
        options.add_argument("--start-maximized")

        if self.config.CHROME_BINARY_PATH:
            options.binary_location = self.config.CHROME_BINARY_PATH

        return options

    def _build_chat_url(self, message: str) -> str:
        group_code = self._get_group_invite_code()
        if group_code:
            return f"https://web.whatsapp.com/accept?code={quote(group_code)}"

        phone = ''.join(char for char in (self.config.WHATSAPP_PHONE_NUMBER or '') if char.isdigit())
        return f"https://web.whatsapp.com/send?phone={phone}&text={quote(message)}"

    def _get_group_invite_code(self) -> str:
        raw_code = getattr(self.config, 'WHATSAPP_GROUP_INVITE_CODE', '').strip()
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

    def _wait_for_compose_box(self, driver):
        wait = WebDriverWait(driver, self.config.WHATSAPP_WAIT_SECONDS)
        return wait.until(lambda current_driver: self._find_visible_compose_box(current_driver))

    def _find_visible_compose_box(self, driver):
        boxes = driver.find_elements(By.XPATH, self.COMPOSE_BOX_XPATH)
        visible_boxes = [box for box in boxes if box.is_displayed()]
        return visible_boxes[-1] if visible_boxes else False

    def _ensure_draft_message(self, driver, compose_box, message: str):
        draft_text = self._element_text(compose_box)
        if self._normalize(message) in self._normalize(draft_text):
            return

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
            return

        compose_box.send_keys(Keys.CONTROL, 'a')
        compose_box.send_keys(Keys.BACKSPACE)
        lines = message.splitlines() or ['']
        for index, line in enumerate(lines):
            if line:
                compose_box.send_keys(line)
            if index < len(lines) - 1:
                compose_box.send_keys(Keys.SHIFT, Keys.ENTER)

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

    def validate_phone_number(self) -> bool:
        """
        Validate that the phone number is in the correct format.

        Returns:
            bool: True if phone number is valid, False otherwise
        """
        phone = self.config.WHATSAPP_PHONE_NUMBER

        if self._get_group_invite_code():
            return True

        if not phone:
            self.logger.error("WhatsApp phone number or group invite code not configured")
            return False

        if not phone.startswith('+') or not phone[1:].replace(' ', '').isdigit():
            self.logger.error(f"Invalid phone number format: {phone}")
            self.logger.info("Phone number should be in format: +1234567890")
            return False

        return True

    def format_email_message(self, email_data: Dict) -> str:
        """Format email data into a clean WhatsApp message."""
        subject = email_data.get('subject', 'No Subject')
        sender = email_data.get('sender', 'Unknown Sender')
        body = email_data.get('body', '')

        if body:
            body = ' '.join(body.split())
            if len(body) > 150:
                body = body[:150] + "..."

        message = "📧 New Email\n\n"
        message += f"From: {sender}\n"
        message += f"Subject: {subject}\n"
        if body:
            message += f"\nPreview: {body}"

        return message
