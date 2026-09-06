from __future__ import annotations

from typing import Any
from graph.neo4j_client import (
    Neo4jClient,
    NEO4J_DATABASE,
)

# ---------------------------------------------------------------------------
# Allowed graph entity types
# ---------------------------------------------------------------------------

ENTITY_LABELS = {
    "PERSON": "Person",
    "PHONE": "Phone",
    "VEHICLE": "Vehicle",
    "LOCATION": "Location",
    "ORGANIZATION": "Organization",
    "ACCOUNT": "Account",
}


# ---------------------------------------------------------------------------
# Allowed LLM relationship types
# ---------------------------------------------------------------------------

RELATION_TYPES = {
    "CALLED",
    "FINANCIAL_LINK",
    "ASSOCIATE",
    "OWNS",
    "VISITED",
    "MEMBER_OF",
    "CO_ACCUSED",
    "SUSPECT_IN",
}


class GraphBuilder:
    """
    Convert validated LLM reasoning output into a Neo4j graph.

    PostgreSQL remains the source of truth.
    This class only represents the LLM reasoning in Neo4j.
    """

    def __init__(self, neo4j_client: Neo4jClient):
        self.client = neo4j_client

    @staticmethod
    def _entity_key(
        entity_type: str,
        value: str,
    ) -> str:
        """
        Create a stable identifier for a graph entity.
        """

        normalized_type = entity_type.strip().upper()
        normalized_value = " ".join(
            value.strip().split()
        ).casefold()

        return f"{normalized_type}:{normalized_value}"

    @staticmethod
    def _validate_relation(
        relation: dict[str, Any],
    ) -> None:
        """
        Ensure the relation came through the same validation contract
        used by the LLM reasoning service.
        """

        if relation.get("from_type") not in ENTITY_LABELS:
            raise ValueError(
                f"Unsupported from_type: "
                f"{relation.get('from_type')}"
            )

        if relation.get("to_type") not in ENTITY_LABELS:
            raise ValueError(
                f"Unsupported to_type: "
                f"{relation.get('to_type')}"
            )

        if relation.get("relation") not in RELATION_TYPES:
            raise ValueError(
                f"Unsupported relation type: "
                f"{relation.get('relation')}"
            )

        if not relation.get("from"):
            raise ValueError(
                "LLM relation is missing 'from'."
            )

        if not relation.get("to"):
            raise ValueError(
                "LLM relation is missing 'to'."
            )

    def _merge_entity(
        self,
        tx,
        entity_type: str,
        value: str,
    ) -> None:
        """
        Create the entity node if it does not already exist.

        MERGE prevents duplicate nodes when the same entity appears
        in multiple FIRs or multiple LLM reasoning results.
        """

        label = ENTITY_LABELS[entity_type]
        entity_key = self._entity_key(entity_type, value)

        query = f"""
        MERGE (e:{label} {{entity_key: $entity_key}})
        SET e.name = $value,
            e.entity_type = $entity_type
        """

        tx.run(
            query,
            entity_key=entity_key,
            value=value.strip(),
            entity_type=entity_type,
        )
    def _merge_relation(
        self,
        tx,
        relation: dict[str, Any],
        fir_id: int,
        reasoning_id: int,
        model_used: str | None = None,
    ) -> None:
        """
        Create an LLM-derived relationship between two graph entities.

        Each reasoning result gets its own relationship provenance so that
        evidence from different FIRs/reasoning runs is not overwritten.
        """

        self._validate_relation(relation)

        from_type = relation["from_type"]
        to_type = relation["to_type"]

        from_value = relation["from"].strip()
        to_value = relation["to"].strip()

        relation_type = relation["relation"]

        from_label = ENTITY_LABELS[from_type]
        to_label = ENTITY_LABELS[to_type]

        from_key = self._entity_key(
            from_type,
            from_value,
        )

        to_key = self._entity_key(
            to_type,
            to_value,
        )

        query = f"""
        MATCH (source:{from_label} {{entity_key: $from_key}})
        MATCH (target:{to_label} {{entity_key: $to_key}})

        MERGE (source)-[r:{relation_type} {{
            reasoning_id: $reasoning_id
        }}]->(target)

        SET r.fir_id = $fir_id,
            r.confidence = $confidence,
            r.evidence_level = $evidence_level,
            r.reasoning = $reasoning,
            r.model_used = $model_used
        """

        tx.run(
            query,
            from_key=from_key,
            to_key=to_key,
            reasoning_id=reasoning_id,
            fir_id=fir_id,
            confidence=relation.get("confidence"),
            evidence_level=relation.get("evidence_level"),
            reasoning=relation.get("reasoning"),
            model_used=model_used,
        )

    def build_from_llm_result(
        self,
        llm_result: dict[str, Any],
        fir_id: int,
        reasoning_id: int,
        model_used: str | None = None,
    ) -> int:
        """
        Convert one validated LLM reasoning result into Neo4j.

        Returns the number of relationships written to the graph.
        """

        if not isinstance(llm_result, dict):
            raise ValueError("LLM result must be a dictionary.")

        relations = llm_result.get("relations", [])

        if not isinstance(relations, list):
            raise ValueError(
                "LLM result 'relations' must be a list."
            )

        if not relations:
            return 0

        def write_graph(tx):
            written = 0

            for relation in relations:
                if not isinstance(relation, dict):
                    continue

                self._validate_relation(relation)

                # Create source and target nodes first.
                self._merge_entity(
                    tx,
                    relation["from_type"],
                    relation["from"],
                )

                self._merge_entity(
                    tx,
                    relation["to_type"],
                    relation["to"],
                )

                # Then create the relationship.
                self._merge_relation(
                    tx,
                    relation,
                    fir_id=fir_id,
                    reasoning_id=reasoning_id,
                    model_used=model_used,
                )

                written += 1

            return written

        with self.client.driver.session(
            database=NEO4J_DATABASE
        ) as session:
            result = session.execute_write(write_graph)

        return result