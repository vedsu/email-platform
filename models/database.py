from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from core.config import settings

from models.contact import CONTACT_INDEXES
from models.campaign import CAMPAIGN_INDEXES
from models.list import LIST_INDEXES
from models.event import EVENT_INDEXES
from models.suppression import SUPPRESSION_INDEXES
from models.user import USER_INDEXES
from models.template import TEMPLATE_INDEXES

client: AsyncIOMotorClient = None
db: AsyncIOMotorDatabase = None

COLLECTION_INDEXES = {
    "contacts": CONTACT_INDEXES,
    "campaigns": CAMPAIGN_INDEXES,
    "lists": LIST_INDEXES,
    "events": EVENT_INDEXES,
    "suppressions": SUPPRESSION_INDEXES,
    "users": USER_INDEXES,
    "templates": TEMPLATE_INDEXES,
}


async def connect_db():
    global client, db
    client = AsyncIOMotorClient(settings.mongo_uri)
    db = client[settings.mongo_db]
    await create_indexes()


async def close_db():
    global client
    if client:
        client.close()


async def create_indexes():
    for collection_name, indexes in COLLECTION_INDEXES.items():
        collection = db[collection_name]
        for index in indexes:
            await collection.create_index(
                index["keys"],
                unique=index.get("unique", False),
            )


def get_db() -> AsyncIOMotorDatabase:
    return db
