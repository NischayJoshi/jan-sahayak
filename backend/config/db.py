from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
import os
from urllib.parse import quote_plus

load_dotenv()

username = quote_plus(os.getenv("MONGODB_USERNAME"))
password = quote_plus(os.getenv("MONGODB_PASSWORD"))

MONGO_URI = f"mongodb+srv://{username}:{password}@anger.vej98ud.mongodb.net/?retryWrites=true&w=majority&appName=anger"
DB_Name = os.getenv("MONGODB_DB")
client = AsyncIOMotorClient(MONGO_URI)
db = client[DB_Name]