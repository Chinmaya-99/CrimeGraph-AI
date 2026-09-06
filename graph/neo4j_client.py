import os
from dotenv import load_dotenv
from neo4j import GraphDatabase

load_dotenv()


NEO4J_URI = os.getenv("NEO4J_URI")
NEO4J_USERNAME = os.getenv("NEO4J_USERNAME")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")
NEO4J_DATABASE = os.getenv("NEO4J_DATABASE", "neo4j")


class Neo4jClient:
    def __init__(self):
        if not NEO4J_URI:
            raise RuntimeError("NEO4J_URI is not configured")

        if not NEO4J_USERNAME:
            raise RuntimeError("NEO4J_USERNAME is not configured")

        if not NEO4J_PASSWORD:
            raise RuntimeError("NEO4J_PASSWORD is not configured")

        self.driver = GraphDatabase.driver(
            NEO4J_URI,
            auth=(NEO4J_USERNAME, NEO4J_PASSWORD)
        )

    def verify_connection(self):
        self.driver.verify_connectivity()
        return True

    def close(self):
        self.driver.close()