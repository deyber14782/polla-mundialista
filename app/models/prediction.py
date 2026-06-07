from pydantic import BaseModel
from typing import Optional
from enum import Enum

class PredictionStatus(str, Enum):
    pending   = "pending"
    locked    = "locked"
    processed = "processed"

class PredictionCreate(BaseModel):
    fixture_id:     int
    predicted_home: int
    predicted_away: int

class PredictionUpdate(BaseModel):
    predicted_home: int
    predicted_away: int

class PredictionResponse(BaseModel):
    id:             str
    uid:            str
    fixture_id:     int
    predicted_home: int
    predicted_away: int
    points:              Optional[int] = None
    classification_pts:  Optional[int] = None  # puntos por clasificación
    status:         PredictionStatus = PredictionStatus.pending
    processed:      bool = False
    home_team_name: Optional[str] = None
    away_team_name: Optional[str] = None
    home_team_logo: Optional[str] = None
    away_team_logo: Optional[str] = None
    kickoff:        Optional[str] = None
    phase:          Optional[str] = None
    real_home:      Optional[int] = None
    real_away:      Optional[int] = None