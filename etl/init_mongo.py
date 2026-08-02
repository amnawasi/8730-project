"""
One-time MongoDB collection setup for the TTC delay project.
Creates two collections with schema validation, mirroring what schema.sql
does for MySQL. Run this once, right after test_connections.py confirms
MongoDB is reachable.

Usage:
    python etl/init_mongo.py
"""

import os
import certifi
from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.server_api import ServerApi
from pymongo.errors import CollectionInvalid

load_dotenv()


RAW_DELAY_INCIDENTS_VALIDATOR = {
    "$jsonSchema": {
        "bsonType": "object",
        "required": ["delay_date", "network", "route_or_line", "raw_text", "source"],
        "properties": {
            "delay_date": {
                "bsonType": "string",
                "description": "ISO date string, e.g. '2026-07-15' — matches MySQL delay_date",
            },
            "network": {
                "bsonType": "string",
                "enum": ["subway", "streetcar", "bus"],
            },
            "route_or_line": {"bsonType": "string"},
            "raw_text": {
                "bsonType": "string",
                "description": "Full raw incident description from the source file",
            },
            "source": {"bsonType": "string"},
            "ingested_at": {"bsonType": "date"},
        },
    }
}

REDDIT_POSTS_VALIDATOR = {
    "$jsonSchema": {
        "bsonType": "object",
        "required": ["post_id", "subreddit", "post_date", "title"],
        "properties": {
            "post_id": {"bsonType": "string", "description": "Reddit's own post ID"},
            "subreddit": {"bsonType": "string"},
            "post_date": {"bsonType": "string"},
            "title": {"bsonType": "string"},
            "body": {"bsonType": "string"},
            "score": {"bsonType": "int"},
            "num_comments": {"bsonType": "int"},
            "mentioned_route": {
                "bsonType": ["string", "null"],
                "description": "Route mentioned in the post, if any could be detected",
            },
            "url": {"bsonType": "string"},
            "ingested_at": {"bsonType": "date"},
        },
    }
}


def create_collection_if_missing(db, name, validator):
    try:
        db.create_collection(name, validator=validator)
        print(f"  Created collection: {name}")
    except CollectionInvalid:
        # Already exists — update its validator instead of failing
        db.command("collMod", name, validator=validator)
        print(f"  Collection already existed, validator updated: {name}")


def main():
    uri = os.getenv("MONGO_URI")
    client = MongoClient(uri, server_api=ServerApi("1"), tlsCAFile=certifi.where())
    db = client["ttc_delays"]

    print("Setting up MongoDB collections in 'ttc_delays'...\n")
    create_collection_if_missing(db, "raw_delay_incidents", RAW_DELAY_INCIDENTS_VALIDATOR)
    create_collection_if_missing(db, "reddit_posts", REDDIT_POSTS_VALIDATOR)

    print("\nDone. Collections in ttc_delays:", db.list_collection_names())


if __name__ == "__main__":
    main()