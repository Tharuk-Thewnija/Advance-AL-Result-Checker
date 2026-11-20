"""No-result site responses must finish one row without disabling automatic mode."""
import threading
import unittest
from selenium.common.exceptions import NoSuchElementException

from al_results import collector
from al_results.nonecap.collector import private_core


class Element:
    def __init__(self, text, visible=True):
        self.text, self.visible = text, visible

    def is_displayed(self):
        return self.visible


class Driver:
    def __init__(self, messages=(), cards=()):
        self.messages, self.cards = messages, cards

    def find_elements(self, by, selector):
        return self.cards if selector == '.card.border-info.watermark' else self.messages

    def find_element(self, by, selector):
        matches = self.find_elements(by, selector)
        if not matches:
            raise NoSuchElementException()
        return matches[0]


class SiteNoticeTests(unittest.TestCase):
    def test_manual_wait_ignores_hidden_and_empty_cards(self):
        from selenium.common.exceptions import TimeoutException
        stop, skip = threading.Event(), threading.Event()
        cards = [Element('hidden text', False), Element('   ')]
        with self.assertRaises(TimeoutException):
            collector.wait_for_results_or_skip(Driver(cards=cards), .02, stop, skip)
        self.assertEqual(collector.wait_for_results_or_skip(
            Driver(cards=cards + [Element('Physics\nA')]), 1, stop, skip), 'Physics\nA')

    def test_visible_site_notice_skips_in_manual_and_automatic_waits(self):
        for core in (collector, private_core()):
            with self.subTest(core=core.__name__):
                driver = Driver([Element('SORRY FOR THE INCONVENIENCE, Please try again')])
                with self.assertRaises(core.SkipCurrentRow) as raised:
                    core.wait_for_results_or_skip(driver, .01, threading.Event(), threading.Event())
                self.assertIn('Site returned', str(raised.exception))

    def test_hidden_notice_does_not_skip_a_valid_result(self):
        core = private_core()
        driver = Driver([Element('Sorry for the inconvenience, Please try again', False)], [Element('Valid result')])
        self.assertEqual(core.wait_for_results_or_skip(driver, 1, threading.Event(), threading.Event()), 'Valid result')
