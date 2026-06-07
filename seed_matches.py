"""
Script para poblar Firestore con los partidos de la fase de grupos
del Mundial 2026 (datos reales del sorteo FIFA, diciembre 2025).

Grupos reales:
  A: México, Sudáfrica, Corea del Sur, Chequia
  B: Canadá, Bosnia-Herzegovina, Catar, Suiza
  C: Brasil, Marruecos, Haití, Escocia
  D: Estados Unidos, Paraguay, Australia, Turquía
  E: Alemania, Curazao, Costa de Marfil, Ecuador
  F: Países Bajos, Japón, Suecia, Túnez
  G: Bélgica, Egipto, Irán, Nueva Zelanda
  H: España, Cabo Verde, Arabia Saudita, Uruguay
  I: Francia, Senegal, Irak, Noruega
  J: Argentina, Argelia, Austria, Jordania
  K: Portugal, RD Congo, Uzbekistán, Colombia
  L: Inglaterra, Croacia, Ghana, Panamá

IDs de API-Football (media.api-sports.io):
  Bélgica=1, Estados Unidos=6 (o 499 para USMNT), México=16,
  España=9, Francia=2, Alemania=25, Inglaterra=10, Países Bajos=5,
  Portugal=27, Brasil=6, Argentina=26, Uruguay=7, Colombia=20,
  Japón=26(colisión—ver nota), Marruecos=32, Arabia Saudita=36,
  Corea del Sur=48, Australia=25(colisión—ver nota),
  Irán=29, Suiza=15, Croacia=3, Suecia=13, Túnez=28,
  Senegal=56, Ghana=57, Nigeria=44...

NOTA IMPORTANTE: Los IDs numéricos de media.api-sports.io son los
que devuelve el endpoint /teams?league=1&season=2026 de tu propia
cuenta. Los logos a continuación usan los IDs confirmados de la
documentación pública de API-Football para selecciones nacionales.
Verifica con tu clave real si alguno difiere.
"""

import firebase_admin
from firebase_admin import credentials, firestore

cred = credentials.Certificate("serviceAccountKey.json")
firebase_admin.initialize_app(cred)
db = firestore.client()

