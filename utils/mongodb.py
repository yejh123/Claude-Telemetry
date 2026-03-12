"""MongoDB data transmission via proxy server or direct pymongo."""

import json
import logging
from typing import Optional
from urllib.error import URLError
from urllib.request import Request, urlopen

from utils.config import get_config
from utils.time import utc_now_iso

_mongodb_status: dict = {"available": None}


def _is_mongodb_available() -> Optional[bool]:
    """Return cached MongoDB availability, or None if not yet tested."""
    return _mongodb_status["available"]


def _set_mongodb_available(available: bool) -> None:
    """Cache MongoDB availability for the rest of this session."""
    _mongodb_status["available"] = available


def send_to_mongodb_server(
    collection: str, data: dict, logger: logging.Logger
) -> tuple[bool, dict]:
    """Send data to MongoDB — via proxy server or directly via pymongo.

    Routes automatically based on the mongodb_enable_proxy config value.

    Args:
        collection: MongoDB collection name (e.g. "conversations", "events", "metadata").
        data: Dictionary containing the payload.
        logger: Logger instance.

    Returns:
        (success, response_data) tuple.
    """
    config = get_config()

    # Bail out early if MongoDB is disabled
    if not config.mongodb_enabled:
        logger.info("MongoDB disabled via config, skipping send")
        return False, {}

    # Check cached availability — skip if previously failed
    cached = _is_mongodb_available()
    if cached is False:
        logger.info("MongoDB unavailable (cached), skipping send")
        return False, {}

    if config.mongodb_enable_proxy:
        return _send_via_proxy(collection=collection, data=data, logger=logger, config=config)
    return _send_via_pymongo(collection=collection, data=data, logger=logger, config=config)


def _check_proxy_health(proxy_url: str, logger: logging.Logger) -> bool:
    """Check if the MongoDB proxy server is alive via its health endpoint.

    Args:
        proxy_url: Base URL of the proxy server.
        logger: Logger instance.

    Returns:
        True if the proxy is healthy, False otherwise.
    """
    health_url = f"{proxy_url.rstrip('/')}/health"
    try:
        req = Request(health_url, method="GET")
        with urlopen(req, timeout=5) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            if body.get("status") == "ok":
                logger.info("Proxy health check OK: %s", body)
                return True
            logger.warning("Proxy health check unexpected response: %s", body)
            return False
    except Exception as e:
        logger.warning("Proxy health check failed: %s", e)
        return False


def _send_via_proxy(
    collection: str, data: dict, logger: logging.Logger, config=None
) -> tuple[bool, dict]:
    """Send data via the MongoDB proxy server.

    Args:
        collection: MongoDB collection name.
        data: Dictionary to POST as JSON.
        logger: Logger instance.
        config: Config instance (optional, created if not provided).

    Returns:
        (success, response_data) tuple.
    """
    if config is None:
        config = get_config()

    proxy_url = config.mongodb_proxy_url
    if not proxy_url:
        logger.warning("mongodb_proxy_url not set, skipping proxy send")
        return False, {}

    if not _check_proxy_health(proxy_url=proxy_url, logger=logger):
        logger.warning("Proxy server at %s is not healthy, skipping send", proxy_url)
        _set_mongodb_available(False)
        return False, {}

    database_name = config.mongodb_database
    if not database_name:
        logger.error("mongodb_database not configured")
        return False, {}

    url = f"{proxy_url.rstrip('/')}/api/{collection}"
    logger.info("Sending to proxy: %s", url)

    try:
        proxy_data = {**data, "database": database_name}
        payload = json.dumps(proxy_data, default=str).encode("utf-8")
        req = Request(url, data=payload, method="POST")
        req.add_header("Content-Type", "application/json")

        with urlopen(req, timeout=30) as resp:
            response_body = resp.read().decode("utf-8")
            response_data = json.loads(response_body)
            logger.info("Proxy response (%s): %s", resp.status, response_data)
            _set_mongodb_available(True)
            return True, response_data
    except URLError as e:
        logger.warning("Proxy HTTP error: %s", e)
        _set_mongodb_available(False)
        return False, {}
    except Exception as e:
        logger.warning("Proxy send error: %s", e)
        return False, {}


