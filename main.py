from fastapi import FastAPI, Depends, BackgroundTasks, HTTPException
from sqlalchemy.orm import Session
from typing import List

from database import init_db, get_db, JobVacancy
from scrapers.ikman import IkmanScraper
from scrapers.linkedin import LinkedInScraper

app = FastAPI(title="Sri Lanka IT Job Scraper API", version="1.0.0")

# Scraper Registry - easily add new scrapers here
SCRAPERS = {
    "ikman": IkmanScraper(),
    "linkedin": LinkedInScraper()
}

@app.on_event("startup")
def startup_event():
    """Initialize ORM models / create database tables on app start."""
    init_db()

@app.get("/")
def root():
    return {"status": "active", "message": "Scraper API is running"}

# --- SCRAPING ENDPOINTS ---

@app.post("/api/v1/scrape/{source_key}")
def trigger_scraper(source_key: str, db: Session = Depends(get_db)):
    """Triggers scraping for a specific platform by key (e.g., 'ikman')."""
    if source_key not in SCRAPERS:
        raise HTTPException(status_code=404, detail=f"Scraper '{source_key}' not found.")
    
    scraper = SCRAPERS[source_key]
    new_jobs = scraper.run(db)
    return {"status": "success", "source": source_key, "new_records_added": new_jobs}

# --- DASHBOARD CONSUMPTION ENDPOINTS ---

@app.get("/api/v1/jobs")
def get_jobs(skip: int = 0, limit: int = 50, db: Session = Depends(get_db)):
    """API Endpoint for future dashboard to fetch saved jobs."""
    jobs = db.query(JobVacancy).order_by(JobVacancy.created_at.desc()).offset(skip).limit(limit).all()
    return {"count": len(jobs), "data": jobs}

@app.get("/api/v1/jobs/stats")
def get_job_stats(db: Session = Depends(get_db)):
    """API Endpoint for dashboard statistics/charts."""
    total_count = db.query(JobVacancy).count()
    return {
        "total_jobs_scraped": total_count,
    }