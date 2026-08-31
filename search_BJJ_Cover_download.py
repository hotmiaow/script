import os
import requests
from PIL import Image
from io import BytesIO
import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from urllib.parse import quote
import sys
import re

def setup_driver():
    """Set up Chrome driver with optimized options for Bing image scraping"""
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option('useAutomationExtension', False)
    chrome_options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    
    try:
        driver = webdriver.Chrome(options=chrome_options)
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        return driver
    except Exception as e:
        print(f"Error setting up Chrome driver: {e}")
        return None

def search_bing_images(folder_name, driver):
    """Search for images using Bing Images and get the first high-quality result"""
    try:
        # Construct search query for Bing Images
        search_query = f"{folder_name} website:bjjfanatics"
        encoded_query = quote(search_query)
        
        # Navigate to Bing Images
        search_url = f"https://www.bing.com/images/search?q={encoded_query}&form=HDRSC2&first=1"
        print(f"    Searching Bing: {search_query}")
        driver.get(search_url)
        
        # Wait for page to load
        time.sleep(3)
        
        # Wait for images to appear
        wait = WebDriverWait(driver, 15)
        
        try:
            # Bing Images structure - look for image containers
            image_containers = wait.until(
                EC.presence_of_all_elements_located((By.CSS_SELECTOR, "a.iusc"))
            )
            
            if not image_containers:
                # Try alternative selectors
                image_containers = driver.find_elements(By.CSS_SELECTOR, "div.imgpt a")
            
            if not image_containers:
                return None, "No image containers found on Bing"
            
            print(f"    Found {len(image_containers)} image results")
            
            # Try the first few images
            for i, container in enumerate(image_containers[:3]):
                try:
                    print(f"    Attempting to process image {i+1}")
                    
                    # Scroll to make sure element is visible
                    driver.execute_script("arguments[0].scrollIntoView(true);", container)
                    time.sleep(1)
                    
                    # Extract image metadata from the container
                    m_attr = container.get_attribute("m")
                    if m_attr:
                        # Parse the JSON-like attribute to get image URL
                        import json
                        try:
                            image_data = json.loads(m_attr)
                            image_url = image_data.get("murl")  # Main image URL
                            if not image_url:
                                image_url = image_data.get("turl")  # Thumbnail URL as fallback
                            
                            if image_url:
                                print(f"    Found image URL from metadata: {image_url[:60]}...")
                                return download_image(image_url)
                        except:
                            pass
                    
                    # Alternative method: click and get the preview image
                    try:
                        container.click()
                        time.sleep(2)
                        
                        # Look for the main preview image
                        preview_img = driver.find_element(By.CSS_SELECTOR, "img.mainImage")
                        if preview_img:
                            img_url = preview_img.get_attribute("src")
                            if img_url and not img_url.startswith("data:"):
                                print(f"    Found preview image URL: {img_url[:60]}...")
                                return download_image(img_url)
                    except:
                        pass
                    
                    # Fallback: try to find img element within container
                    try:
                        img_element = container.find_element(By.CSS_SELECTOR, "img")
                        img_url = img_element.get_attribute("src")
                        if img_url and not img_url.startswith("data:") and len(img_url) > 50:
                            print(f"    Found container image URL: {img_url[:60]}...")
                            return download_image(img_url)
                    except:
                        pass
                        
                except Exception as e:
                    print(f"    Image {i+1} processing failed: {str(e)}")
                    continue
            
            return None, "All image processing attempts failed"
            
        except Exception as e:
            return None, f"Error finding images on Bing: {str(e)}"
            
    except Exception as e:
        return None, f"Error in Bing search: {str(e)}"

def capture_first_bing_image_screenshot(folder_name, driver):
    """Fallback method: capture screenshot of the first Bing search result"""
    try:
        print("    Attempting screenshot capture as fallback...")
        
        # Find the first image result
        wait = WebDriverWait(driver, 10)
        first_img = wait.until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "a.iusc img, div.imgpt img"))
        )
        
        # Scroll to the image
        driver.execute_script("arguments[0].scrollIntoView(true);", first_img)
        time.sleep(1)
        
        # Get image dimensions and position
        location = first_img.location
        size = first_img.size
        
        # Take full page screenshot
        screenshot = driver.get_screenshot_as_png()
        
        # Crop the image area from screenshot
        screenshot_image = Image.open(BytesIO(screenshot))
        
        # Calculate crop box with some padding
        left = max(0, location['x'] - 5)
        top = max(0, location['y'] - 5)
        right = min(screenshot_image.width, left + size['width'] + 10)
        bottom = min(screenshot_image.height, top + size['height'] + 10)
        
        # Crop the image
        cropped_image = screenshot_image.crop((left, top, right, bottom))
        
        # Check if cropped image is reasonable size
        if cropped_image.size[0] < 50 or cropped_image.size[1] < 50:
            return None, "Cropped image too small"
        
        # Convert to bytes
        img_buffer = BytesIO()
        cropped_image.save(img_buffer, format='PNG')
        
        return img_buffer.getvalue(), None
        
    except Exception as e:
        return None, f"Screenshot capture failed: {str(e)}"

