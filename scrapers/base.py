from abc import ABC, abstractmethod
from sqlalchemy.orm import Session

class BaseScraper(ABC):
    source_name: str

    @abstractmethod
    def run(self, db: Session) -> int:
        """Executes scraping logic and saves new records into DB. Returns count of inserted jobs."""
        pass