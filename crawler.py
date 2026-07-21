import asyncio
import os
import re
import argparse
import sys
import json
import urllib.parse
import random
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

# Setup simple console colors
class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'

LOG_FILE_PATH = None

def write_to_log_file(level, msg):
    if LOG_FILE_PATH:
        # Strip ANSI escape codes (colors) from the log file output
        clean_msg = re.sub(r'\033\[[0-9;]*m', '', msg)
        try:
            with open(LOG_FILE_PATH, "a") as f:
                f.write(f"[{level}] {clean_msg}\n")
        except Exception:
            pass

def log_info(msg):
    print(f"{Colors.OKBLUE}[INFO]{Colors.ENDC} {msg}")
    write_to_log_file("INFO", msg)

def log_success(msg):
    print(f"{Colors.OKGREEN}[SUCCESS]{Colors.ENDC} {msg}")
    write_to_log_file("SUCCESS", msg)

def log_warn(msg):
    print(f"{Colors.WARNING}[WARN]{Colors.ENDC} {msg}")
    write_to_log_file("WARN", msg)

def log_error(msg):
    print(f"{Colors.FAIL}[ERROR]{Colors.ENDC} {msg}")
    write_to_log_file("ERROR", msg)

def clean_extracted_text(text):
    if not text:
        return ""
    lines = text.splitlines()
    cleaned_lines = []
    
    for line in lines:
        cleaned_line = line.strip()
        # Collapse multiple empty lines into at most one empty line
        if not cleaned_line:
            if cleaned_lines and cleaned_lines[-1] != "":
                cleaned_lines.append("")
        else:
            cleaned_lines.append(cleaned_line)
            
    # Remove leading and trailing empty lines
    while cleaned_lines and not cleaned_lines[0]:
        cleaned_lines.pop(0)
    while cleaned_lines and not cleaned_lines[-1]:
        cleaned_lines.pop()
        
    return "\n".join(cleaned_lines)

# Global structure of categories
categories_data = {
    "Study Type": {},
    "Study Area": {}
}

def load_checkpoint(output_dir):
    checkpoint_path = os.path.join(output_dir, "checkpoint.json")
    if os.path.exists(checkpoint_path):
        try:
            with open(checkpoint_path, "r") as f:
                return json.load(f)
        except Exception as e:
            log_warn(f"Failed to load checkpoint file: {e}. Starting fresh.")
    return {
        "discovered_categories": {},
        "completed_categories": [],
        "extracted_items": {}
    }

def save_checkpoint(checkpoint, output_dir):
    checkpoint_path = os.path.join(output_dir, "checkpoint.json")
    tmp_path = checkpoint_path + ".tmp"
    try:
        with open(tmp_path, "w") as f:
            json.dump(checkpoint, f, indent=2)
        os.replace(tmp_path, checkpoint_path)
    except Exception as e:
        log_error(f"Failed to save checkpoint: {e}")


async def discover_categories(page):
    log_info("Navigating to home page to discover Study Types and Study Areas...")
    await page.goto("https://handbook.rmit.edu.au/ords/r/rmit/catalogue/home")
    await page.wait_for_load_state("networkidle")
    await page.wait_for_timeout(2000)
    
    # 1. Discover Study Types
    study_type_links = await page.locator("a[href*='browse1?p3_browse_id=']").all()
    for link in study_type_links:
        name = (await link.inner_text()).strip()
        href = await link.get_attribute("href")
        full_url = f"https://handbook.rmit.edu.au{href}"
        categories_data["Study Type"][name] = full_url
        
    log_success(f"Discovered {len(categories_data['Study Type'])} Study Types: {list(categories_data['Study Type'].keys())}")
    
    # 2. Discover Study Areas
    study_area_tab = page.get_by_role("tab", name="Study Area")
    if await study_area_tab.count() > 0:
        await study_area_tab.click()
        await page.wait_for_timeout(1000)
    else:
        study_area_text = page.locator("text='Study Area'").first
        if await study_area_text.count() > 0:
            await study_area_text.click()
            await page.wait_for_timeout(1000)
            
    study_area_links = await page.locator("a[href*='browse2?p4_browse_id=']").all()
    for link in study_area_links:
        name = (await link.inner_text()).strip()
        href = await link.get_attribute("href")
        full_url = f"https://handbook.rmit.edu.au{href}"
        categories_data["Study Area"][name] = full_url
        
    log_success(f"Discovered {len(categories_data['Study Area'])} Study Areas: {list(categories_data['Study Area'].keys())}")

