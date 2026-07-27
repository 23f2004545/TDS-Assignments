from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
import re

BASE = "https://sanand0.github.io/tdsdata/js_table?seed={}"

SEEDS = list(range(50,60))

grand_total = 0

def parse_numbers(text):

    nums = re.findall(r"-?\d+(?:\.\d+)?", text)

    return sum(float(x) for x in nums)

with sync_playwright() as p:

    browser = p.chromium.launch(headless=True)

    page = browser.new_page()

    for seed in SEEDS:

        url = BASE.format(seed)

        print(url)

        page.goto(url,wait_until="networkidle")

        html = page.content()

        soup = BeautifulSoup(html,"lxml")

        tables = soup.find_all("table")

        subtotal = 0

        for table in tables:

            subtotal += parse_numbers(table.get_text(" "))

        print(f"Seed {seed}: {subtotal}")

        grand_total += subtotal

    browser.close()

print("="*40)
print(f"TOTAL = {grand_total}")
print("="*40)