from pydantic import BaseModel
from typing import Optional

class TopScorerPrediction(BaseModel):
    player_name: str
    team_name:   str

class TopScorerResponse(BaseModel):
    uid:         str
    player_name: str
    team_name:   str
    points:      Optional[int] = None
    processed:   bool = False