async def scroll_and_extract_links(page, url, category_name, max_scrolls, test_mode):
    log_info(f"Extracting items from {category_name} ({url})...")
    await page.goto(url)
    await page.wait_for_load_state("networkidle")
    await page.wait_for_timeout(2000)
    
    last_count = 0
    no_change_count = 0
    
    scroll_limit = 1 if test_mode else max_scrolls
    
    for scroll_idx in range(scroll_limit):
        # Query only the count to minimize Playwright IPC roundtrips and memory overhead
        current_count = await page.locator("a[href^='javascript:setDestinationUrl']").count()
        log_info(f"  [{category_name}] Scroll {scroll_idx+1}/{scroll_limit}: Cards in DOM: {current_count}")
        
        if test_mode:
            break
            
        if current_count == last_count:
            no_change_count += 1
            if no_change_count >= 3:
                log_info(f"  [{category_name}] No more new items loaded. Stopping scroll.")
                break
        else:
            no_change_count = 0
            
        last_count = current_count
        
        # Scroll down to load more
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        # Wait a random time between 2.0s and 3.5s to mimic human scrolling
        await page.wait_for_timeout(int(2000 + random.uniform(0, 1500)))
        
    # Extract links in a single JavaScript execution to prevent OOM / DOM memory bloat in Python
    log_info(f"  [{category_name}] Scroll completed. Extracting card details via page.evaluate...")
    cards_data = await page.evaluate("""() => {
        const links = Array.from(document.querySelectorAll("a[href^='javascript:setDestinationUrl']"));
        return links.map(link => ({
            href: link.getAttribute('href') || '',
            name: (link.innerText || '').trim()
        }));
    }""")
    
    items = {}
    for card in cards_data:
        href = card["href"]
        name = card["name"]
        
        # Extract parameters: setDestinationUrl(130, 'type', session_id, 'NO', 'code')
        match = re.search(r"setDestinationUrl\(130,\s*'([^']*)',\s*(\d+),\s*'NO',\s*'([^']*)'\)", href)
        if match:
            item_type = match.group(1)
            session_id = match.group(2)
            code = match.group(3)
            
            # Use clean name (remove codes or duplicate details)
            if code not in items:
                items[code] = {
                    "name": name,
                    "type": item_type,
                    "session_id": session_id,
                    "href": href
                }
                
    log_info(f"  [{category_name}] Total unique items extracted: {len(items)}")
    return items

async def download_item_detail(browser, category_url, item_type, session_id, code, name, cache_dir, retries=3):
    cache_path_txt = os.path.join(cache_dir, f"{item_type}_{code}.txt")
    cache_path_html = os.path.join(cache_dir, f"{item_type}_{code}.html")
    
    if os.path.exists(cache_path_txt) and os.path.exists(cache_path_html):
        # Read from cache
        with open(cache_path_txt, "r") as f:
            text_content = f.read()
        # Ensure cached text is also cleaned
        text_content = clean_extracted_text(text_content)
        with open(cache_path_html, "r") as f:
            html_content = f.read()
        return text_content, html_content

    # Load page to fetch details with retries
    for attempt in range(retries):
        page = await browser.new_page()
        try:
            # Load the browse page first to initialize session cookies
            await page.goto(category_url, timeout=30000)
            await page.wait_for_load_state("networkidle")
            # Wait a random delay between 1.0s and 2.5s
            await page.wait_for_timeout(int(1000 + random.uniform(0, 1500)))
            
            # Execute redirect JS
            js_call = f"setDestinationUrl(130, '{item_type}', {session_id}, 'NO', '{code}')"
            async with page.expect_navigation(timeout=30000):
                await page.evaluate(js_call)
                
            await page.wait_for_load_state("networkidle")
            # Wait a random delay between 2.0s and 3.5s for details to fully load
            await page.wait_for_timeout(int(2000 + random.uniform(0, 1500)))
            
            html_content = await page.content()
            soup = BeautifulSoup(html_content, "lxml")
            
            # Clean details by taking inner text of body or main
            body = soup.find("body")
            text_content = body.get_text() if body else soup.get_text()
            text_content = clean_extracted_text(text_content)
            
            # Validation: Ensure page detail content actually loaded
            # If length is very small and code isn't in content, it failed
            if code not in text_content and len(text_content) < 1500:
                raise Exception("Page loaded but detail content is missing (empty shell / session timeout)")
                
            # Save to cache
            with open(cache_path_txt, "w") as f:
                f.write(text_content)
            with open(cache_path_html, "w") as f:
                f.write(html_content)
                
            return text_content, html_content
            
        except Exception as e:
            log_warn(f"  Attempt {attempt+1}/{retries} failed for {code} - {name}: {e}")
            if attempt < retries - 1:
                # Add jitter to the retry backoff delay
                delay = (attempt + 1) * 3 + random.uniform(1.0, 3.0)
                log_info(f"  Waiting {delay:.2f}s before retrying...")
                await asyncio.sleep(delay)
        finally:
            await page.close()
            
    raise Exception(f"Failed to download details for {code} after {retries} attempts.")

