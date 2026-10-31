"""MongoDB connection management."""

from typing import Optional
from pymongo import MongoClient
from pymongo.database import Database
from pymongo.errors import ConnectionFailure, PyMongoError, ServerSelectionTimeoutError
from app.core.config import settings
from app.core.logging import logger

_mongo_client: Optional[MongoClient] = None


def get_mongo_client() -> Optional[MongoClient]:
    """Retrieve or create the global PyMongo client instance."""
    global _mongo_client
    if _mongo_client is not None:
        return _mongo_client

    if not settings.MONGODB_URI:
        logger.info("MONGODB_URI is not set; running with in-memory storage fallback.")
        return None

    try:
        # 3-second timeout for server selection so startup does not block indefinitely
        _mongo_client = MongoClient(
            settings.MONGODB_URI,
            serverSelectionTimeoutMS=3000,
            connectTimeoutMS=3000,
            socketTimeoutMS=5000,
            appname="IncidentTimelineInvestigator",
            retryWrites=True,
        )
        # Verify connection
        _mongo_client.admin.command("ping")
        logger.info("Successfully connected to MongoDB Atlas.")
        return _mongo_client
    except PyMongoError as exc:
        logger.warning(
            f"Failed to connect to MongoDB ({exc}). Falling back to in-memory storage."
        )
        _mongo_client = None
        return None


def set_mongo_client(client: Optional[MongoClient]) -> None:
    """Explicitly set or override the PyMongo client instance (useful for testing)."""
    global _mongo_client
    _mongo_client = client


def get_database() -> Optional[Database]:
    """Retrieve the application database instance."""
    client = get_mongo_client()
    if client is None:
        return None
    return client[settings.MONGODB_DB_NAME]


def check_db_connection() -> bool:
    """Check if MongoDB is actively connected and responding to ping."""
    client = get_mongo_client()
    if client is None:
        return False
    try:
        client.admin.command("ping")
        return True
    except Exception:
        return False


def close_mongo_client() -> None:
    """Close the active PyMongo connection."""
    global _mongo_client
    if _mongo_client is not None:
        try:
            _mongo_client.close()
            logger.info("Closed MongoDB client connection.")
        except Exception as exc:
            logger.warning(f"Error closing MongoDB client: {exc}")
        finally:
            _mongo_client = None
