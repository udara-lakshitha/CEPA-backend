import time
import re
import urllib.parse
import requests
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session
from database import JobVacancy
from scrapers.base import BaseScraper


class LinkedInScraper(BaseScraper):
    source_name = "linkedin"

    def __init__(self, keywords: str = "Software Engineer", location: str = "Sri Lanka"):
        self.keywords = keywords
        self.location = location

    def parse_dynamic_content(self, description_html: str) -> tuple[str, str, str]:
        """
        Dynamically processes the raw HTML description from LinkedIn.
        Extracts raw description, requirements, and key tech skills directly from the document.
        """
        if not description_html:
            return "No description available", "Not specified", "Not specified"

        soup = BeautifulSoup(description_html, "html.parser")

        # 1. Get full structured text
        full_text = soup.get_text("\n", strip=True)

        # 2. Dynamically extract requirement sections & bullet points
        lines = [line.strip() for line in full_text.split("\n") if line.strip()]
        
        requirement_lines = []
        is_requirement_block = False

        # Target headers commonly used by employers (case-insensitive)
        req_headers = [
            "requirement", "qualification", "what you need", "what we look for",
            "who you are", "must have", "nice to have", "competencies", "eligibility"
        ]

        for i, line in enumerate(lines):
            line_lower = line.lower()

            # Check if this line looks like a requirements header
            if any(h in line_lower for h in req_headers) and len(line) < 60:
                is_requirement_block = True
                continue

            # Check if we hit another header block (e.g. Benefits, About Company) to stop
            if is_requirement_block and any(h in line_lower for h in ["benefit", "about us", "we offer", "perk", "how to apply"]) and len(line) < 60:
                is_requirement_block = False

            if is_requirement_block:
                requirement_lines.append(line)

        # Fallback: If no explicit headers were detected, extract all bullet point items (li tags)
        if not requirement_lines:
            bullet_points = [li.get_text(strip=True) for li in soup.find_all("li") if len(li.get_text(strip=True)) > 5]
            if bullet_points:
                requirement_lines = bullet_points

        # 3. Dynamic Skill Isolation from Bullet Points & Phrases
        # Collect short candidate phrases (1-5 words) from extracted requirements
        extracted_skills = []
        for req in requirement_lines:
            # Look for skill lists usually separated by commas, slashes, or bullets
            parts = re.split(r"[,;•|/]", req)
            for part in parts:
                clean_part = part.strip()
                # Keep short technical phrases directly from the recruiter's bullet points
                if 2 <= len(clean_part) <= 35 and not any(verb in clean_part.lower() for verb in ["experience in", "ability to", "responsible for", "working with"]):
                    extracted_skills.append(clean_part)

        # Format deliverables
        job_requirements = "\n".join(requirement_lines[:15]) if requirement_lines else full_text[:1000]
        required_skills = " | ".join(list(dict.fromkeys(extracted_skills))[:12]) if extracted_skills else "Derived from description"

        return full_text, job_requirements, required_skills

    def run(self, db: Session) -> int:
        inserted_count = 0

        params = {
            "keywords": self.keywords,
            "location": self.location,
            "pageNum": "0",
            "start": "0"
        }

        search_url = f"https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?{urllib.parse.urlencode(params)}"

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
        }

        session = requests.Session()

        print(f"[{self.source_name}] Requesting LinkedIn listings for '{self.keywords}' in '{self.location}'...")
        response = session.get(search_url, headers=headers, timeout=20)

        if response.status_code != 200:
            print(f"[{self.source_name}] Request failed with status: {response.status_code}")
            return 0

        soup = BeautifulSoup(response.text, "html.parser")
        job_cards = soup.find_all("li")

        print(f"[{self.source_name}] Found {len(job_cards)} job cards.")

        for card in job_cards:
            try:
                title_elem = card.find("h3", class_=re.compile(r"base-search-card__title"))
                company_elem = card.find("h4", class_=re.compile(r"base-search-card__subtitle"))
                link_elem = card.find("a", class_=re.compile(r"base-card__full-link"))
                date_elem = card.find("time")

                if not title_elem or not link_elem:
                    continue

                title = title_elem.get_text(strip=True)
                company = company_elem.get_text(strip=True) if company_elem else "Unknown Company"
                raw_job_url = link_elem["href"].split("?")[0]
                posted_age = date_elem.get_text(strip=True) if date_elem else "Recent"

                # DB Deduplication
                if db.query(JobVacancy).filter_by(source_url=raw_job_url).first():
                    print(f"[{self.source_name}] Skipping duplicate: {title} @ {company}")
                    continue

                # Extract Job ID
                job_id_match = re.search(r"-(\d+)", raw_job_url)
                if not job_id_match:
                    continue

                job_id = job_id_match.group(1)
                detail_api_url = f"https://www.linkedin.com/jobs-guest/jobs/api/jobDetail/{job_id}"

                detail_resp = session.get(detail_api_url, headers=headers, timeout=15)

                full_desc = "No description available"
                requirements = "Not specified"
                skills = "Not specified"

                if detail_resp.status_code == 200:
                    detail_soup = BeautifulSoup(detail_resp.text, "html.parser")
                    desc_elem = detail_soup.find("div", class_=re.compile(r"show-more-less-html__markup"))

                    if desc_elem:
                        # Extract dynamically from the DOM text
                        full_desc, requirements, skills = self.parse_dynamic_content(str(desc_elem))

                new_job = JobVacancy(
                    job_title=title,
                    company_name=company,
                    posted_age=posted_age,
                    job_category="IT / Software Development",
                    job_description=full_desc[:3000],
                    job_requirements=requirements[:1500],
                    required_skills=skills[:1000],
                    source_website=self.source_name,
                    source_url=raw_job_url
                )

                db.add(new_job)
                db.commit()
                inserted_count += 1
                print(f"[{self.source_name}] Saved: {title} @ {company}")

                time.sleep(1)

            except Exception as e:
                db.rollback()
                print(f"[{self.source_name}] Error saving record: {e}")

        return inserted_count