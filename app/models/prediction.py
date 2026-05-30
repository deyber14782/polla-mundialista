from pydantic import BaseModel
from typing import Optional
from enum import Enum

class PredictionStatus(str, Enum):
    pending = "pending"       # partido no ha iniciado
    locked = "locked"         # partido en curso o finalizado
    processed = "processed"   # puntos calculados

class PredictionCreate(BaseModel):
    fixture_id: int
    predicted_home: int
    predicted_away: int

class PredictionUpdate(BaseModel):
    predicted_home: int
    predicted_away: int

class PredictionResponse(BaseModel):
    id: str
    uid: str
    fixture_id: int
    predicted_home: int
    predicted_away: int
    points: Optional[int] = None
    status: PredictionStatus = PredictionStatus.pending
    processed: bool = False
    # Info del partido embebida para no hacer doble consulta en el front
    home_team_name: Optional[str] = None
    away_team_name: Optional[str] = None
    home_team_logo: Optional[str] = None
    away_team_logo: Optional[str] = None
    kickoff: Optional[str] = None
    phase: Optional[str] = None
    real_home: Optional[int] = None
    real_away: Optional[int] = None