#!/usr/bin/env python3
"""
MongoDB Availability Test Module
Tests MongoDB connection and basic operations across all platforms.
"""

import sys
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(project_root))

from utils import get_config  # noqa: E402

# Load configuration (absorbs .env files automatically)
cfg = get_config()


class TestResult:
    """Container for test results."""

    def __init__(self, name, passed, message="", details=""):
        self.name = name
        self.passed = passed
        self.message = message
        self.details = details


def test_pymongo_installed():
    """Test if pymongo package is installed."""
    try:
        import pymongo  # noqa: F401

        return TestResult(
            "pymongo_installed",
            True,
            "pymongo package is installed",
        )
    except ImportError:
        return TestResult(
            "pymongo_installed",
            False,
            "pymongo package is NOT installed",
            "Install with: pip install pymongo",
        )


def test_mongodb_env_configured():
    """Test if MongoDB connection is configured."""
    mongodb_url = cfg.mongodb_url

    if not mongodb_url:
        return TestResult(
            "mongodb_env_configured",
            False,
            "mongodb_url is not configured",
            "Set mongodb_url in config.json or MONGODB_URL env var",
        )

    # Mask the password in the URL for logging
    masked_url = mongodb_url
    if "@" in mongodb_url:
        # Format: mongodb://user:password@host:port/db
        parts = mongodb_url.split("@")
        prefix = parts[0]
        if ":" in prefix:
            # Mask password
            idx = prefix.rfind(":")
            masked_url = prefix[:idx] + ":****@" + parts[1]

    return TestResult(
        "mongodb_env_configured",
        True,
        "MONGODB_URL is configured",
        f"URL: {masked_url}",
    )


def test_mongodb_connection():
    """Test MongoDB connection."""
    mongodb_url = cfg.mongodb_url

    if not mongodb_url:
        return TestResult(
            "mongodb_connection",
            False,
            "Cannot test connection - MONGODB_URL not configured",
        )

    try:
        from pymongo import MongoClient
        from pymongo.errors import (
            ConfigurationError,
            ConnectionFailure,
            OperationFailure,
            ServerSelectionTimeoutError,
        )
    except ImportError:
        return TestResult(
            "mongodb_connection",
            False,
            "Cannot test connection - pymongo not installed",
        )

    try:
        # Create client with short timeout for testing
        client = MongoClient(mongodb_url, serverSelectionTimeoutMS=5000)

        # Force connection by issuing a command
        client.admin.command("ping")

        # Get server info
        server_info = client.server_info()
        version = server_info.get("version", "unknown")

        client.close()

        return TestResult(
            "mongodb_connection",
            True,
            "Successfully connected to MongoDB",
            f"MongoDB version: {version}",
        )

    except ServerSelectionTimeoutError as e:
        return TestResult(
            "mongodb_connection",
            False,
            "Connection timeout - MongoDB server not reachable",
            str(e),
        )
    except ConnectionFailure as e:
        return TestResult(
            "mongodb_connection",
            False,
            "Connection failed - check network and credentials",
            str(e),
        )
    except ConfigurationError as e:
        return TestResult(
            "mongodb_connection",
            False,
            "Configuration error - check MONGODB_URL format",
            str(e),
        )
    except OperationFailure as e:
        return TestResult(
            "mongodb_connection",
            False,
            "Authentication failed - check username/password",
            str(e),
        )
    except Exception as e:
        return TestResult(
            "mongodb_connection",
            False,
            f"Unexpected error: {type(e).__name__}",
            str(e),
        )