async def worker(queue, browser, cache_dir, output_dir, delay, retries):
    while True:
        task = await queue.get()
        if task is None:
            queue.task_done()
            break
            
        section, category_url, category_name, code, item_data = task
        item_type = item_data["type"]
        session_id = item_data["session_id"]
        name = item_data["name"]
        
        log_info(f"  [Detail Queue] Processing {code} - {name} (Category: {category_name})...")
        try:
            txt, html = await download_item_detail(browser, category_url, item_type, session_id, code, name, cache_dir, retries)
            
            # Save directly into final folder structure in real-time
            cat_dir = os.path.join(output_dir, section, category_name.replace("/", "_"))
            os.makedirs(cat_dir, exist_ok=True)
            
            safe_name = "".join(c for c in name if c.isalnum() or c in (' ', '_', '-')).rstrip()
            txt_file_path = os.path.join(cat_dir, f"{code}_{safe_name}.txt")
            html_file_path = os.path.join(cat_dir, f"{code}_{safe_name}.html")
            
            with open(txt_file_path, "w") as f:
                f.write(txt)
            with open(html_file_path, "w") as f:
                f.write(html)
                
            log_success(f"  [Detail Queue] Successfully saved {code} under {section}/{category_name}")
        except Exception as e:
            log_error(f"  [Detail Queue] Failed to download/save details for {code} - {name}: {e}")
            
        # Throttling delay between requests (randomized by +/- 50% to mimic human patterns)
        if delay > 0:
            random_delay = random.uniform(delay * 0.5, delay * 1.5)
            await asyncio.sleep(random_delay)
            
        queue.task_done()

