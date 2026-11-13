import unittest
from urllib.parse import quote
from unittest.mock import patch
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.select import Select
from al_results.collector import open_search_form


class FormTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        options = webdriver.ChromeOptions()
        options.add_argument('--headless=new')
        cls.driver = webdriver.Chrome(options=options)

    @classmethod
    def tearDownClass(cls):
        cls.driver.quit()

    def test_labels_and_delayed_options(self):
        for label in ['G.C.E.(A/L) EXAMINATION',
                      'G.C.E.(A/L) EXAMINATION-(After Rescrutiny)']:
            with self.subTest(label=label):
                html = '''<select id="exam" class="form-control flex-grow-1 h5"
                  onchange="setTimeout(() => document.getElementById('year').innerHTML += '<option>2025</option>', 550)">
                  <option value="default">Select</option><option value="al"></option></select>
                  <select id="year" class="form-control flex-grow-1 h5"><option>Select year</option></select>
                  <select class="custom-option form-control"><option value="index">Index</option><option value="nic">NIC</option></select>
                  <script>setTimeout(() => document.querySelector('option[value=al]').textContent = 'LABEL', 550)</script>'''.replace('LABEL', label)
                navigate = self.driver.get
                with patch.object(self.driver, 'get', side_effect=lambda _: navigate('data:text/html,' + quote(html))):
                    open_search_form(self.driver, '2025')
                self.assertEqual(Select(self.driver.find_element(By.ID, 'exam')).first_selected_option.get_attribute('value'), 'al')
                self.assertEqual(Select(self.driver.find_element(By.ID, 'year')).first_selected_option.text, '2025')
                self.assertEqual(Select(self.driver.find_element(By.CSS_SELECTOR, '.custom-option')).first_selected_option.get_attribute('value'), 'nic')
