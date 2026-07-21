import asyncio
import os
import re
import shutil
import json
import random
import urllib.parse
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

OUTPUT_DIR = "output"
COURSES_DIR = os.path.join(OUTPUT_DIR, "Study Type", "Courses")
PROGRAM_DIR = os.path.join(OUTPUT_DIR, "Program")

def clean_extracted_text(text):
    if not text:
        return ""
    lines = text.splitlines()
    cleaned_lines = []
    for line in lines:
        cleaned_line = line.strip()
        if not cleaned_line:
            if cleaned_lines and cleaned_lines[-1] != "":
                cleaned_lines.append("")
        else:
            cleaned_lines.append(cleaned_line)
    while cleaned_lines and not cleaned_lines[0]:
        cleaned_lines.pop(0)
    while cleaned_lines and not cleaned_lines[-1]:
        cleaned_lines.pop()
    return "\n".join(cleaned_lines)

def clear_old_output():
    print("[INFO] Clearing old crawl data in output directory...")
    if os.path.exists(OUTPUT_DIR):
        for item in os.listdir(OUTPUT_DIR):
            item_path = os.path.join(OUTPUT_DIR, item)
            # Retain non-crawl evaluation result summaries if any, but clear crawl caches & data
            if item in ["Study Area", "Study Type", "Program", "checkpoint.json", ".cache", "crawler.log"]:
                if os.path.isdir(item_path):
                    shutil.rmtree(item_path)
                else:
                    os.remove(item_path)
    os.makedirs(COURSES_DIR, exist_ok=True)
    os.makedirs(PROGRAM_DIR, exist_ok=True)
    print("[SUCCESS] Output directory reset.")

async def crawl_mc271():
    clear_old_output()
    
    program_code = "MC271"
    program_url = f"https://handbook.rmit.edu.au/ords/r/rmit/catalogue/program?p5_code={program_code}"
    
    visited_courses = set()
    courses_to_visit = set()
    
    async with async_playwright() as p:
        print("[INFO] Launching Chromium browser...")
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        print(f"[INFO] Navigating to program page: {program_url}")
        await page.goto(program_url, timeout=45000)
        await page.wait_for_load_state("networkidle")
        await page.wait_for_timeout(3000)
        
        # Click expand buttons if available
        try:
            collapse_btns = await page.locator("button.pr_collapse").all()
            for btn in collapse_btns:
                await btn.click()
                await page.wait_for_timeout(500)
        except Exception as e:
            print(f"[WARN] Expanding collapse buttons: {e}")
            
        program_html = await page.content()
        soup = BeautifulSoup(program_html, "html.parser")

        # Save program detail
        prog_txt = clean_extracted_text(soup.get_text())
        with open(os.path.join(PROGRAM_DIR, f"{program_code}_Master_of_Artificial_Intelligence.html"), "w", encoding="utf-8") as f:
            f.write(program_html)
        with open(os.path.join(PROGRAM_DIR, f"{program_code}_Master_of_Artificial_Intelligence.txt"), "w", encoding="utf-8") as f:
            f.write(prog_txt)
        print(f"[SUCCESS] Saved program page for {program_code}")
        
        # Find all course links
        course_links = soup.find_all("a", href=True)
        for a in course_links:
            href = a["href"]
            match = re.search(r"p6_code=(\d+)", href)
            if match:
                courses_to_visit.add(match.group(1))
                
        # Fallback regex over full raw html
        raw_matches = re.findall(r"p6_code=(\d+)", program_html)
        for code in raw_matches:
            courses_to_visit.add(code)
            
        print(f"[INFO] Discovered {len(courses_to_visit)} initial courses for program {program_code}: {sorted(list(courses_to_visit))}")
        
        await page.close()
        
        # Crawl each course in the queue
        while courses_to_visit:
            current_code = courses_to_visit.pop()
            if current_code in visited_courses:
                continue
                
            visited_courses.add(current_code)
            course_url = f"https://handbook.rmit.edu.au/ords/r/rmit/catalogue/course?p6_code={current_code}"
            print(f"[INFO] Crawling course [{len(visited_courses)}/{len(visited_courses)+len(courses_to_visit)}] Code: {current_code}...")
            
            c_page = await browser.new_page()
            try:
                await c_page.goto(course_url, timeout=30000)
                await c_page.wait_for_load_state("networkidle")
                await c_page.wait_for_timeout(2000)
                
                c_html = await c_page.content()
                c_soup = BeautifulSoup(c_html, "lxml")
                
                title_el = c_soup.find(id="P6_TITLE")
                raw_title = title_el.text.strip() if title_el else f"Course_{current_code}"
                safe_title = "".join(c for c in raw_title if c.isalnum() or c in (' ', '_', '-')).rstrip()
                
                c_txt = clean_extracted_text(c_soup.get_text())
                
                html_path = os.path.join(COURSES_DIR, f"{current_code}_{safe_title}.html")
                txt_path = os.path.join(COURSES_DIR, f"{current_code}_{safe_title}.txt")
                
                with open(html_path, "w", encoding="utf-8") as f:
                    f.write(c_html)
                with open(txt_path, "w", encoding="utf-8") as f:
                    f.write(c_txt)
                    
                print(f"  [SUCCESS] Saved: {current_code} - {raw_title}")
                
                # Check for prerequisite references in this course to recursively discover related courses
                prereq_matches = re.findall(r"p6_code=(\d+)", c_html)
                for p_code in prereq_matches:
                    if p_code not in visited_courses:
                        courses_to_visit.add(p_code)
                        
                text_id_matches = re.findall(r"Course ID\s+(\d+)", c_txt)
                for p_code in text_id_matches:
                    if p_code not in visited_courses:
                        courses_to_visit.add(p_code)
                        
            except Exception as e:
                print(f"  [ERROR] Failed to crawl course {current_code}: {e}")
            finally:
                await c_page.close()
                await asyncio.sleep(random.uniform(0.5, 1.5))
                
        await browser.close()
        print(f"[SUCCESS] Crawl completed! Total courses processed: {len(visited_courses)}")

if __name__ == "__main__":
    asyncio.run(crawl_mc271())
