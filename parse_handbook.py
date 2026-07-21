import os
import re
import json
import logging
import urllib.parse
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("parse_handbook")

def parse_html_file(filepath):
    """Parses a single RMIT Course HTML file and extracts details."""
    try:
        # Use latin-1 to avoid decode errors (copyright signs etc.)
        with open(filepath, "r", encoding="latin-1") as f:
            html = f.read()
    except Exception as e:
        logger.error(f"Failed to read file {filepath}: {e}")
        return None

    soup = BeautifulSoup(html, "lxml")
    
    # Extract Course Code
    course_code_el = soup.find(id="P6_COURSE_CODE")
    course_code = course_code_el.text.strip() if course_code_el else None
    
    if not course_code:
        # Fallback to filename parsing
        filename = os.path.basename(filepath)
        match = re.match(r"^(\d+)_", filename)
        if match:
            course_code = match.group(1)
        else:
            return None

    # Extract Course Title
    title_el = soup.find(id="P6_TITLE")
    title = title_el.text.strip() if title_el else ""
    if title.startswith(course_code):
        title = re.sub(rf"^{course_code}\s*-\s*", "", title)

    # Extract Credits
    credits_el = soup.find(id="P6_HE_UNITS")
    credits = 12 # Default RMIT credit points value
    if credits_el:
        try:
            credits = int(credits_el.text.strip())
        except ValueError:
            pass

    # Extract School
    school_el = soup.find(id="P6_HE_DEPARTMENT")
    school = school_el.text.strip() if school_el else "Unknown"

    # Extract Coordinator Name and Email
    coord_name_el = soup.find(id="P6_WD_PERSON_FULL_NAME")
    coordinator = coord_name_el.text.strip() if coord_name_el else "Unknown"
    
    coord_email_el = soup.find(id="P6_WD_PERSON_EMAIL_CONTACTS")
    coordinator_email = coord_email_el.text.strip() if coord_email_el else "Unknown"

    # Extract Description
    descr_el = soup.find(id="P6_HE_COURSE_CRSE_DESCR") or soup.find(id="P6_VE_COURSE_CRSE_DESCR")
    description = ""
    if descr_el:
        # P6 elements contain HTML-escaped content
        escaped_html = descr_el.text.strip()
        descr_soup = BeautifulSoup(escaped_html, "html.parser")
        description = descr_soup.get_text().strip()

    # Extract Prerequisites
    prereqs = []
    prior_knowledge_el = soup.find(id="P6_HE_COURSE_PRIOR_KNOWLEDGE") or soup.find(id="P6_VE_COURSE_ENFORCED_REQ")
    if prior_knowledge_el:
        escaped_html = prior_knowledge_el.text.strip()
        prereq_soup = BeautifulSoup(escaped_html, "html.parser")
        
        # Look for links containing p6_code parameter
        links = prereq_soup.find_all("a")
        for link in links:
            href = link.get("href", "")
            parsed_url = urllib.parse.urlparse(href)
            query_params = urllib.parse.parse_qs(parsed_url.query)
            
            p6_code = query_params.get("p6_code")
            if p6_code:
                prereq_code = p6_code[0]
                prereq_title = link.text.strip()
                if prereq_code != course_code and prereq_code not in [p["course_id"] for p in prereqs]:
                    prereqs.append({
                        "course_id": prereq_code,
                        "title": prereq_title
                    })
                    
        # Fallback regex search for Course ID references in text (e.g., "(Course ID 034151)")
        text = prereq_soup.get_text()
        matches = re.findall(r"Course ID\s+(\d+)", text)
        for match in matches:
            if match != course_code and match not in [p["course_id"] for p in prereqs]:
                prereqs.append({
                    "course_id": match,
                    "title": "Unknown Course"
                })

    return {
        "course_id": course_code,
        "title": title,
        "credits": credits,
        "school": school,
        "coordinator": coordinator,
        "coordinator_email": coordinator_email,
        "description": description,
        "prerequisites": prereqs
    }

def build_graph(courses_dir, output_json_path="data/rmit_graph.json", output_ttl_path="data/rmit_graph.ttl"):
    """Crawls course HTML files and compiles them into a JSON graph and RDF Turtle file."""
    logger.info(f"Scanning directory for HTML files: {courses_dir}")
    
    courses = {}
    
    # Traverse directories to find HTML files
    for root, dirs, files in os.walk(courses_dir):
        for file in files:
            if file.endswith(".html") and not file.startswith("."):
                filepath = os.path.join(root, file)
                course_data = parse_html_file(filepath)
                if course_data:
                    c_id = course_data["course_id"]
                    # If duplicate found, keep the richer one or merge
                    if c_id in courses:
                        # Merge prerequisites
                        existing_prereqs = {p["course_id"] for p in courses[c_id]["prerequisites"]}
                        for p in course_data["prerequisites"]:
                            if p["course_id"] not in existing_prereqs:
                                courses[c_id]["prerequisites"].append(p)
                    else:
                        courses[c_id] = course_data
                        
    logger.info(f"Successfully parsed {len(courses)} courses.")
    
    # Save as JSON
    os.makedirs(os.path.dirname(output_json_path), exist_ok=True)
    with open(output_json_path, "w", encoding="utf-8") as f:
        json.dump(courses, f, indent=2)
    logger.info(f"Saved JSON Knowledge Graph to {output_json_path}")
    
    # Save as Turtle RDF
    with open(output_ttl_path, "w", encoding="utf-8") as f:
        f.write("@prefix rmit: <http://rmit.edu.au/handbook/> .\n")
        f.write("@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .\n\n")
        
        for c_id, course in courses.items():
            f.write(f"rmit:C{c_id} a rmit:Course ;\n")
            f.write(f"    rmit:courseId \"{c_id}\" ;\n")
            f.write(f"    rmit:title \"{course['title'].replace('\"', '\\\"')}\" ;\n")
            f.write(f"    rmit:credits {course['credits']} ;\n")
            f.write(f"    rmit:school \"{course['school'].replace('\"', '\\\"')}\" ;\n")
            f.write(f"    rmit:coordinator \"{course['coordinator'].replace('\"', '\\\"')}\" ;\n")
            f.write(f"    rmit:coordinatorEmail \"{course['coordinator_email'].replace('\"', '\\\"')}\" ;\n")
            
            # Prereqs
            prereq_uris = [f"rmit:C{p['course_id']}" for p in course["prerequisites"]]
            if prereq_uris:
                f.write(f"    rmit:requiresPrerequisite {', '.join(prereq_uris)} ;\n")
                
            f.write(f"    rmit:description \"\"\"{course['description'].replace('\"\"\"', '\\\"\\\"\\\"')}\"\"\" .\n\n")
            
    logger.info(f"Saved RDF Turtle Knowledge Graph to {output_ttl_path}")
    return courses

if __name__ == "__main__":
    courses_directory = "output/Study Type/Courses"
    build_graph(courses_directory)