async def main_async(args):
    # Setup folders
    output_dir = args.output_dir
    cache_dir = os.path.join(output_dir, ".cache")
    os.makedirs(cache_dir, exist_ok=True)
    
    # Setup log file path
    global LOG_FILE_PATH
    LOG_FILE_PATH = os.path.join(output_dir, args.log_file)
    # Clear log file from previous run if any
    if os.path.exists(LOG_FILE_PATH):
        os.remove(LOG_FILE_PATH)
        
    log_info(f"Log file initialized at: {LOG_FILE_PATH}")
    
    # Load checkpoint
    checkpoint = {
        "discovered_categories": {},
        "completed_categories": [],
        "extracted_items": {}
    } if args.fresh else load_checkpoint(output_dir)
    
    # Init Playwright
    async with async_playwright() as p:
        log_info("Launching headless browser...")
        browser = await p.chromium.launch(headless=True)
        
        # 1. Discover all categories
        global categories_data
        if checkpoint.get("discovered_categories"):
            categories_data = checkpoint["discovered_categories"]
            log_success("Loaded discovered categories from checkpoint.")
            log_info(f"  Study Types: {list(categories_data.get('Study Type', {}).keys())}")
            log_info(f"  Study Areas: {list(categories_data.get('Study Area', {}).keys())}")
        else:
            discovery_page = await browser.new_page()
            await discover_categories(discovery_page)
            await discovery_page.close()
            checkpoint["discovered_categories"] = categories_data
            save_checkpoint(checkpoint, output_dir)
        
        # 2. Process category by category (scroll then download details immediately)
        main_sections = ["Study Type", "Study Area"]
        categories_to_crawl = {}
        
        for section in main_sections:
            categories_to_crawl[section] = {}
            names = list(categories_data.get(section, {}).keys())
            if args.test_mode:
                # Limit to 1 category per section in test mode
                if names:
                    categories_to_crawl[section][names[0]] = categories_data[section][names[0]]
            else:
                categories_to_crawl[section] = categories_data.get(section, {})
                
        # For each category, scroll to extract links and download their details immediately
        for section, cats in categories_to_crawl.items():
            for cat_name, cat_url in cats.items():
                cat_key = f"{section} -> {cat_name}"
                
                # Check checkpoint to see if already fully completed
                if cat_key in checkpoint.get("completed_categories", []):
                    log_success(f"Category already completed: '{cat_key}'. Skipping.")
                    continue
                
                log_info("")
                log_info("=" * 60)
                log_info(f"PROCESSING CATEGORY: {cat_key}")
                log_info("=" * 60)
                
                # Retrieve extracted items from checkpoint or scroll to extract fresh ones
                items = {}
                if cat_key in checkpoint.get("extracted_items", {}):
                    items = checkpoint["extracted_items"][cat_key]
                    log_success(f"Loaded {len(items)} extracted items from checkpoint for category: '{cat_name}'")
                else:
                    # Scroll and extract links for this category
                    discovery_page = await browser.new_page()
                    items = await scroll_and_extract_links(discovery_page, cat_url, cat_name, args.max_scrolls, args.test_mode)
                    await discovery_page.close()
                    
                    # Store in checkpoint to prevent re-scrolling if crash occurs during downloads
                    if "extracted_items" not in checkpoint:
                        checkpoint["extracted_items"] = {}
                    checkpoint["extracted_items"][cat_key] = items
                    save_checkpoint(checkpoint, output_dir)
                
                if not items:
                    log_warn(f"No items discovered under category '{cat_name}'")
                    # Even if empty, mark category as completed to prevent re-crawling
                    if "completed_categories" not in checkpoint:
                        checkpoint["completed_categories"] = []
                    checkpoint["completed_categories"].append(cat_key)
                    save_checkpoint(checkpoint, output_dir)
                    continue
                    
                # Create detail downloader queue for this category
                queue = asyncio.Queue()
                item_codes = list(items.keys())
                if args.test_mode:
                    item_codes = item_codes[:3]  # Limit to 3 items in test mode
                    
                for code in item_codes:
                    await queue.put((section, cat_url, cat_name, code, items[code]))
                    
                log_info(f"Detail queue for '{cat_name}' initialized with {queue.qsize()} download tasks.")
                
                # Start workers
                concurrency = args.concurrency
                workers = []
                for _ in range(concurrency):
                    w = asyncio.create_task(worker(queue, browser, cache_dir, output_dir, args.delay, args.retries))
                    workers.append(w)
                    
                # Wait for current category details to finish processing
                await queue.join()
                
                # Stop workers
                for _ in range(concurrency):
                    await queue.put(None)
                await asyncio.gather(*workers)
                
                # Mark category as fully completed
                if "completed_categories" not in checkpoint:
                    checkpoint["completed_categories"] = []
                if cat_key not in checkpoint["completed_categories"]:
                    checkpoint["completed_categories"].append(cat_key)
                save_checkpoint(checkpoint, output_dir)
                
                log_success(f"Successfully processed category: {cat_name}")
        
        await browser.close()
        log_success(f"Crawl completed successfully! Outputs saved to {output_dir}")
        
        await browser.close()
        log_success(f"Crawl completed successfully! Outputs saved to {output_dir}")

def main():
    parser = argparse.ArgumentParser(description="RMIT Handbook Scraper")
    parser.add_argument("--output-dir", default="output", help="Directory where files will be saved")
    parser.add_argument("--test-mode", action="store_true", help="Run in test mode (limit scrolling and page downloads)")
    parser.add_argument("--concurrency", type=int, default=5, help="Number of concurrent pages to fetch details")
    parser.add_argument("--max-scrolls", type=int, default=600, help="Max scroll iterations per category")
    parser.add_argument("--log-file", default="crawler.log", help="Name of the log file to save in the output directory")
    parser.add_argument("--delay", type=float, default=8, help="Base delay (in seconds) between requests; will be randomized by +/- 50% to mimic human patterns")
    parser.add_argument("--retries", type=int, default=5, help="Number of download retries on timeout/failure")
    parser.add_argument("--fresh", action="store_true", help="Ignore existing checkpoint and start crawl from scratch")
    
    args = parser.parse_args()
    
    # Run async main
    asyncio.run(main_async(args))

if __name__ == "__main__":
    main()
