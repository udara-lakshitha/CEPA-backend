import os
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, func
from sqlalchemy.orm import declarative_base, sessionmaker
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

NEON_DB_URL = os.getenv("DATABASE_URL")

if not NEON_DB_URL:
    raise ValueError("DATABASE_URL environment variable is missing!")

engine = create_engine(NEON_DB_URL, echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class JobVacancy(Base):
    __tablename__ = "job_vacancies"

    id = Column(Integer, primary_key=True, index=True)
    job_title = Column(String(255), nullable=False)
    company_name = Column(String(255), nullable=False)
    posted_age = Column(String(100))
    job_category = Column(String(100))
    job_description = Column(Text)
    job_requirements = Column(Text)
    required_skills = Column(Text)
    source_website = Column(String(100), nullable=False)
    source_url = Column(Text, unique=True, nullable=False)
    created_at = Column(DateTime, server_default=func.now())

def init_db():
    """Automatically creates defined tables in NeonDB if they do not exist."""
    Base.metadata.create_all(bind=engine)

def get_db():
    """Dependency helper to get DB session per API request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()