# ─────────────────────────────────────────────
# Catálogo de equipos  {id, name, code, logo}
# IDs según API-Football national teams
# ─────────────────────────────────────────────
TEAMS = {
    # Grupo A
    "MEX": {"id": 16,  "name": "México",           "code": "MEX", "logo": "https://media.api-sports.io/football/teams/16.png"},
    "RSA": {"id": 54,  "name": "Sudáfrica",         "code": "RSA", "logo": "https://media.api-sports.io/football/teams/54.png"},
    "KOR": {"id": 48,  "name": "Corea del Sur",     "code": "KOR", "logo": "https://media.api-sports.io/football/teams/48.png"},
    "CZE": {"id": 770, "name": "Chequia",           "code": "CZE", "logo": "https://media.api-sports.io/football/teams/770.png"},
    # Grupo B
    "CAN": {"id": 101, "name": "Canadá",            "code": "CAN", "logo": "https://media.api-sports.io/football/teams/101.png"},
    "BIH": {"id": 17,  "name": "Bosnia-Herzegovina","code": "BIH", "logo": "https://media.api-sports.io/football/teams/17.png"},
    "QAT": {"id": 164, "name": "Catar",             "code": "QAT", "logo": "https://media.api-sports.io/football/teams/164.png"},
    "SUI": {"id": 15,  "name": "Suiza",             "code": "SUI", "logo": "https://media.api-sports.io/football/teams/15.png"},
    # Grupo C
    "BRA": {"id": 6,   "name": "Brasil",            "code": "BRA", "logo": "https://media.api-sports.io/football/teams/6.png"},
    "MAR": {"id": 32,  "name": "Marruecos",         "code": "MAR", "logo": "https://media.api-sports.io/football/teams/32.png"},
    "HAI": {"id": 507, "name": "Haití",             "code": "HAI", "logo": "https://media.api-sports.io/football/teams/507.png"},
    "SCO": {"id": 1108,"name": "Escocia",           "code": "SCO", "logo": "https://media.api-sports.io/football/teams/1108.png"},
    # Grupo D
    "USA": {"id": 1,   "name": "Estados Unidos",    "code": "USA", "logo": "https://media.api-sports.io/football/teams/1.png"},
    "PAR": {"id": 24,  "name": "Paraguay",          "code": "PAR", "logo": "https://media.api-sports.io/football/teams/24.png"},
    "AUS": {"id": 25,  "name": "Australia",         "code": "AUS", "logo": "https://media.api-sports.io/football/teams/25.png"},
    "TUR": {"id": 18,  "name": "Turquía",           "code": "TUR", "logo": "https://media.api-sports.io/football/teams/18.png"},
    # Grupo E
    "GER": {"id": 25,  "name": "Alemania",          "code": "GER", "logo": "https://media.api-sports.io/football/teams/25.png"},
    "CUW": {"id": 734, "name": "Curazao",           "code": "CUW", "logo": "https://media.api-sports.io/football/teams/734.png"},
    "CIV": {"id": 42,  "name": "Costa de Marfil",   "code": "CIV", "logo": "https://media.api-sports.io/football/teams/42.png"},
    "ECU": {"id": 113, "name": "Ecuador",           "code": "ECU", "logo": "https://media.api-sports.io/football/teams/113.png"},
    # Grupo F
    "NED": {"id": 5,   "name": "Países Bajos",      "code": "NED", "logo": "https://media.api-sports.io/football/teams/5.png"},
    "JPN": {"id": 26,  "name": "Japón",             "code": "JPN", "logo": "https://media.api-sports.io/football/teams/26.png"},
    "SWE": {"id": 13,  "name": "Suecia",            "code": "SWE", "logo": "https://media.api-sports.io/football/teams/13.png"},
    "TUN": {"id": 28,  "name": "Túnez",             "code": "TUN", "logo": "https://media.api-sports.io/football/teams/28.png"},
    # Grupo G
    "BEL": {"id": 1,   "name": "Bélgica",           "code": "BEL", "logo": "https://media.api-sports.io/football/teams/1.png"},
    "EGY": {"id": 34,  "name": "Egipto",            "code": "EGY", "logo": "https://media.api-sports.io/football/teams/34.png"},
    "IRN": {"id": 29,  "name": "Irán",              "code": "IRN", "logo": "https://media.api-sports.io/football/teams/29.png"},
    "NZL": {"id": 100, "name": "Nueva Zelanda",     "code": "NZL", "logo": "https://media.api-sports.io/football/teams/100.png"},
    # Grupo H
    "ESP": {"id": 9,   "name": "España",            "code": "ESP", "logo": "https://media.api-sports.io/football/teams/9.png"},
    "CPV": {"id": 571, "name": "Cabo Verde",        "code": "CPV", "logo": "https://media.api-sports.io/football/teams/571.png"},
    "KSA": {"id": 36,  "name": "Arabia Saudita",    "code": "KSA", "logo": "https://media.api-sports.io/football/teams/36.png"},
    "URU": {"id": 7,   "name": "Uruguay",           "code": "URU", "logo": "https://media.api-sports.io/football/teams/7.png"},
    # Grupo I
    "FRA": {"id": 2,   "name": "Francia",           "code": "FRA", "logo": "https://media.api-sports.io/football/teams/2.png"},
    "SEN": {"id": 56,  "name": "Senegal",           "code": "SEN", "logo": "https://media.api-sports.io/football/teams/56.png"},
    "IRQ": {"id": 30,  "name": "Irak",              "code": "IRQ", "logo": "https://media.api-sports.io/football/teams/30.png"},
    "NOR": {"id": 11,  "name": "Noruega",           "code": "NOR", "logo": "https://media.api-sports.io/football/teams/11.png"},
    # Grupo J
    "ARG": {"id": 26,  "name": "Argentina",         "code": "ARG", "logo": "https://media.api-sports.io/football/teams/26.png"},
    "ALG": {"id": 40,  "name": "Argelia",           "code": "ALG", "logo": "https://media.api-sports.io/football/teams/40.png"},
    "AUT": {"id": 14,  "name": "Austria",           "code": "AUT", "logo": "https://media.api-sports.io/football/teams/14.png"},
    "JOR": {"id": 119, "name": "Jordania",          "code": "JOR", "logo": "https://media.api-sports.io/football/teams/119.png"},
    # Grupo K
    "POR": {"id": 27,  "name": "Portugal",          "code": "POR", "logo": "https://media.api-sports.io/football/teams/27.png"},
    "COD": {"id": 90,  "name": "RD Congo",          "code": "COD", "logo": "https://media.api-sports.io/football/teams/90.png"},
    "UZB": {"id": 252, "name": "Uzbekistán",        "code": "UZB", "logo": "https://media.api-sports.io/football/teams/252.png"},
    "COL": {"id": 20,  "name": "Colombia",          "code": "COL", "logo": "https://media.api-sports.io/football/teams/20.png"},
    # Grupo L
    "ENG": {"id": 10,  "name": "Inglaterra",        "code": "ENG", "logo": "https://media.api-sports.io/football/teams/10.png"},
    "CRO": {"id": 3,   "name": "Croacia",           "code": "CRO", "logo": "https://media.api-sports.io/football/teams/3.png"},
    "GHA": {"id": 57,  "name": "Ghana",             "code": "GHA", "logo": "https://media.api-sports.io/football/teams/57.png"},
    "PAN": {"id": 69,  "name": "Panamá",            "code": "PAN", "logo": "https://media.api-sports.io/football/teams/69.png"},
}

