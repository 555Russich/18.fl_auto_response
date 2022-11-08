import json
import os
import time
import logging
import pickle
from datetime import datetime, timedelta

from seleniumwire import webdriver
from seleniumwire.utils import decode
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.wait import WebDriverWait
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.remote.webelement import WebElement
from webdriver_manager.chrome import ChromeDriverManager

from my_logging import get_logger


class Bot:
    filepath_cookies_profi_ru = 'cookies_profi'
    filepath_tasks = 'tasks.json'

    def __init__(self):
        self.driver = None
        self.login_profi_ru = os.environ['LOGIN_PROFI_RU']
        self.password_profi_ru = os.environ['PASSWORD_PROFI_RU']

    def get_driver(self) -> None:
        options = webdriver.ChromeOptions()
        options_wire = {
            # 'ignore_http_methods': [],
            # 'verify_ssl': True
            'disable_encoding': True
        }
        # fake user agent
        options.add_argument(
            f'user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) '
            f'Chrome/107.0.0.0 Safari/537.36'
        )
        # disable web driver mode
        options.add_argument('--disable-blink-features=AutomationControlled')
        # headless mode
        options.headless = False
        # maximized window
        options.add_argument('--start-maximized')
        self.driver = webdriver.Chrome(
            service=Service(ChromeDriverManager().install()),
            options=options,
            seleniumwire_options=options_wire
        )

    def find_element(self, by: By, pattern: str) -> bool | WebElement:
        try:
            return self.driver.find_element(by, pattern)
        except:
            return False

    def save_cookie(self, filepath: str) -> None:
        with open(filepath, 'wb') as f:
            pickle.dump(self.driver.get_cookies(), f)

    def load_cookie(self, filepath: str) -> None:
        with open(filepath, 'rb') as f:
            for cookie in pickle.load(f):
                self.driver.add_cookie(cookie)

    def authorize(self) -> None:
        """ Authorization with login and password """
        # self.find_element(By.XPATH, '//a[text()="Вход для специалистов"]').click()
        self.find_element(By.XPATH, '//input[@type="text"][@required][@value]').send_keys(self.login_profi_ru)
        self.find_element(By.XPATH, '//input[@type="password"][@required][@value]').send_keys(self.password_profi_ru)
        self.find_element(By.XPATH, '//a[text()="Продолжить"]').click()

        # if WebDriverWait(self.driver, timeout=10).until(
        #         EC.presence_of_element_located((By.XPATH, '//h1[text()="Введите код из СМС"]'))
        # ):
        #     sms_code = input('Input sms code: ')
        #     cells = self.driver.find_elements(By.XPATH, '//div[@class="pin-form"]//input')
        #     for i in range(len(cells)):
        #         cells[i].send_keys(sms_code[i])
    def find_request(self) -> dict:
        """ Find POST request to get orders search result """
        for request in self.driver.requests:
            if request.response and request.url == 'https://profi.ru/backoffice/api/':
                data = request.response.body.decode('utf-8')
                data = json.loads(data)
                if data.get('meta') and data.get('meta').get('method') == 'findOrders':
                    return data

    def parse_orders(self, data: dict):
        for order in data['data']['orders']:
            order_data = {
                'id': order['id'],
                'title': order['title']
            }

    def first_time_get_orders(self, scroll_pause_time=0.5):
        data = self.find_request()
        del self.driver.requests

        while True:
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(scroll_pause_time)

            # new_height = self.driver.execute_script("return document.body.scrollHeight")
            # if new_height == last_height:
            #     break
            # last_height = new_height

    def move_to_task_search(self):
        self.driver.get('https://profi.ru/backoffice/n.php')

        if self.find_element(By.XPATH, '//h1[text()="Вход и регистрация для профи"]'):
            self.authorize()
            time.sleep(3)
            self.save_cookie(self.filepath_cookies_profi_ru)


if __name__ == '__main__':
    get_logger('bot.log')
    bot = Bot()
    bot.get_driver()
    bot.move_to_task_search()
    bot.find_request()
    time.sleep(999)
    # bot.save_all_tasks()