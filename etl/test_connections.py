"""
Quick connection test for the TTC delay project.
Run this once after setting up .env to confirm both databases are reachable
before writing any real extraction/load scripts.

Usage:
    python etl/test_connections.py
"""

import os
from dotenv import load_dotenv

load_dotenv()


def test_mysql():
    import mysql.connector

    try:
        conn = mysql.connector.connect(
            host=os.getenv("MYSQL_HOST"),
            port=int(os.getenv("MYSQL_PORT", 3306)),
            user=os.getenv("MYSQL_USER"),
            password=os.getenv("MYSQL_PASSWORD"),
            database=os.getenv("MYSQL_DATABASE"),
        )
        cursor = conn.cursor()
        cursor.execute("SHOW TABLES;")
        tables = [row[0] for row in cursor.fetchall()]
        cursor.close()
        conn.close()
        print("MySQL: connected successfully.")
        print(f"  Database: {os.getenv('MYSQL_DATABASE')}")
        print(f"  Tables found: {tables}")
    except Exception as e:
        print("MySQL: connection FAILED.")
        print(f"  Error: {e}")


def test_mongo():
    import certifi
    from pymongo import MongoClient
    from pymongo.server_api import ServerApi

    try:
        uri = os.getenv("MONGO_URI")
        client = MongoClient(uri, server_api=ServerApi("1"), tlsCAFile=certifi.where())
        client.admin.command("ping")
        print("MongoDB: connected successfully.")
        print(f"  Databases visible: {client.list_database_names()}")
    except Exception as e:
        print("MongoDB: connection FAILED.")
        print(f"  Error: {e}")


if __name__ == "__main__":
    print("Testing connections...\n")
    test_mysql()
    print()
    test_mongo()