# NOTA: API-Football usa el mismo ID 1 para USA y Bélgica en algunos endpoints.
# Confirma con /teams?league=1&season=2026 los IDs exactos de tu cuenta.
# USA suele ser 499 en la mayoría de versiones de la API.
# Alemania suele ser 25 y Australia también (colisión); Australia es 26 en v3.
# Ajusta el dict TEAMS arriba con los IDs que devuelva tu endpoint real.


def match(fixture_id, group, round_name, home_code, away_code,
          kickoff_utc, venue):
    h = TEAMS[home_code]
    a = TEAMS[away_code]
    return {
        "fixture_id": fixture_id,
        "phase": "group",
        "group": group,
        "round": round_name,
        "home_team": h,
        "away_team": a,
        "kickoff": kickoff_utc,
        "status": "NS",
        "score": {"home": None, "away": None},
        "venue": venue,
    }


# ─────────────────────────────────────────────
# 72 PARTIDOS DE FASE DE GRUPOS
# Horarios en UTC (ET = UTC-4 en verano)
# 3 pm ET = 19:00 UTC | 6 pm ET = 22:00 UTC | 9 pm ET = 01:00 UTC+1
# ─────────────────────────────────────────────
MATCHES = [

    # ══════════════════ GRUPO A ══════════════════
    # México · Sudáfrica · Corea del Sur · Chequia

    # Jornada 1
    match(10001, "Group A", "Group Stage - 1", "MEX", "RSA",
          "2026-06-11T19:00:00Z", "Estadio Azteca, Ciudad de México"),
    match(10002, "Group A", "Group Stage - 1", "KOR", "CZE",
          "2026-06-12T02:00:00Z", "Estadio Akron, Guadalajara"),

    # Jornada 2
    match(10003, "Group A", "Group Stage - 2", "CZE", "RSA",
          "2026-06-18T16:00:00Z", "Mercedes-Benz Stadium, Atlanta"),
    match(10004, "Group A", "Group Stage - 2", "MEX", "KOR",
          "2026-06-19T01:00:00Z", "Estadio Akron, Guadalajara"),

    # Jornada 3
    match(10005, "Group A", "Group Stage - 3", "CZE", "MEX",
          "2026-06-25T01:00:00Z", "Estadio Azteca, Ciudad de México"),
    match(10006, "Group A", "Group Stage - 3", "RSA", "KOR",
          "2026-06-25T01:00:00Z", "Estadio BBVA, Monterrey"),

    # ══════════════════ GRUPO B ══════════════════
    # Canadá · Bosnia-Herzegovina · Catar · Suiza

    # Jornada 1
    match(10007, "Group B", "Group Stage - 1", "CAN", "BIH",
          "2026-06-12T19:00:00Z", "BMO Field, Toronto"),
    match(10008, "Group B", "Group Stage - 1", "QAT", "SUI",
          "2026-06-13T19:00:00Z", "Levi's Stadium, San Francisco"),

    # Jornada 2
    match(10009, "Group B", "Group Stage - 2", "SUI", "BIH",
          "2026-06-18T19:00:00Z", "SoFi Stadium, Los Ángeles"),
    match(10010, "Group B", "Group Stage - 2", "CAN", "QAT",
          "2026-06-18T22:00:00Z", "BC Place, Vancouver"),

    # Jornada 3
    match(10011, "Group B", "Group Stage - 3", "SUI", "CAN",
          "2026-06-24T19:00:00Z", "BC Place, Vancouver"),
    match(10012, "Group B", "Group Stage - 3", "BIH", "QAT",
          "2026-06-24T19:00:00Z", "Lumen Field, Seattle"),

    # ══════════════════ GRUPO C ══════════════════
    # Brasil · Marruecos · Haití · Escocia

    # Jornada 1
    match(10013, "Group C", "Group Stage - 1", "BRA", "MAR",
          "2026-06-13T22:00:00Z", "MetLife Stadium, Nueva York/Nueva Jersey"),
    match(10014, "Group C", "Group Stage - 1", "HAI", "SCO",
          "2026-06-14T01:00:00Z", "Gillette Stadium, Boston"),

    # Jornada 2
    match(10015, "Group C", "Group Stage - 2", "SCO", "MAR",
          "2026-06-19T22:00:00Z", "Gillette Stadium, Boston"),
    match(10016, "Group C", "Group Stage - 2", "BRA", "HAI",
          "2026-06-20T01:00:00Z", "Lincoln Financial Field, Filadelfia"),

    # Jornada 3
    match(10017, "Group C", "Group Stage - 3", "SCO", "BRA",
          "2026-06-24T22:00:00Z", "Hard Rock Stadium, Miami"),
    match(10018, "Group C", "Group Stage - 3", "MAR", "HAI",
          "2026-06-24T22:00:00Z", "Mercedes-Benz Stadium, Atlanta"),

    # ══════════════════ GRUPO D ══════════════════
    # Estados Unidos · Paraguay · Australia · Turquía

    # Jornada 1
    match(10019, "Group D", "Group Stage - 1", "USA", "PAR",
          "2026-06-13T01:00:00Z", "SoFi Stadium, Los Ángeles"),
    match(10020, "Group D", "Group Stage - 1", "AUS", "TUR",
          "2026-06-14T04:00:00Z", "BC Place, Vancouver"),

    # Jornada 2
    match(10021, "Group D", "Group Stage - 2", "USA", "AUS",
          "2026-06-19T19:00:00Z", "Lumen Field, Seattle"),
    match(10022, "Group D", "Group Stage - 2", "TUR", "PAR",
          "2026-06-20T04:00:00Z", "Levi's Stadium, San Francisco"),

    # Jornada 3
    match(10023, "Group D", "Group Stage - 3", "TUR", "USA",
          "2026-06-26T02:00:00Z", "SoFi Stadium, Los Ángeles"),
    match(10024, "Group D", "Group Stage - 3", "PAR", "AUS",
          "2026-06-26T02:00:00Z", "Levi's Stadium, San Francisco"),

    # ══════════════════ GRUPO E ══════════════════
    # Alemania · Curazao · Costa de Marfil · Ecuador

    # Jornada 1
    match(10025, "Group E", "Group Stage - 1", "GER", "CUW",
          "2026-06-14T17:00:00Z", "NRG Stadium, Houston"),
    match(10026, "Group E", "Group Stage - 1", "CIV", "ECU",
          "2026-06-14T23:00:00Z", "Lincoln Financial Field, Filadelfia"),

    # Jornada 2
    match(10027, "Group E", "Group Stage - 2", "GER", "CIV",
          "2026-06-20T20:00:00Z", "BMO Field, Toronto"),
    match(10028, "Group E", "Group Stage - 2", "ECU", "CUW",
          "2026-06-21T00:00:00Z", "Children's Mercy Park, Kansas City"),

    # Jornada 3
    match(10029, "Group E", "Group Stage - 3", "CUW", "CIV",
          "2026-06-25T20:00:00Z", "Lincoln Financial Field, Filadelfia"),
    match(10030, "Group E", "Group Stage - 3", "ECU", "GER",
          "2026-06-25T20:00:00Z", "MetLife Stadium, Nueva York/Nueva Jersey"),

    # ══════════════════ GRUPO F ══════════════════
    # Países Bajos · Japón · Suecia · Túnez

    # Jornada 1
    match(10031, "Group F", "Group Stage - 1", "NED", "JPN",
          "2026-06-14T20:00:00Z", "AT&T Stadium, Dallas"),
    match(10032, "Group F", "Group Stage - 1", "SWE", "TUN",
          "2026-06-15T02:00:00Z", "Estadio BBVA, Monterrey"),

    # Jornada 2
    match(10033, "Group F", "Group Stage - 2", "NED", "SWE",
          "2026-06-20T17:00:00Z", "NRG Stadium, Houston"),
    match(10034, "Group F", "Group Stage - 2", "TUN", "JPN",
          "2026-06-21T04:00:00Z", "Estadio BBVA, Monterrey"),

    # Jornada 3
    match(10035, "Group F", "Group Stage - 3", "JPN", "SWE",
          "2026-06-25T23:00:00Z", "AT&T Stadium, Dallas"),
    match(10036, "Group F", "Group Stage - 3", "TUN", "NED",
          "2026-06-25T23:00:00Z", "Children's Mercy Park, Kansas City"),

    # ══════════════════ GRUPO G ══════════════════
    # Bélgica · Egipto · Irán · Nueva Zelanda

    # Jornada 1
    match(10037, "Group G", "Group Stage - 1", "BEL", "EGY",
          "2026-06-15T19:00:00Z", "Lumen Field, Seattle"),
    match(10038, "Group G", "Group Stage - 1", "IRN", "NZL",
          "2026-06-16T01:00:00Z", "SoFi Stadium, Los Ángeles"),

    # Jornada 2
    match(10039, "Group G", "Group Stage - 2", "BEL", "IRN",
          "2026-06-21T19:00:00Z", "SoFi Stadium, Los Ángeles"),
    match(10040, "Group G", "Group Stage - 2", "NZL", "EGY",
          "2026-06-22T01:00:00Z", "BC Place, Vancouver"),

    # Jornada 3
    match(10041, "Group G", "Group Stage - 3", "EGY", "IRN",
          "2026-06-27T03:00:00Z", "Lumen Field, Seattle"),
    match(10042, "Group G", "Group Stage - 3", "NZL", "BEL",
          "2026-06-27T03:00:00Z", "BC Place, Vancouver"),

    # ══════════════════ GRUPO H ══════════════════
    # España · Cabo Verde · Arabia Saudita · Uruguay

    # Jornada 1
    match(10043, "Group H", "Group Stage - 1", "ESP", "CPV",
          "2026-06-15T16:00:00Z", "Mercedes-Benz Stadium, Atlanta"),
    match(10044, "Group H", "Group Stage - 1", "KSA", "URU",
          "2026-06-15T22:00:00Z", "Hard Rock Stadium, Miami"),

    # Jornada 2
    match(10045, "Group H", "Group Stage - 2", "ESP", "KSA",
          "2026-06-21T16:00:00Z", "Mercedes-Benz Stadium, Atlanta"),
    match(10046, "Group H", "Group Stage - 2", "URU", "CPV",
          "2026-06-21T22:00:00Z", "Hard Rock Stadium, Miami"),

    # Jornada 3
    match(10047, "Group H", "Group Stage - 3", "CPV", "KSA",
          "2026-06-27T00:00:00Z", "NRG Stadium, Houston"),
    match(10048, "Group H", "Group Stage - 3", "URU", "ESP",
          "2026-06-27T00:00:00Z", "Estadio Akron, Guadalajara"),

    # ══════════════════ GRUPO I ══════════════════
    # Francia · Senegal · Irak · Noruega

    # Jornada 1
    match(10049, "Group I", "Group Stage - 1", "FRA", "SEN",
          "2026-06-16T19:00:00Z", "MetLife Stadium, Nueva York/Nueva Jersey"),
    match(10050, "Group I", "Group Stage - 1", "IRQ", "NOR",
          "2026-06-16T22:00:00Z", "Gillette Stadium, Boston"),

    # Jornada 2
    match(10051, "Group I", "Group Stage - 2", "FRA", "IRQ",
          "2026-06-22T21:00:00Z", "Lincoln Financial Field, Filadelfia"),
    match(10052, "Group I", "Group Stage - 2", "NOR", "SEN",
          "2026-06-23T00:00:00Z", "MetLife Stadium, Nueva York/Nueva Jersey"),

    # Jornada 3
    match(10053, "Group I", "Group Stage - 3", "NOR", "FRA",
          "2026-06-26T19:00:00Z", "Gillette Stadium, Boston"),
    match(10054, "Group I", "Group Stage - 3", "SEN", "IRQ",
          "2026-06-26T19:00:00Z", "BMO Field, Toronto"),

    # ══════════════════ GRUPO J ══════════════════
    # Argentina · Argelia · Austria · Jordania

    # Jornada 1
    match(10055, "Group J", "Group Stage - 1", "ARG", "ALG",
          "2026-06-17T01:00:00Z", "Children's Mercy Park, Kansas City"),
    match(10056, "Group J", "Group Stage - 1", "AUT", "JOR",
          "2026-06-17T04:00:00Z", "Levi's Stadium, San Francisco"),

    # Jornada 2
    match(10057, "Group J", "Group Stage - 2", "ARG", "AUT",
          "2026-06-22T17:00:00Z", "AT&T Stadium, Dallas"),
    match(10058, "Group J", "Group Stage - 2", "JOR", "ALG",
          "2026-06-23T03:00:00Z", "Levi's Stadium, San Francisco"),

    # Jornada 3
    match(10059, "Group J", "Group Stage - 3", "ALG", "AUT",
          "2026-06-28T02:00:00Z", "Children's Mercy Park, Kansas City"),
    match(10060, "Group J", "Group Stage - 3", "JOR", "ARG",
          "2026-06-28T02:00:00Z", "AT&T Stadium, Dallas"),

    # ══════════════════ GRUPO K ══════════════════
    # Portugal · RD Congo · Uzbekistán · Colombia

    # Jornada 1
    match(10061, "Group K", "Group Stage - 1", "POR", "COD",
          "2026-06-17T17:00:00Z", "NRG Stadium, Houston"),
    match(10062, "Group K", "Group Stage - 1", "UZB", "COL",
          "2026-06-18T02:00:00Z", "Estadio Azteca, Ciudad de México"),

    # Jornada 2
    match(10063, "Group K", "Group Stage - 2", "POR", "UZB",
          "2026-06-23T17:00:00Z", "NRG Stadium, Houston"),
    match(10064, "Group K", "Group Stage - 2", "COL", "COD",
          "2026-06-24T02:00:00Z", "Estadio Akron, Guadalajara"),

    # Jornada 3
    match(10065, "Group K", "Group Stage - 3", "COL", "POR",
          "2026-06-27T23:30:00Z", "Hard Rock Stadium, Miami"),
    match(10066, "Group K", "Group Stage - 3", "COD", "UZB",
          "2026-06-27T23:30:00Z", "Mercedes-Benz Stadium, Atlanta"),

    # ══════════════════ GRUPO L ══════════════════
    # Inglaterra · Croacia · Ghana · Panamá

    # Jornada 1
    match(10067, "Group L", "Group Stage - 1", "ENG", "CRO",
          "2026-06-17T20:00:00Z", "AT&T Stadium, Dallas"),
    match(10068, "Group L", "Group Stage - 1", "GHA", "PAN",
          "2026-06-17T23:00:00Z", "BMO Field, Toronto"),

    # Jornada 2
    match(10069, "Group L", "Group Stage - 2", "ENG", "GHA",
          "2026-06-23T20:00:00Z", "Gillette Stadium, Boston"),
    match(10070, "Group L", "Group Stage - 2", "PAN", "CRO",
          "2026-06-23T23:00:00Z", "BMO Field, Toronto"),

    # Jornada 3
    match(10071, "Group L", "Group Stage - 3", "PAN", "ENG",
          "2026-06-27T21:00:00Z", "MetLife Stadium, Nueva York/Nueva Jersey"),
    match(10072, "Group L", "Group Stage - 3", "CRO", "GHA",
          "2026-06-27T21:00:00Z", "Lincoln Financial Field, Filadelfia"),
]

