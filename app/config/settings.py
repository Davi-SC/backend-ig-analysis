from pydantic_settings import BaseSettings
from dotenv import load_dotenv
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))

class Settings(BaseSettings):
    MONGO_URI: str

    DB_NAME: str
     
settings = Settings()