def test_mongodb_database_access():
    """Test MongoDB database access and collection operations."""
    mongodb_url = cfg.mongodb_url
    mongodb_database = cfg.mongodb_database or "claude_code_db_dev"
    mongodb_collection = "conversations"

    if not mongodb_url:
        return TestResult(
            "mongodb_database_access",
            False,
            "Cannot test database access - MONGODB_URL not configured",
        )

    try:
        from pymongo import MongoClient
        from pymongo.errors import OperationFailure
    except ImportError:
        return TestResult(
            "mongodb_database_access",
            False,
            "Cannot test database access - pymongo not installed",
        )

    try:
        client = MongoClient(mongodb_url, serverSelectionTimeoutMS=5000)
        db = client[mongodb_database]
        # List collections to verify database access
        collections = db.list_collection_names()
        # Check if target collection exists or can be created
        collection = db[mongodb_collection]
        # Try a simple count operation
        count = collection.count_documents({})

        client.close()
        return TestResult(
            "mongodb_database_access",
            True,
            f"Database '{mongodb_database}' accessible. All collections: {collections}",
            f"Collection '{mongodb_collection}' has {count} documents",
        )

    except OperationFailure as e:
        return TestResult(
            "mongodb_database_access",
            False,
            "Database access denied - check user permissions",
            str(e),
        )
    except Exception as e:
        return TestResult(
            "mongodb_database_access",
            False,
            f"Database access error: {type(e).__name__}",
            str(e),
        )


def test_mongodb_write_permission():
    """Test MongoDB write permission with a test document."""
    mongodb_url = cfg.mongodb_url
    mongodb_database = cfg.mongodb_database or "claude_code_db_dev"

    if not mongodb_url:
        return TestResult(
            "mongodb_write_permission",
            False,
            "Cannot test write permission - MONGODB_URL not configured",
        )

    try:
        from pymongo import MongoClient
        from pymongo.errors import OperationFailure
    except ImportError:
        return TestResult(
            "mongodb_write_permission",
            False,
            "Cannot test write permission - pymongo not installed",
        )

    try:
        from datetime import datetime, timezone

        client = MongoClient(mongodb_url, serverSelectionTimeoutMS=5000)
        db = client[mongodb_database]

        # Use a test collection
        test_collection = db["_connection_test"]

        # Create test document
        test_doc = {
            "_id": "connection_test",
            "test": True,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        # Try to upsert the test document
        test_collection.replace_one({"_id": "connection_test"}, test_doc, upsert=True)

        # Verify it was written
        result = test_collection.find_one({"_id": "connection_test"})

        # Clean up
        test_collection.delete_one({"_id": "connection_test"})

        client.close()

        if result:
            return TestResult(
                "mongodb_write_permission",
                True,
                "Write permission verified",
                "Successfully wrote and deleted test document",
            )
        else:
            return TestResult(
                "mongodb_write_permission",
                False,
                "Write verification failed",
                "Document was not found after insert",
            )

    except OperationFailure as e:
        return TestResult(
            "mongodb_write_permission",
            False,
            "Write permission denied",
            str(e),
        )
    except Exception as e:
        return TestResult(
            "mongodb_write_permission",
            False,
            f"Write test error: {type(e).__name__}",
            str(e),
        )


def run_all_tests():
    """Run all MongoDB tests and return results."""
    tests = [
        test_pymongo_installed,
        test_mongodb_env_configured,
        test_mongodb_connection,
        test_mongodb_database_access,
        test_mongodb_write_permission,
    ]

    results = []
    for test_func in tests:
        try:
            result = test_func()
            results.append(result)
        except Exception as e:
            results.append(
                TestResult(
                    test_func.__name__,
                    False,
                    f"Test crashed: {type(e).__name__}",
                    str(e),
                )
            )

    return results


def print_results(results):
    """Print test results in a formatted way."""
    print("\n" + "=" * 60)
    print("MongoDB Availability Test Results")
    print("=" * 60)

    passed = 0
    failed = 0

    for result in results:
        status = "PASS" if result.passed else "FAIL"
        icon = "[+]" if result.passed else "[-]"

        print(f"\n{icon} {result.name}: {status}")
        print(f"    {result.message}")
        if result.details:
            print(f"    Details: {result.details}")

        if result.passed:
            passed += 1
        else:
            failed += 1

    print("\n" + "-" * 60)
    print(f"Summary: {passed} passed, {failed} failed, {len(results)} total")
    print("=" * 60)

    return failed == 0


def main():
    """Main entry point."""
    results = run_all_tests()
    success = print_results(results)
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
