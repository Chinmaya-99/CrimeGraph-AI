from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from data_base.database import get_db
from models.llm_results import LLMReasoningResult

from graph.neo4j_client import (
    Neo4jClient,
    NEO4J_DATABASE,
)
from models.fir import FIRRecord
from graph.graph_builder import GraphBuilder


router = APIRouter(
    prefix="/graphs",
    tags=["Graph"],
)


# ================================================================
# GET HISTORICAL INTELLIGENCE
# ================================================================
@router.get("/history")
async def get_historical_intelligence(
    fir_id: int,
    db: Session = Depends(get_db),
):
    """
    Retrieve previously stored LLM intelligence for a specific FIR.

    This endpoint does NOT call the LLM and does NOT create new
    reasoning. It reads previously persisted reasoning results
    from PostgreSQL using the FIR ID.
    """

    rows = (
        db.query(
            LLMReasoningResult,
            FIRRecord,
        )
        .join(
            FIRRecord,
            LLMReasoningResult.fir_id
            == FIRRecord.fir_id,
        )
        .filter(
            FIRRecord.fir_id == fir_id,
        )
        .order_by(
            LLMReasoningResult.reasoning_id.desc()
        )
        .all()
    )

    results = []

    for reasoning_row, fir_row in rows:

        relations = (
            reasoning_row.relations
            or []
        )

        suspicious_flags = (
            reasoning_row.suspicious_flags
            or []
        )

        results.append(
            {
                "fir_id": fir_row.fir_id,

                "case_id": fir_row.case_id,

                "fir_number": (
                    fir_row.fir_number
                ),

                "police_station": (
                    fir_row.police_station
                ),

                "district": (
                    fir_row.district
                ),

                "state": (
                    fir_row.state
                ),

                "source_file": (
                    fir_row.source_file
                ),

                "reasoning_id": (
                    reasoning_row.reasoning_id
                ),

                "model_used": (
                    reasoning_row.model_used
                ),

                "created_at": (
                    reasoning_row.created_at.isoformat()
                    if reasoning_row.created_at
                    else None
                ),

                "relations": relations,

                "suspicious_flags": suspicious_flags,
            }
        )

    return {
        "fir_id": fir_id,
        "investigations": results,
        "total": len(results),
    }# ================================================================
# BUILD / PROJECT GRAPH
# ================================================================

@router.post("/{fir_id}/project")
async def project_fir_graph(
    fir_id: int,
    db: Session = Depends(get_db),
):
    """
    Project the latest validated LLM reasoning result
    for a FIR into Neo4j Aura.
    """

    # ------------------------------------------------------------
    # Get latest LLM reasoning result from PostgreSQL
    # ------------------------------------------------------------

    reasoning_row = (
        db.query(LLMReasoningResult)
        .filter(
            LLMReasoningResult.fir_id == fir_id
        )
        .order_by(
            LLMReasoningResult.reasoning_id.desc()
        )
        .first()
    )

    if reasoning_row is None:

        raise HTTPException(
            status_code=404,
            detail=(
                f"No LLM reasoning result found "
                f"for FIR {fir_id}."
            ),
        )

    # ------------------------------------------------------------
    # Prepare LLM result for GraphBuilder
    # ------------------------------------------------------------

    llm_result = {
        "relations": reasoning_row.relations or [],
        "suspicious_flags": (
            reasoning_row.suspicious_flags or []
        ),
        "summary": "",
    }

    # ------------------------------------------------------------
    # Project validated reasoning into Neo4j
    # ------------------------------------------------------------

    neo4j_client = Neo4jClient()

    try:

        neo4j_client.verify_connection()

        graph_builder = GraphBuilder(
            neo4j_client
        )

        relationships_written = (
            graph_builder.build_from_llm_result(
                llm_result=llm_result,
                fir_id=fir_id,
                reasoning_id=reasoning_row.reasoning_id,
                model_used=reasoning_row.model_used,
            )
        )

    except Exception as e:

        raise HTTPException(
            status_code=502,
            detail=(
                f"Neo4j graph projection failed: {str(e)}"
            ),
        )

    finally:

        neo4j_client.close()

    return {
        "fir_id": fir_id,
        "reasoning_id": reasoning_row.reasoning_id,
        "model_used": reasoning_row.model_used,
        "relationships_written": relationships_written,
    }


# ================================================================
# GET FIR GRAPH
# ================================================================

@router.get("/{fir_id}")
async def get_fir_graph(
    fir_id: int,
):
    """
    Return the Neo4j graph for a FIR in a
    frontend-friendly JSON structure.
    """

    neo4j_client = Neo4jClient()

    try:

        neo4j_client.verify_connection()

        query = """
        MATCH (source)-[r]->(target)
        WHERE r.fir_id = $fir_id

        RETURN
            source.entity_key AS source_id,
            source.name AS source_name,
            source.entity_type AS source_type,

            type(r) AS relation,

            target.entity_key AS target_id,
            target.name AS target_name,
            target.entity_type AS target_type,

            r.fir_id AS fir_id,
            r.reasoning_id AS reasoning_id,
            r.confidence AS confidence,
            r.evidence_level AS evidence_level,
            r.reasoning AS reasoning,
            r.model_used AS model_used
        """

        with neo4j_client.driver.session(
     database=NEO4J_DATABASE
    ) as session:

            result = session.run(
                query,
                fir_id=fir_id,
            )

            nodes = {}
            edges = []

            for record in result:

                source_id = record["source_id"]
                target_id = record["target_id"]

                # ------------------------------------------------
                # Source node
                # ------------------------------------------------

                if source_id not in nodes:

                    nodes[source_id] = {
                        "id": source_id,
                        "label": record["source_name"],
                        "type": record["source_type"],
                    }

                # ------------------------------------------------
                # Target node
                # ------------------------------------------------

                if target_id not in nodes:

                    nodes[target_id] = {
                        "id": target_id,
                        "label": record["target_name"],
                        "type": record["target_type"],
                    }

                # ------------------------------------------------
                # Relationship
                # ------------------------------------------------

                edges.append(
                    {
                        "id": (
                            f"{source_id}"
                            f"->{record['relation']}"
                            f"->{target_id}"
                            f":{record['reasoning_id']}"
                        ),
                        "source": source_id,
                        "target": target_id,
                        "relation": record["relation"],
                        "confidence": record["confidence"],
                        "evidence_level": (
                            record["evidence_level"]
                        ),
                        "reasoning_id": (
                            record["reasoning_id"]
                        ),
                        "fir_id": record["fir_id"],
                        "reasoning": record["reasoning"],
                        "model_used": record["model_used"],
                    }
                )

        return {
            "fir_id": fir_id,
            "nodes": list(nodes.values()),
            "edges": edges,
        }

    except Exception as e:

        raise HTTPException(
            status_code=502,
            detail=(
                f"Failed to retrieve FIR graph: {str(e)}"
            ),
        )

    finally:

        neo4j_client.close()