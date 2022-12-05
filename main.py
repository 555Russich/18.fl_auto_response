import json
import os
import re
import time
import logging
import pickle
import traceback
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from seleniumwire import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement
from webdriver_manager.chrome import ChromeDriverManager

from my_logging import get_logger


def append_to_json(filepath: str, data2append: str) -> None:
    if not os.path.exists(filepath):
        with open(filepath, 'w') as f:
            json.dump([], f)
    with open(filepath, 'r') as f:
        data = json.load(f)
    if data2append not in data:
        data.append(data2append)
    with open(filepath, 'w') as f:
        json.dump(data, f, indent=4)


def is_id_in_json(filepath: str, id_: str) -> bool:
    if not os.path.exists(filepath):
        return False
    with open(filepath, 'r') as f:
        data = json.load(f)
    return True if id_ in data else False


class Bot:
    filepath_cookies_profi_ru = 'cookies_profi'
    filepath_orders = 'orders_id.json'

    def __init__(self):
        self.driver = self.get_driver
        self.login_profi_ru = os.environ['LOGIN_PROFI_RU']
        self.password_profi_ru = os.environ['PASSWORD_PROFI_RU']

    @property
    def get_driver(self) -> webdriver.Chrome:
        options = webdriver.ChromeOptions()
        options_wire = {
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
        options.headless = True
        # maximized window
        options.add_argument('--start-maximized')
        return webdriver.Chrome(
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
        self.find_element(By.XPATH, '//input[@type="text"][@required][@value]').send_keys(self.login_profi_ru)
        self.find_element(By.XPATH, '//input[@type="password"][@required][@value]').send_keys(self.password_profi_ru)
        self.find_element(By.XPATH, '//a[text()="Продолжить"]').click()

    def move_to_search(self) -> None:
        self.driver.get('https://profi.ru/backoffice/n.php')
        if self.find_element(By.XPATH, '//h1[text()="Вход и регистрация для профи"]'):
            logging.info('Start authorizing')
            self.authorize()
            time.sleep(3)
            self.save_cookie(self.filepath_cookies_profi_ru)

    def find_request(self, method: str, retries=3) -> dict | bool:
        """ Find POST request to get orders search result """
        for retry in range(retries):
            for request in self.driver.requests:
                if request.response and request.url == 'https://profi.ru/backoffice/api/':
                    data = request.response.body.decode('utf-8')
                    data = json.loads(data)
                    if data.get('meta') and data.get('meta').get('method') == method:
                        del self.driver.requests
                        match len(data['errors']):
                            case 0:
                                return data
                            case _:
                                if data['errors'][0]['title'] == 'Unauthorized user':
                                    logging.info('Unauthorized user')
                                    self.driver.refresh()
                                    return self.find_request(method)
                                else:
                                    return False
            time.sleep(0.5)
        else:
            del self.driver.requests
            return False

    def find_new_orders(self) -> int:
        count_new_orders = 0
        data = self.find_request('findOrders')
        if not data:
            return -1
        for order in data['data']['orders']:
            if order.get('type') == 'adFox' or is_id_in_json(self.filepath_orders, order['id']):
                continue
            else:
                count_new_orders += 1
                self.handle_new_order(order)
        return count_new_orders

    def handle_new_order(self, order: dict):
        for i in range(3):
            self.driver.get(f'https://profi.ru/backoffice/n.php?o={order["id"]}')
            time.sleep(1)
            if r := self.find_request('getOrder'):
                order_datetime = datetime.strptime(
                    r['data']['order']['receivd'], '%Y-%m-%d %H:%M:%S'
                ).replace(tzinfo=ZoneInfo('Europe/Moscow'))
                current_datetime = datetime.now(tz=ZoneInfo('Europe/Moscow'))
                if current_datetime - timedelta(days=7) <= order_datetime:
                    if current_datetime - timedelta(minutes=3) < order_datetime:
                        # self.find_element(By.XPATH, '//a[text()="Вход для специалистов"]').click()
                        return False
                    text = '\n'.join(
                            [
                                r['data']['order']['subjects'],
                                r['data']['order']['aim']
                            ]).lower()
                    name = r['data']['order']['name']
                    if self.filter_order(text, order['id']): 
                        try:
                            self.response_to_order(name)
                        except:
                            logging.error(f'order_id={order["id"]}\n{traceback.format_exc()}')
                            return False
                append_to_json(self.filepath_orders, order['id'])
                return True
            else:
                logging.error(f'Request was not found for {order["id"]}, trying again')
                time.sleep(5)
        else:
            return False

    def filter_order(self, text: str, order_id: str) -> bool:
        with open('pattern_bad.regexp', 'r', encoding='utf-8') as f:
            pattern_bad = f.read()

        to_work = False
        if result := re.search(pattern_bad, text):
            reason = result.group(0)
            logging.info(f'{order_id=}; {to_work=}, {reason=}')
            # self.driver.save_screenshot(str(Path('screenshots', f'False_{order_id}.png')))
        else:
            to_work = True
            logging.info(f'{order_id=}; {to_work=}')
            # self.driver.save_screenshot(str(Path('screenshots', f'True_{order_id}.png')))
        return to_work

    def response_to_order(self, name: str):
        self.driver.implicitly_wait(1.5)
        if not (btn_response := self.find_element(By.XPATH, '//p[text()="Написать клиенту"]//ancestor::button')):
            return False

        self.driver.execute_script("arguments[0].scrollIntoView();", btn_response)
        btn_response.click()
        time.sleep(0.5)

        self.find_element(By.XPATH, '//p[text()="Дальше"]//ancestor::button').click()
        time.sleep(0.5)

        response_sample = self.find_element(
            By.XPATH, '//div[@class="backoffice-common-list-item__text-container"]/p[@size]'
        ).text
        response_sample = response_sample.replace('Здравствуйте, !', f'Здравствуйте, {name}!')

        self.find_element(
            By.XPATH, '//textarea[@placeholder="Уточните детали задачи или предложите свои условия"]'
        ).send_keys(response_sample)

        self.find_element(
            By.XPATH, '//p[text()="Отправить сообщение"]//ancestor::a'
        ).click()
        self.driver.implicitly_wait(0)

    def loop_check_orders(self, mode: str, tab_main, tab_second):
        retries = 0
        while True:
            self.driver.refresh() if mode == 'updates' else ...
            self.driver.switch_to.window(tab_second)
            count_new_orders = self.find_new_orders()
            if count_new_orders == -1:
                retries += 1
                if retries == 3:
                    raise Exception('Coudn\'t get "findOrders" request.') 
                logging.error(f'Coudn\'t get "findOrders" request. retry: {retries}')
                continue
            self.driver.switch_to.window(tab_main)
            if count_new_orders >= 3:
                self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(1)
            else:
                if mode == 'start':
                    logging.info('First time getting orders finished')
                    return True
                elif mode == 'updates':
                    logging.info('No new orders, sleeping...')
                    time.sleep(30)

    def run(self):
        self.move_to_search()
        self.driver.switch_to.new_window('tab')
        tab_main, tab_second = self.driver.window_handles
        self.loop_check_orders('start', tab_main, tab_second)
        self.loop_check_orders('updates', tab_main, tab_second)


def run_bot():
    while True:
        bot = Bot()
        try:
            bot.run()
        except KeyboardInterrupt:
            raise
        except:
            logging.error(f'ERROR\n{traceback.format_exc()}')
            try:
                bot.driver.quit()
                del bot
                logging.info('driver was quited')
            except:
                pass


if __name__ == '__main__':
    get_logger('bot.log')
    run_bot()
