from pydantic import BaseModel
from typing import Optional

class RankingEntry(BaseModel):
    position: int
    uid: str
    display_name: str
    photo_url: Optional[str] = None
    total_score: int = 0
    predictions_count: int = 0
    exact_results: int = 0
    correct_winners: int = 0
    accuracy: float = 0.0