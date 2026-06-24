from pymongo import MongoClient
from pymongo.database import Database
from core.config import settings

_client: MongoClient = None
_db: Database = None


def get_sync_db() -> Database:
    global _client, _db
    if _db is None:
        _client = MongoClient(settings.mongo_uri)
        _db = _client[settings.mongo_db]
    return _db
