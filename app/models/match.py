from pydantic import BaseModel
from typing import Optional
from enum import Enum

class MatchStatus(str, Enum):
    not_started = "NS"      # No iniciado
    first_half = "1H"       # Primer tiempo
    halftime = "HT"         # Descanso
    second_half = "2H"      # Segundo tiempo
    finished = "FT"         # Finalizado
    postponed = "PST"       # Pospuesto

class MatchPhase(str, Enum):
    group = "group"
    round_of_16 = "round_of_16"
    quarterfinal = "quarterfinal"
    semifinal = "semifinal"
    third_place = "third_place"
    final = "final"

class TeamInfo(BaseModel):
    id: int
    name: str
    logo: str
    code: Optional[str] = None

class MatchScore(BaseModel):
    home: Optional[int] = None
    away: Optional[int] = None

class MatchResponse(BaseModel):
    fixture_id: int
    phase: MatchPhase
    group: Optional[str] = None         # ej. "Group A"
    home_team: TeamInfo
    away_team: TeamInfo
    kickoff: str                         # ISO 8601
    status: MatchStatus
    score: MatchScore
    venue: Optional[str] = None
    round: Optional[str] = None