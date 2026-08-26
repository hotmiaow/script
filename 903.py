import requests
import m3u8
import time

import asyncio
from playwright.async_api import async_playwright

referer = 'https://www.881903.com/live/903'

# Function to download file with specific cookies
def download_file_with_cookies(url, cookies, file_path):
    response = requests.get(url, cookies=cookies, stream=True)
    if response.status_code == 200:
        with open(file_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=1024):
                f.write(chunk)
    else:
        print(f"Failed to download file from {url}")


async def getCookie():
    # Start Playwright in async mode
    async with async_playwright() as p:
        # Launch Chromium browser
        browser = await p.chromium.launch(headless=True)  # Run headless mode
        page = await browser.new_page()

        # Navigate to the URL
        await page.goto("https://www.881903.com/timetable/903")

        # Extract cookies
        cookies = await page.context.cookies()

        # Close the browser
        await browser.close()
        return cookies



if __name__ == '__main__':
    cookies=asyncio.run(getCookie())

    headers = {
        'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/100.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9',
        'Accept-Language': 'en-US,en;q=0.9',
        'Referer': referer
    }

    # URL of the M3U8 file
    m3u8_url = 'https://live.881903.com/edge-aac/903hd/chunks.m3u8'
    time.sleep(3)
    # Download the M3U8 file and parse it
    m3u8_response = requests.get(m3u8_url, cookies=cookies, headers=headers)
    m3u8_playlist = m3u8.loads(m3u8_response.text)

    # Assuming the first URI is the AAC file you want (adjust as necessary)
    if m3u8_playlist.segments:
        aac_file_url = m3u8_playlist.segments[0].uri
        print(f"Found AAC file URL: {aac_file_url}")

        # Download the AAC file
        download_file_with_cookies(aac_file_url, cookies, "output.aac")
    else:
        print("No segments found in the M3U8 file.")