def _send_via_pymongo(
    collection: str, data: dict, logger: logging.Logger, config=None
) -> tuple[bool, dict]:
    """Send data directly to MongoDB using pymongo.

    Args:
        collection: MongoDB collection name.
        data: Dictionary containing the payload.
        logger: Logger instance.
        config: Config instance (optional, created if not provided).

    Returns:
        (success, response_data) tuple.
    """
    if config is None:
        config = get_config()

    mongodb_url = config.mongodb_url
    if not mongodb_url:
        logger.warning("mongodb_url not configured, skipping MongoDB send")
        return False, {}

    database_name = config.mongodb_database
    if not database_name:
        logger.error("mongodb_database not configured")
        return False, {}

    try:
        from pymongo import MongoClient

        client = MongoClient(mongodb_url, serverSelectionTimeoutMS=5000)
        db = client[database_name]
        mongo_collection = db[collection]

        current_time = utc_now_iso()
        conversation_id: str = data.get("conversation_id", "")

        if collection == "conversations":
            new_events: list[dict] = data.get("new_events", [])
            existing = mongo_collection.find_one({"conversation_id": conversation_id})

            if existing:
                existing_events: dict = existing.get("events", {})
                for event in new_events:
                    existing_events[str(event["id"])] = event
                mongo_collection.update_one(
                    {"conversation_id": conversation_id},
                    {"$set": {"events": existing_events, "updated_at": current_time}},
                )
                result = {
                    "status": "updated",
                    "total_events_count": len(existing_events),
                }
            else:
                events_dict = {str(e["id"]): e for e in new_events}
                mongo_collection.insert_one(
                    {
                        "conversation_id": conversation_id,
                        "created_at": current_time,
                        "events": events_dict,
                        "updated_at": current_time,
                    }
                )
                result = {"status": "created", "total_events_count": len(events_dict)}

        elif collection == "events":
            event_data: dict = data.get("event_data", {})
            event_key: str = str(event_data.get("id", "0"))
            existing = mongo_collection.find_one({"conversation_id": conversation_id})

            if existing:
                mongo_collection.update_one(
                    {"conversation_id": conversation_id},
                    {
                        "$set": {
                            f"events.{event_key}": event_data,
                            "updated_at": current_time,
                        }
                    },
                )
                result = {"status": "updated", "event_key": event_key}
            else:
                mongo_collection.insert_one(
                    {
                        "conversation_id": conversation_id,
                        "created_at": current_time,
                        "events": {event_key: event_data},
                        "updated_at": current_time,
                    }
                )
                result = {"status": "created", "event_key": event_key}

        elif collection == "metadata":
            doc = data.get("document", {})
            doc["updated_at"] = current_time
            existing = mongo_collection.find_one(
                {"conversation_id": doc.get("conversation_id", "")}
            )
            if existing:
                mongo_collection.update_one(
                    {"conversation_id": doc["conversation_id"]},
                    {"$set": doc},
                )
                result = {"status": "updated"}
            else:
                doc["created_at"] = current_time
                mongo_collection.insert_one(doc)
                result = {"status": "created"}

        elif collection == "monitors":
            monitor_data: dict = data.get("monitor_data", {})
            monitor_key: str = str(monitor_data.get("id", "0"))
            existing = mongo_collection.find_one({"conversation_id": conversation_id})

            if existing:
                mongo_collection.update_one(
                    {"conversation_id": conversation_id},
                    {
                        "$set": {
                            f"monitors.{monitor_key}": monitor_data,
                            "updated_at": current_time,
                        }
                    },
                )
                result = {"status": "updated", "monitor_key": monitor_key}
            else:
                mongo_collection.insert_one(
                    {
                        "conversation_id": conversation_id,
                        "created_at": current_time,
                        "monitors": {monitor_key: monitor_data},
                        "updated_at": current_time,
                    }
                )
                result = {"status": "created", "monitor_key": monitor_key}

        else:
            logger.error("Unknown collection: %s", collection)
            return False, {}

        client.close()
        logger.info("MongoDB send OK: %s", result)
        _set_mongodb_available(True)
        return True, result

    except ImportError:
        logger.error("pymongo not installed. Install with: pip install pymongo")
        return False, {}
    except Exception as e:
        logger.error("MongoDB send error: %s", e)
        _set_mongodb_available(False)
        return False, {}
