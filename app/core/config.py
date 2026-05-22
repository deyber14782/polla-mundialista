from dotenv import load_dotenv
import os

load_dotenv()

class Settings:
    FIREBASE_CREDENTIALS: str = os.getenv("FIREBASE_CREDENTIALS", "serviceAccountKey.json")
    API_FOOTBALL_KEY: str = os.getenv("API_FOOTBALL_KEY", "")
    API_FOOTBALL_HOST: str = os.getenv("API_FOOTBALL_HOST", "v3.football.api-sports.io")
    APP_ENV: str = os.getenv("APP_ENV", "development")

settings = Settings()