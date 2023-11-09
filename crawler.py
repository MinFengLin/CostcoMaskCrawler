# 好市多線上購物爬蟲
# python 3.7.7
# encoding=utf-8

import os
import pytz
import time
import random
import logging
import requests
import smtplib
import json
from datetime import datetime
from email.mime.text import MIMEText
from email.header import Header
from bs4 import BeautifulSoup
from linebot import LineBotApi
from linebot.models import TextSendMessage
from linebot.exceptions import LineBotApiError
from typing import List
from dotenv import load_dotenv

class Product:
    def __init__(self, title, url, status=0, price='N/A', id=None):
        self.title = title
        self.url = url
        self.status = status
        self.price = price
        self.id = id if id else self.extract_id(url)

    @staticmethod
    def extract_id(url):
        # 切割網址取得商品編號
        if url.rsplit("/", 2)[1] == "p":
            return url.rsplit("/", 1)[1]
        return None

class costco:
    def __init__(self):
        logging.basicConfig(level=logging.INFO, format="%(asctime)s, %(levelname)s: %(message)s", \
                            datefmt="%Y-%m-%d %H:%M:%S")

        UserAgentConfigFileName = "user_agent_config.json"
        if not os.path.isfile(UserAgentConfigFileName):
            print("could not find", UserAgentConfigFileName)
            exit()

        productFileName = "product.json"
        if not os.path.isfile(productFileName):
            print("could not find", productFileName)
            exit()

        # 讀取設定
        load_dotenv()

        # 設定 Line API
        self.line_notify       = os.getenv('LINE_NOTIFY')
        self.line_notify_token = os.getenv('LINE_NOTIFY_TOKEN')
        self.line_bot          = os.getenv('LINE_BOT')
        self.line_bot_token    = os.getenv('LINE_BOT_TOKEN')

        # 設定信箱
        self.email_service = os.getenv('EMAIL_SERVICE')
        self.server        = os.getenv('EMAIL_SERVER')
        self.port          = os.getenv('EMAIL_PORT')
        self.user          = os.getenv('EMAIL_USER')
        self.password      = os.getenv('EMAIL_PASSWORD')
        self.from_addr     = os.getenv('EMAIL_FROM_ADDR')
        self.to_addr       = os.getenv('EMAIL_TO_ADDR')

        # 設定等待時間
        self.next_search_time = int(os.getenv('NEXT_SEARCH_TIME'))
        self.continuous       = os.getenv('CONTINUOUS')

        # 設定checklog2file
        self.save_check_timestamp_2_file = os.getenv('SAVE_CHECK_TIMESTAMP_2_FILE')

        # 讀取user-agent設定
        with open(UserAgentConfigFileName, "r", encoding="utf-8") as json_file:
            config = json.load(json_file)

            # 設定 user-agent
            self.USER_AGENT_LIST = config["agent"]["user-agent"]

        # 設定目標商品
        self.products: List[Product] = []
        with open(productFileName, "r", encoding="utf-8") as json_file:
            product_config = json.load(json_file)

            for item in product_config:
                # 創建Product實例並添加到列表
                self.products.append(Product(item["title"], item["url"]))
        
        if self.line_bot.lower() != 'false':
            self.line_bot_api = LineBotApi(self.line_bot_token)

        self.message = [
            "商品下架通知",
            "商品上架通知(無庫存)",
            "商品上架/價格變動通知(可能有庫存, 可加入購物車)"
        ]

        '''
        商品狀態
        0 :未上架(分類清單中未出現)
        1 :有上架但無庫存(分類清單中有出現或商品網頁存在，但加入購物車按鈕不存在)
        2 :有上架且"可能"有庫存(分類清單中有出現或商品網頁存在，且加入購物車按鈕存在)
        '''

    def get_new_products(self):
        with open('product.json', 'r', encoding='utf-8') as file:
            new_products_data = json.load(file)
            return new_products_data

    def Updateproduct(self):
        new_products_data = self.get_new_products()   # 讀取產品列表

        # 用來儲存更新後的產品
        updated_products = []

        # 遍歷新產品數據, 添加新增的產品
        for new_product_data in new_products_data:
            if not any(product.url == new_product_data['url'] for product in self.products):
                new_product = Product(
                    title=new_product_data['title'],
                    url=new_product_data['url']
                )
                updated_products.append(new_product)
                logging.info(f"Added new product: {new_product.title}")
            else:
                # 如果產品已經存在, 直接添加到列表即可
                existing_product = next((product for product in self.products if product.url == new_product_data['url']), None)
                if existing_product:
                    updated_products.append(existing_product)

        # 更新產品列表
        self.products = updated_products
        logging.info("Product list has been updated.")


    def start(self):
        while True:
            self.nowtime = datetime.now(pytz.timezone("Asia/Taipei"))
            if self.check_time():
                logging.info("check " + self.nowtime.strftime("%Y-%m-%d %H:%M:%S"))
                self.Updateproduct()
                if self.save_check_timestamp_2_file.lower() != 'false':
                    if not os.path.isfile('check_log_record'):
                        with open('check_log_record', 'w') as file:
                            pass

                    with open('check_log_record', 'r') as file:
                        lines = file.readlines()

                    if len(lines) >= 10:
                        with open('check_log_record', 'w') as file:
                            file.write("check " + self.nowtime.strftime("%Y-%m-%d %H:%M:%S") + '\n')
                    else:
                        with open('check_log_record', 'a') as file:
                            file.write("check " + self.nowtime.strftime("%Y-%m-%d %H:%M:%S") + '\n')

                no_update = "No Update: "
                for item in self.products:
                    status_result = self.search(item)
                    price_update = self.price
                    if status_result != item.status or price_update != item.price:
                        item.status = status_result
                        item.price = price_update
                        logging.info(item.title + " " + item.url)
                        if self.line_notify.lower() != 'false':
                            self.send_line_notify(item)
                        if self.line_bot.lower() != 'false':
                            self.send_line_bot(item)
                        if self.email_service.lower() != 'false':
                            self.send_email(item)
                    else:
                        no_update = no_update + item.title + "/"
                logging.info(no_update)


            time.sleep(random.randint(10, self.next_search_time))


    # 爬取資料，檢查按鈕是否存在
    def search(self, product):
        header = {
            "user-agent": random.choice(self.USER_AGENT_LIST)
        }
        with requests.get(product.url, headers=header) as res:
            soup = BeautifulSoup(res.text, "lxml")
            if (soup.find('span', class_='notranslate ng-star-inserted') != None):
                span_price_tag = soup.find('span', class_='notranslate ng-star-inserted')
                self.price = span_price_tag.get_text()

                if (soup.find('span', class_='you-pay-value') != None):
                    span_save_tag = soup.find('span', class_='you-pay-value')
                    self.price = "原價:" + self.price + ", 特價: " + span_save_tag.get_text()
            else:
                self.price = "N/A"
    
            '''
            商品頁面存在，可以找到 addToCartButton
            商品頁面不存在則會自動跳回分類列表，若分類列表存在商品，可能可以找到 add-to-cart-button-xxxxxx
            出現"加入購物車"按鈕不代表一定有庫存
            若不知道商品網址或編號，只有商品分類網址跟商品名稱，就直接搜尋名稱，但無法檢查按鈕
            '''
            if product.id is not None and (soup.find(id="addToCartButton") is not None or \
                                       soup.find(id=("add-to-cart-button-" + product.id)) is not None or \
                                       soup.find(id="add-to-cart-button")):
                return 2
            elif product.title in res.text:
                return 1
        return 0


    # 自動加入購物車
    def add_to_cart(self):
        pass

    def checkout(self):
        pass


    # 自訂時間範圍檢查
    def check_time(self):
        if self.continuous:
            return True
        elif 8 <= self.nowtime.hour <= 22:
            return True
        return False

    # email通知
    def send_email(self, item):
        text = self.nowtime.strftime("%Y-%m-%d %H:%M:%S ") + item.price + "\n" + item.title + "\n" + item.url

        msg = MIMEText(text, "plain", "utf-8")
        msg["From"] = Header("好市多爬蟲", "utf-8")
        msg["To"] = Header(self.to_addr, "utf-8")
        msg["Subject"] = Header(self.message[item.status], "utf-8")

        with smtplib.SMTP(self.server, self.port) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.login(self.user, self.password)
            ret = smtp.sendmail(self.from_addr, self.to_addr, msg.as_string())
            if ret == {}:
                logging.info("郵件傳送成功")
                return True
        logging.info("郵件傳送失敗")
        return False

    # line_notify通知
    def send_line_notify(self, item):
        notify_url = 'https://notify-api.line.me/api/notify'
        token = self.line_notify_token
        headers = {
            'Authorization': 'Bearer ' + token    # 設定token
        }
        data = {
            'message': self.message[item.status] + "\n" + \
                       self.nowtime.strftime("%Y-%m-%d %H:%M:%S") + "\n" + \
                       item.price + "\n" + \
                       item.title + "\n" + item.url
        }
        # logging.info(notify_url)
        # logging.info(headers)
        # logging.info(data)

        requests.post(notify_url, headers=headers, data=data)

    # line_bot通知
    def send_line_bot(self, item):
        text = self.message[item.status] + "\n" + \
               self.nowtime.strftime("%Y-%m-%d %H:%M:%S") + "\n" + item.price + "\n" + item.title + "\n" + item.url
        try:
            self.line_bot_api.broadcast(TextSendMessage(text=text))
        except LineBotApiError as e:
            print(e)

def main():
    csd = costco()
    csd.start()

if __name__ == "__main__":
    main()