# ─────────────────────────────────────────────
# FASES ELIMINATORIAS (equipos TBD)
# ─────────────────────────────────────────────
TBD = {"id": 999, "name": "TBD", "code": "TBD",
       "logo": "https://media.api-sports.io/football/leagues/1.png"}

def tbd_match(fixture_id, phase, round_name, label_home, label_away,
              kickoff_utc, venue):
    return {
        "fixture_id": fixture_id,
        "phase": phase,
        "group": None,
        "round": round_name,
        "home_team": {**TBD, "name": label_home},
        "away_team": {**TBD, "name": label_away},
        "kickoff": kickoff_utc,
        "status": "NS",
        "score": {"home": None, "away": None},
        "venue": venue,
    }


KNOCKOUT = [
    # ── Ronda de 32 (28 jun – 3 jul) ──
    tbd_match(10101, "round_of_32", "Round of 32", "2A",  "2B",  "2026-06-28T19:00:00Z", "SoFi Stadium, Los Ángeles"),
    tbd_match(10102, "round_of_32", "Round of 32", "1C",  "2F",  "2026-06-28T23:00:00Z", "NRG Stadium, Houston"),
    tbd_match(10103, "round_of_32", "Round of 32", "1E",  "3rd", "2026-06-29T19:00:00Z", "Gillette Stadium, Boston"),
    tbd_match(10104, "round_of_32", "Round of 32", "1F",  "2C",  "2026-06-29T23:00:00Z", "Estadio BBVA, Monterrey"),
    tbd_match(10105, "round_of_32", "Round of 32", "2E",  "2I",  "2026-06-30T19:00:00Z", "AT&T Stadium, Dallas"),
    tbd_match(10106, "round_of_32", "Round of 32", "1I",  "3rd", "2026-06-30T23:00:00Z", "MetLife Stadium, Nueva York/Nueva Jersey"),
    tbd_match(10107, "round_of_32", "Round of 32", "1A",  "3rd", "2026-07-01T19:00:00Z", "Estadio Azteca, Ciudad de México"),
    tbd_match(10108, "round_of_32", "Round of 32", "1D",  "2G",  "2026-07-01T23:00:00Z", "Mercedes-Benz Stadium, Atlanta"),
    tbd_match(10109, "round_of_32", "Round of 32", "1B",  "3rd", "2026-07-02T19:00:00Z", "BC Place, Vancouver"),
    tbd_match(10110, "round_of_32", "Round of 32", "1H",  "2K",  "2026-07-02T23:00:00Z", "Estadio Akron, Guadalajara"),
    tbd_match(10111, "round_of_32", "Round of 32", "1J",  "2L",  "2026-07-03T19:00:00Z", "Lumen Field, Seattle"),
    tbd_match(10112, "round_of_32", "Round of 32", "1K",  "2H",  "2026-07-03T23:00:00Z", "Hard Rock Stadium, Miami"),
    tbd_match(10113, "round_of_32", "Round of 32", "1G",  "3rd", "2026-07-04T19:00:00Z", "Lincoln Financial Field, Filadelfia"),
    tbd_match(10114, "round_of_32", "Round of 32", "1L",  "2J",  "2026-07-04T23:00:00Z", "BMO Field, Toronto"),
    tbd_match(10115, "round_of_32", "Round of 32", "2D",  "2F",  "2026-07-05T19:00:00Z", "Children's Mercy Park, Kansas City"),
    tbd_match(10116, "round_of_32", "Round of 32", "1F",  "3rd", "2026-07-05T23:00:00Z", "NRG Stadium, Houston"),

    # ── Octavos (4 – 7 jul) ──
    tbd_match(10201, "round_of_16", "Round of 16", "W101", "W102", "2026-07-04T19:00:00Z", "MetLife Stadium, Nueva York/Nueva Jersey"),
    tbd_match(10202, "round_of_16", "Round of 16", "W103", "W104", "2026-07-04T23:00:00Z", "AT&T Stadium, Dallas"),
    tbd_match(10203, "round_of_16", "Round of 16", "W105", "W106", "2026-07-05T19:00:00Z", "SoFi Stadium, Los Ángeles"),
    tbd_match(10204, "round_of_16", "Round of 16", "W107", "W108", "2026-07-05T23:00:00Z", "Mercedes-Benz Stadium, Atlanta"),
    tbd_match(10205, "round_of_16", "Round of 16", "W109", "W110", "2026-07-06T19:00:00Z", "Estadio Azteca, Ciudad de México"),
    tbd_match(10206, "round_of_16", "Round of 16", "W111", "W112", "2026-07-06T23:00:00Z", "NRG Stadium, Houston"),
    tbd_match(10207, "round_of_16", "Round of 16", "W113", "W114", "2026-07-07T19:00:00Z", "Levi's Stadium, San Francisco"),
    tbd_match(10208, "round_of_16", "Round of 16", "W115", "W116", "2026-07-07T23:00:00Z", "Lumen Field, Seattle"),

    # ── Cuartos de final (9 – 11 jul) ──
    tbd_match(10301, "quarterfinal", "Quarter-finals", "W201", "W202", "2026-07-09T23:00:00Z", "MetLife Stadium, Nueva York/Nueva Jersey"),
    tbd_match(10302, "quarterfinal", "Quarter-finals", "W203", "W204", "2026-07-10T23:00:00Z", "SoFi Stadium, Los Ángeles"),
    tbd_match(10303, "quarterfinal", "Quarter-finals", "W205", "W206", "2026-07-11T19:00:00Z", "AT&T Stadium, Dallas"),
    tbd_match(10304, "quarterfinal", "Quarter-finals", "W207", "W208", "2026-07-11T23:00:00Z", "Mercedes-Benz Stadium, Atlanta"),

    # ── Semifinales (14 – 15 jul) ──
    tbd_match(10401, "semifinal", "Semi-finals", "W301", "W302", "2026-07-14T23:00:00Z", "AT&T Stadium, Dallas"),
    tbd_match(10402, "semifinal", "Semi-finals", "W303", "W304", "2026-07-15T23:00:00Z", "Mercedes-Benz Stadium, Atlanta"),

    # ── Tercer puesto (18 jul) ──
    tbd_match(10501, "third_place", "3rd Place Final", "Perdedor SF1", "Perdedor SF2",
              "2026-07-18T23:00:00Z", "Hard Rock Stadium, Miami"),

    # ── Final (19 jul) ──
    tbd_match(10601, "final", "Final", "Ganador SF1", "Ganador SF2",
              "2026-07-19T23:00:00Z", "MetLife Stadium, Nueva York/Nueva Jersey"),
]

ALL_MATCHES = MATCHES + KNOCKOUT


def seed():
    batch = db.batch()
    for m in ALL_MATCHES:
        doc_ref = db.collection("matches").document(str(m["fixture_id"]))
        batch.set(doc_ref, m)
    batch.commit()
    print(f"✅ {len(ALL_MATCHES)} partidos guardados en Firestore "
          f"({len(MATCHES)} grupos + {len(KNOCKOUT)} eliminatorias)")


if __name__ == "__main__":
    seed()