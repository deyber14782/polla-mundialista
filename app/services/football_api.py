import httpx
from app.core.config import settings

BASE_URL = "https://v3.football.api-sports.io"
WORLD_CUP_2026_ID = 1  # ID del Mundial 2026 — lo confirmaremos con la API

HEADERS = {
    "x-apisports-key": settings.API_FOOTBALL_KEY,
}

async def get_world_cup_fixtures() -> list[dict]:
    """Trae partidos del Mundial filtrando por fecha."""
    from datetime import date, timedelta
    
    all_fixtures = []
    async with httpx.AsyncClient() as client:
        # Buscar los últimos 3 días + hoy
        for days_ago in range(3, -1, -1):
            d = date.today() - timedelta(days=days_ago)
            response = await client.get(
                f"{BASE_URL}/fixtures",
                headers=HEADERS,
                params={"date": str(d)},
                timeout=15.0
            )
            response.raise_for_status()
            data = response.json()
            fixtures = data.get("response", [])
            # Filtrar solo Mundial (league id = 1)
            wc = [f for f in fixtures if f.get("league", {}).get("id") == WORLD_CUP_2026_ID]
            all_fixtures.extend(wc)
    
    return all_fixtures


async def get_live_fixtures() -> list[dict]:
    """Trae partidos en vivo del Mundial."""
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{BASE_URL}/fixtures",
            headers=HEADERS,
            params={"live": "all"},
            timeout=15.0
        )
        response.raise_for_status()
        data = response.json()
        # Filtrar solo Mundial
        return [f for f in data.get("response", []) if f.get("league", {}).get("id") == WORLD_CUP_2026_ID]


async def get_fixture_by_id(fixture_id: int) -> dict | None:
    """Trae un partido específico por su ID."""
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{BASE_URL}/fixtures",
            headers=HEADERS,
            params={"id": fixture_id},
            timeout=15.0
        )
        response.raise_for_status()
        data = response.json()
        results = data.get("response", [])
        return results[0] if results else None


async def get_world_cup_league_id() -> int | None:
    """
    Util para confirmar el ID correcto del Mundial 2026.
    Llama a este endpoint una sola vez para verificar.
    """
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{BASE_URL}/leagues",
            headers=HEADERS,
            params={"name": "FIFA World Cup", "type": "Cup"},
            timeout=15.0
        )
        response.raise_for_status()
        data = response.json()
        leagues = data.get("response", [])
        if leagues:
            return leagues[0]["league"]["id"]
        return None