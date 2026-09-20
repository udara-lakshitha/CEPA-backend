import time
import re
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
from sqlalchemy.orm import Session
from database import JobVacancy
from scrapers.base import BaseScraper

class IkmanScraper(BaseScraper):
    source_name = "ikman.lk"

    def __init__(self, target_url: str = "https://ikman.lk/en/ads/sri-lanka/it-and-network-industry-jobs"):
        self.target_url = target_url

    def run(self, db: Session) -> int:
        inserted_count = 0
        
        with sync_playwright() as p:
            # Launch chromium with anti-bot detection flags
            browser = p.chromium.launch(
                headless=True,
                args=["--disable-blink-features=AutomationControlled"]
            )
            
            context = browser.new_context(
                viewport={"width": 1280, "height": 800},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            )
            
            page = context.new_page()
            
            print(f"[{self.source_name}] Navigating to {self.target_url}")
            page.goto(self.target_url, wait_until="domcontentloaded", timeout=60000)
            
            # Wait for list items to render on page
            try:
                page.wait_for_selector("li[class*='list-item']", timeout=10000)
            except Exception:
                # Fallback scroll to trigger lazy loading
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                time.sleep(2)

            soup = BeautifulSoup(page.content(), "html.parser")
            
            # Broadened selector to catch all variation card classes on ikman
            job_cards = soup.find_all("li", class_=re.compile(r"list-item|gtm-normal-ad|gtm-top-ad"))
            print(f"[{self.source_name}] Found {len(job_cards)} potential job listings.")

            for card in job_cards:
                try:
                    # Find link element inside card
                    link_elem = card.find("a", href=True)
                    if not link_elem:
                        continue

                    relative_url = link_elem["href"]
                    # Ignore non-ad links
                    if "/en/ad/" not in relative_url:
                        continue

                    full_url = f"https://ikman.lk{relative_url}" if not relative_url.startswith("http") else relative_url

                    # Check DB duplicate
                    if db.query(JobVacancy).filter_by(source_url=full_url).first():
                        print(f"[{self.source_name}] Skipping duplicate: {full_url}")
                        continue

                    # Extract Job Title
                    title_elem = card.find(["h2", "h3"]) or card.find(class_=re.compile(r"title"))
                    title = title_elem.get_text(strip=True) if title_elem else "IT Vacancy"

                    # Company & Date/Age
                    company_elem = card.find(class_=re.compile(r"description|company|poster"))
                    company = company_elem.get_text(strip=True) if company_elem else "Unspecified Employer"

                    posted_elem = card.find(class_=re.compile(r"updated-time|date"))
                    posted_age = posted_elem.get_text(strip=True) if posted_elem else "N/A"

                    # Open Detail Page
                    detail_page = context.new_page()
                    detail_page.goto(full_url, wait_until="domcontentloaded", timeout=30000)
                    detail_soup = BeautifulSoup(detail_page.content(), "html.parser")

                    # Extract full job details
                    desc_container = detail_soup.find(class_=re.compile(r"description-body|description|details"))
                    raw_desc = desc_container.get_text("\n", strip=True) if desc_container else "No description provided."

                    # Separate requirements if keywords exist
                    requirements = "N/A"
                    if any(k in raw_desc.lower() for k in ["requirement", "qualification", "skills"]):
                        parts = re.split(r"(?i)(requirements|qualifications|skills):", raw_desc)
                        if len(parts) > 2:
                            requirements = parts[-1].strip()

                    new_job = JobVacancy(
                        job_title=title,
                        company_name=company,
                        posted_age=posted_age,
                        job_category="IT & Network Industry",
                        job_description=raw_desc,
                        job_requirements=requirements,
                        source_website=self.source_name,
                        source_url=full_url
                    )

                    db.add(new_job)
                    db.commit()
                    inserted_count += 1
                    print(f"[{self.source_name}] Successfully saved: {title}")

                    detail_page.close()
                    time.sleep(1)

                except Exception as e:
                    db.rollback()
                    print(f"[{self.source_name}] Error scraping card: {e}")

            browser.close()
            
        return inserted_count