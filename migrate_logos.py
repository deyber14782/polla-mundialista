"""
Migración: corrige el campo `logo` en todos los documentos de la
colección `matches` en Firestore, reemplazando las URLs de
media.api-sports.io (que apuntan a clubes por ID numérico) por URLs
de flagcdn.com (banderas reales por código ISO de país).

Ejecutar UNA sola vez después de haber corrido seed_matches_2026.py.
"""

import firebase_admin
from firebase_admin import credentials, firestore

cred = credentials.Certificate("serviceAccountKey.json")
firebase_admin.initialize_app(cred)
db = firestore.client()

# ── Mapa código FIFA → URL de bandera (flagcdn.com) ──────────────────────────
# flagcdn.com es gratuito, no requiere API key y usa códigos ISO 3166-1 alpha-2
# Tamaños disponibles: w20, w40, w80, w160, w320 (px de ancho)
FLAG_SIZE = "w80"

FLAGS = {
    # Grupo A
    "MEX": f"https://flagcdn.com/{FLAG_SIZE}/mx.png",   # México
    "RSA": f"https://flagcdn.com/{FLAG_SIZE}/za.png",   # Sudáfrica
    "KOR": f"https://flagcdn.com/{FLAG_SIZE}/kr.png",   # Corea del Sur
    "CZE": f"https://flagcdn.com/{FLAG_SIZE}/cz.png",   # Chequia
    # Grupo B
    "CAN": f"https://flagcdn.com/{FLAG_SIZE}/ca.png",   # Canadá
    "BIH": f"https://flagcdn.com/{FLAG_SIZE}/ba.png",   # Bosnia-Herzegovina
    "QAT": f"https://flagcdn.com/{FLAG_SIZE}/qa.png",   # Catar
    "SUI": f"https://flagcdn.com/{FLAG_SIZE}/ch.png",   # Suiza
    # Grupo C
    "BRA": f"https://flagcdn.com/{FLAG_SIZE}/br.png",   # Brasil
    "MAR": f"https://flagcdn.com/{FLAG_SIZE}/ma.png",   # Marruecos
    "HAI": f"https://flagcdn.com/{FLAG_SIZE}/ht.png",   # Haití
    "SCO": f"https://flagcdn.com/{FLAG_SIZE}/gb-sct.png", # Escocia
    # Grupo D
    "USA": f"https://flagcdn.com/{FLAG_SIZE}/us.png",   # Estados Unidos
    "PAR": f"https://flagcdn.com/{FLAG_SIZE}/py.png",   # Paraguay
    "AUS": f"https://flagcdn.com/{FLAG_SIZE}/au.png",   # Australia
    "TUR": f"https://flagcdn.com/{FLAG_SIZE}/tr.png",   # Turquía
    # Grupo E
    "GER": f"https://flagcdn.com/{FLAG_SIZE}/de.png",   # Alemania
    "CUW": f"https://flagcdn.com/{FLAG_SIZE}/cw.png",   # Curazao
    "CIV": f"https://flagcdn.com/{FLAG_SIZE}/ci.png",   # Costa de Marfil
    "ECU": f"https://flagcdn.com/{FLAG_SIZE}/ec.png",   # Ecuador
    # Grupo F
    "NED": f"https://flagcdn.com/{FLAG_SIZE}/nl.png",   # Países Bajos
    "JPN": f"https://flagcdn.com/{FLAG_SIZE}/jp.png",   # Japón
    "SWE": f"https://flagcdn.com/{FLAG_SIZE}/se.png",   # Suecia
    "TUN": f"https://flagcdn.com/{FLAG_SIZE}/tn.png",   # Túnez
    # Grupo G
    "BEL": f"https://flagcdn.com/{FLAG_SIZE}/be.png",   # Bélgica
    "EGY": f"https://flagcdn.com/{FLAG_SIZE}/eg.png",   # Egipto
    "IRN": f"https://flagcdn.com/{FLAG_SIZE}/ir.png",   # Irán
    "NZL": f"https://flagcdn.com/{FLAG_SIZE}/nz.png",   # Nueva Zelanda
    # Grupo H
    "ESP": f"https://flagcdn.com/{FLAG_SIZE}/es.png",   # España
    "CPV": f"https://flagcdn.com/{FLAG_SIZE}/cv.png",   # Cabo Verde
    "KSA": f"https://flagcdn.com/{FLAG_SIZE}/sa.png",   # Arabia Saudita
    "URU": f"https://flagcdn.com/{FLAG_SIZE}/uy.png",   # Uruguay
    # Grupo I
    "FRA": f"https://flagcdn.com/{FLAG_SIZE}/fr.png",   # Francia
    "SEN": f"https://flagcdn.com/{FLAG_SIZE}/sn.png",   # Senegal
    "IRQ": f"https://flagcdn.com/{FLAG_SIZE}/iq.png",   # Irak
    "NOR": f"https://flagcdn.com/{FLAG_SIZE}/no.png",   # Noruega
    # Grupo J
    "ARG": f"https://flagcdn.com/{FLAG_SIZE}/ar.png",   # Argentina
    "ALG": f"https://flagcdn.com/{FLAG_SIZE}/dz.png",   # Argelia
    "AUT": f"https://flagcdn.com/{FLAG_SIZE}/at.png",   # Austria
    "JOR": f"https://flagcdn.com/{FLAG_SIZE}/jo.png",   # Jordania
    # Grupo K
    "POR": f"https://flagcdn.com/{FLAG_SIZE}/pt.png",   # Portugal
    "COD": f"https://flagcdn.com/{FLAG_SIZE}/cd.png",   # RD Congo
    "UZB": f"https://flagcdn.com/{FLAG_SIZE}/uz.png",   # Uzbekistán
    "COL": f"https://flagcdn.com/{FLAG_SIZE}/co.png",   # Colombia
    # Grupo L
    "ENG": f"https://flagcdn.com/{FLAG_SIZE}/gb-eng.png", # Inglaterra
    "CRO": f"https://flagcdn.com/{FLAG_SIZE}/hr.png",   # Croacia
    "GHA": f"https://flagcdn.com/{FLAG_SIZE}/gh.png",   # Ghana
    "PAN": f"https://flagcdn.com/{FLAG_SIZE}/pa.png",   # Panamá
}

PLACEHOLDER_FLAG = "https://flagcdn.com/w80/un.png"  # ONU como fallback TBD


def get_flag(team: dict) -> str:
    code = team.get("code", "TBD")
    return FLAGS.get(code, PLACEHOLDER_FLAG)


def migrate():
    docs = db.collection("matches").stream()
    batch = db.batch()
    count = 0

    for doc in docs:
        data = doc.to_dict()
        updates = {}

        home = data.get("home_team", {})
        away = data.get("away_team", {})

        new_home_logo = get_flag(home)
        new_away_logo = get_flag(away)

        # Solo actualizar si el logo cambió (evita writes innecesarios)
        if home.get("logo") != new_home_logo:
            updates["home_team.logo"] = new_home_logo

        if away.get("logo") != new_away_logo:
            updates["away_team.logo"] = new_away_logo

        if updates:
            batch.update(doc.reference, updates)
            count += 1

        # Firestore limita a 500 operaciones por batch
        if count > 0 and count % 490 == 0:
            batch.commit()
            batch = db.batch()
            print(f"  → Batch intermedio commiteado ({count} docs)")

    if count % 490 != 0:
        batch.commit()

    print(f"✅ Migración completa: {count} documentos actualizados")


if __name__ == "__main__":
    migrate()