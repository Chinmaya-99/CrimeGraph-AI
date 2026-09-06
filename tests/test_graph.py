from graph.neo4j_client import Neo4jClient
from graph.graph_builder import GraphBuilder


test_llm_result = {
    "relations": [
        {
            "from": "Arjun Mehta",
            "from_type": "PERSON",
            "to": "Ravi Das",
            "to_type": "PERSON",
            "relation": "ASSOCIATE",
            "confidence": 0.87,
            "evidence_level": "INFERRED",
            "reasoning": "Both individuals were connected through evidence associated with the investigation."
        }
    ]
}


client = Neo4jClient()

try:
    client.verify_connection()

    builder = GraphBuilder(client)

    count = builder.build_from_llm_result(
        llm_result=test_llm_result,
        fir_id=999999,
        reasoning_id=999999,
        model_used="TEST",
    )

    print(f"Relationships written: {count}")

finally:
    client.close()