def download_image(image_url):
    """Download image from URL with better headers for Bing"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Referer': 'https://www.bing.com/',
            'Accept': 'image/webp,image/apng,image/jpeg,image/png,image/*,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
        }
        
        response = requests.get(image_url, headers=headers, timeout=30, stream=True)
        response.raise_for_status()
        
        # Read image data
        image_data = b''
        for chunk in response.iter_content(chunk_size=8192):
            image_data += chunk
        
        # Basic validation
        if len(image_data) < 1000:
            return None, f"Downloaded data too small: {len(image_data)} bytes"
        
        # Check if it's actually an image
        try:
            test_image = Image.open(BytesIO(image_data))
            test_image.verify()
            print(f"    Successfully downloaded {len(image_data)} bytes")
            return image_data, None
        except:
            return None, "Downloaded data is not a valid image"
        
    except Exception as e:
        return None, f"Download failed: {str(e)}"

def convert_to_png(image_data):
    """Convert image data to PNG format - FIXED VERSION"""
    try:
        # Open the image
        if isinstance(image_data, bytes):
            image = Image.open(BytesIO(image_data))
        else:
            image = image_data
        
        print(f"    Image: {image.format}, Size: {image.size}, Mode: {image.mode}")
        
        # Ensure minimum reasonable size
        if image.size[0] < 50 or image.size[1] < 50:
            return None, f"Image too small: {image.size}"
        
        # Handle different color modes properly
        if image.mode == 'RGBA':
            # RGBA has alpha channel - use it as mask
            print("    Converting RGBA to RGB with alpha mask")
            background = Image.new('RGB', image.size, (255, 255, 255))
            background.paste(image, mask=image.split()[3])  # Use alpha channel
            image = background
            
        elif image.mode == 'LA':
            # LA has alpha channel - use it as mask  
            print("    Converting LA to RGB with alpha mask")
            background = Image.new('RGB', image.size, (255, 255, 255))
            background.paste(image, mask=image.split()[1])  # Use alpha channel
            image = background
            
        elif image.mode == 'P':
            # Palette mode - check if it has transparency
            print("    Converting palette mode to RGB")
            if 'transparency' in image.info:
                # Convert palette with transparency to RGBA first, then to RGB
                image = image.convert('RGBA')
                background = Image.new('RGB', image.size, (255, 255, 255))
                background.paste(image, mask=image.split()[3])
                image = background
            else:
                # No transparency, direct conversion
                image = image.convert('RGB')
                
        elif image.mode in ('L', 'RGB'):
            # Already in compatible format
            pass
            
        else:
            # Any other mode - convert to RGB
            print(f"    Converting {image.mode} to RGB")
            image = image.convert('RGB')
        
        # Save as PNG
        png_buffer = BytesIO()
        image.save(png_buffer, format='PNG', optimize=True, quality=95)
        png_data = png_buffer.getvalue()
        
        print(f"    Converted to PNG: {len(png_data)} bytes")
        return png_data, None
        
    except Exception as e:
        return None, f"Conversion error: {str(e)}"

def process_folders():
    """Main function to process all folders"""
    current_dir = os.getcwd()
    folders = [f for f in os.listdir(current_dir) 
              if os.path.isdir(os.path.join(current_dir, f)) and not f.startswith('.')]
    
    if not folders:
        print("No folders found in current directory")
        return
    
    print(f"Found {len(folders)} folders to process")
    
    # Setup Chrome driver
    driver = setup_driver()
    if not driver:
        print("Failed to setup Chrome driver. Exiting.")
        return
    
    processed = 0
    skipped = 0
    errors = 0
    
    try:
        for i, folder_name in enumerate(folders, 1):
            folder_path = os.path.join(current_dir, folder_name)
            cover_png_path = os.path.join(folder_path, "cover.png")
            cover_webp_path = os.path.join(folder_path, "cover.webp")
            cover_jpg_path = os.path.join(folder_path, "cover.jpg")
            
            print(f"\n[{i}/{len(folders)}] Processing folder: '{folder_name}'")
            
            # Check if cover already exists
            if os.path.exists(cover_png_path) or os.path.exists(cover_webp_path) or os.path.exists(cover_jpg_path):
                print(f"  ✓ Skipped - cover file already exists")
                skipped += 1
                continue
            
            # Search Bing Images
            print(f"  🔍 Searching Bing Images...")
            image_data, error = search_bing_images(folder_name, driver)
            
            # If main method fails, try screenshot capture
            if not image_data and error:
                print(f"  ⚠️ Main method failed: {error}")
                image_data, error = capture_first_bing_image_screenshot(folder_name, driver)
            
            if not image_data:
                print(f"  ❌ All methods failed: {error}")
                errors += 1
                continue
            
            # Convert to PNG
            print(f"  🔄 Converting to PNG...")
            png_data, error = convert_to_png(image_data)
            
            if error:
                print(f"  ❌ Conversion error: {error}")
                errors += 1
                continue
            
            # Save the PNG file
            try:
                with open(cover_png_path, 'wb') as f:
                    f.write(png_data)
                print(f"  ✅ Successfully saved cover.png ({len(png_data)} bytes)")
                processed += 1
            except Exception as e:
                print(f"  ❌ Error saving file: {str(e)}")
                errors += 1
            
            # Delay to be respectful to Bing
            time.sleep(3)
    
    except KeyboardInterrupt:
        print("\n\nProcess interrupted by user")
    
    finally:
        driver.quit()
    
    # Final summary
    print(f"\n{'='*50}")
    print(f"SUMMARY:")
    print(f"Total folders: {len(folders)}")
    print(f"Successfully processed: {processed}")
    print(f"Skipped (already have cover): {skipped}")
    print(f"Errors: {errors}")
    print(f"{'='*50}")

if __name__ == "__main__":
    print("BJJ Fanatics Cover Image Downloader v4.1 (Fixed)")
    print("="*50)
    
    # Check requirements
    try:
        import selenium
        from PIL import Image
        import requests
    except ImportError as e:
        print(f"Missing required package: {e}")
        print("\nPlease install required packages:")
        print("pip install selenium pillow requests")
        sys.exit(1)
    
    print("Starting folder processing with Bing Images...")
    process_folders()
