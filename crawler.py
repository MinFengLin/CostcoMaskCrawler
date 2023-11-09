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

class costco:
    def __init__(self):
        logging.basicConfig(level=logging.INFO, format="%(asctime)s, %(levelname)s: %(message)s", \
                            datefmt="%Y-%m-%d %H:%M:%S")

        configFileName = "config.json"
        if not os.path.isfile(configFileName):
            print("could not find", configFileName)
            exit()

        productFileName = "product.json"
        if not os.path.isfile(productFileName):
            print("could not find", productFileName)
            exit()

        # 讀取設定
        with open(configFileName, "r", encoding="utf-8") as json_file:
            config = json.load(json_file)

            # 設定 Line API
            self.line_notify       = config["line"]["line_notify_token"]
            self.line_notify_token = config["line"]["line_notify_token"]
            self.line_bot          = config["line"]["line_bot"]
            self.line_bot_token    = config["line"]["line_bot_token"]

            # 設定信箱
            self.email_service = config["email"]["email_service"]
            self.server        = config["email"]["server"]
            self.port          = config["email"]["port"]
            self.user          = config["email"]["user"]
            self.password      = config["email"]["password"]
            self.from_addr     = config["email"]["from_addr"]
            self.to_addr       = config["email"]["to_addr"]

            # 設定等待時間
            self.next_search_time = config["time"]["next_search_time"]
            self.continuous = config["time"]["continuous"]

            # 設定checklog2file
            self.save_check_timestamp_2_file = config["log_save"]["save_check_timestamp_2_file"]

            # 設定 user-agent
            self.USER_AGENT_LIST = config["agent"]["user-agent"]

        # 設定目標商品
        self.product = list()
        with open(productFileName, "r", encoding="utf-8") as json_file:
            config = json.load(json_file)

            for item in config:
                # 檢查網址為商品頁面或分類列表
                # 切割網址取得商品編號
                if item["url"].rsplit("/", 2)[1] == "p":
                    item["id"] = item["url"].rsplit("/", 1)[1]
                else:
                    item["id"] = None
                item["status"] = 0
                self.product.append(item)
        if self.line_bot:
            self.line_bot_api = LineBotApi(self.line_bot_token)

        self.message = [
            "商品下架通知",
            "商品上架通知(無庫存)",
            "商品上架通知(可能有庫存, 可加入購物車)"
        ]

        '''
        商品狀態
        0 :未上架(分類清單中未出現)
        1 :有上架但無庫存(分類清單中有出現或商品網頁存在，但加入購物車按鈕不存在)
        2 :有上架且"可能"有庫存(分類清單中有出現或商品網頁存在，且加入購物車按鈕存在)
        '''


    def start(self):
        while True:
            self.nowtime = datetime.now(pytz.timezone("Asia/Taipei"))
            if self.check_time():
                logging.info("check " + self.nowtime.strftime("%Y-%m-%d %H:%M:%S"))
                if self.save_check_timestamp_2_file:
                    with open('check_log_record', 'r') as file:
                        lines = file.readlines()

                    if len(lines) >= 10:
                        with open('check_log_record', 'w') as file:
                            file.write("check " + self.nowtime.strftime("%Y-%m-%d %H:%M:%S") + '\n')
                    else:
                        with open('check_log_record', 'a') as file:
                            file.write("check " + self.nowtime.strftime("%Y-%m-%d %H:%M:%S") + '\n')

                for item in self.product:
                    result = self.search(item)
                    if result != item["status"]:
                        item["status"] = result
                        item["price"] = self.price
                        logging.info(item["title"] + " " + item["url"])
                        if self.line_notify:
                            self.send_line_notify(item)
                        if self.line_bot:
                            self.send_line_bot(item)
                        if self.email_service:
                            self.send_email(item)

            time.sleep(random.randint(10, self.next_search_time))


    # 爬取資料，檢查按鈕是否存在
    def search(self, item):
        header = {
            "user-agent": random.choice(self.USER_AGENT_LIST)
        }
        with requests.get(item["url"], headers=header) as res:
            soup = BeautifulSoup(res.text, "lxml")
            span_price_tag = soup.find('span', class_='notranslate ng-star-inserted')
            self.price = span_price_tag.get_text()
            if (soup.find('span', class_='you-pay-value') != None):
                span_save_tag = soup.find('span', class_='you-pay-value')
                self.price = "原價:" + self.price + ", 特價: " + span_save_tag.get_text()

            '''
            商品頁面存在，可以找到 addToCartButton
            商品頁面不存在則會自動跳回分類列表，若分類列表存在商品，可能可以找到 add-to-cart-button-xxxxxx
            出現"加入購物車"按鈕不代表一定有庫存
            若不知道商品網址或編號，只有商品分類網址跟商品名稱，就直接搜尋名稱，但無法檢查按鈕
            '''
            if item["id"] != None and (soup.find(id="addToCartButton") != None or \
                                       soup.find(id=("add-to-cart-button-" + item["id"])) != None or \
                                       soup.find(id="add-to-cart-button") ):
                return 2
            elif item["title"] in res.text:
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
        text = self.nowtime.strftime("%Y-%m-%d %H:%M:%S ") + item["title"] + "\n" + item["url"]

        msg = MIMEText(text, "plain", "utf-8")
        msg["From"] = Header("好市多爬蟲", "utf-8")
        msg["To"] = Header(self.to_addr, "utf-8")
        msg["Subject"] = Header(self.message[item["status"]], "utf-8")

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
            'message': self.message[item["status"]] + "\n" + \
                       self.nowtime.strftime("%Y-%m-%d %H:%M:%S") + "\n" + \
                       item["price"] + "\n" + \
                       item["title"] + "\n" + item["url"]
        }
        # logging.info(notify_url)
        # logging.info(headers)
        # logging.info(data)

        requests.post(notify_url, headers=headers, data=data)

    # line_bot通知
    def send_line_bot(self, item):
        text = self.message[item["status"]] + "\n" + \
               self.nowtime.strftime("%Y-%m-%d %H:%M:%S") + "\n" + item["title"] + "\n" + item["url"]
        try:
            self.line_bot_api.broadcast(TextSendMessage(text=text))
        except LineBotApiError as e:
            print(e)

def main():
    csd = costco()
    csd.start()

if __name__ == "__main__":
    main()
