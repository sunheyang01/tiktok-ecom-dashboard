"""打开浏览器登录TikTok Shop，登录后自动保存cookie"""
import os
import time

os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", os.path.expanduser("~/.playwright-browsers"))

from playwright.sync_api import sync_playwright

STORAGE_PATH = os.path.expanduser("~/zewenkanban/tiktok-mcn-scraper/data/storage_state.json")
SIGNAL_FILE = "/tmp/tiktok_login_done"

# 清除旧信号
if os.path.exists(SIGNAL_FILE):
    os.remove(SIGNAL_FILE)

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    context = browser.new_context()
    page = context.new_page()
    page.goto("https://partner.eu.tiktokshop.com")
    print("浏览器已打开，请登录 TikTok Shop Partner Center EU")
    print(f"登录成功后，运行: touch {SIGNAL_FILE}")

    # 等待信号文件
    while not os.path.exists(SIGNAL_FILE):
        time.sleep(2)

    # 保存 cookie
    os.makedirs(os.path.dirname(STORAGE_PATH), exist_ok=True)
    context.storage_state(path=STORAGE_PATH)
    print(f"Cookie 已保存到 {STORAGE_PATH}")
    browser.close()
