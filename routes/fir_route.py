import hashlib

from fastapi import (
    APIRouter,
    UploadFile,
    File,
    HTTPException,
    Depends,
)

from fastapi.concurrency import (
    run_in_threadpool,
)

from sqlalchemy.orm import Session

from data_base.database import get_db

from models.fir import FIRRecord
from models.entities import ExtractedEntity

from services.pdf_reader import (
    extract_text_from_pdf,
)

from services.new_ner import (
    extract_entities,
    get_entity_text,
    get_entity_type,
)

from services.cross_lookup import (
    run_cross_lookup,
    result_to_groq_payload,
)

from services.llm_reasoning import (
    LLMReasoningService,
    LLMReasoningError,
)

from models.users import User

from services.rbac import (
    require_permission,
)

from services.blockchain_service import (
    record_fir_event,
)


router = APIRouter(
    prefix="/firs",
    tags=["FIR"],
)


MAX_UPLOAD_BYTES = 20 * 1024 * 1024  # 20 MB


def _texts_for_type(
    entities: list[dict],
    *types: str,
) -> list[str]:

    wanted = {
        t.upper()
        for t in types
    }

    values = []
    seen = set()

    for entity in entities:

        if get_entity_type(entity) not in wanted:
            continue

        text = get_entity_text(
            entity
        )

        if not text:
            continue

        key = text.lower()

        if key not in seen:

            seen.add(key)
            values.append(text)

    return values


def _first_of_type(
    entities: list[dict],
    etype: str,
    limit: int = 100,
) -> str | None:

    for entity in entities:

        if get_entity_type(
            entity
        ) == etype.upper():

            value = get_entity_text(
                entity
            )

            if value:
                return value[:limit]

    return None


@router.post("/upload")
async def upload_fir(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_permission(
            "fir_records",
            "write",
        )
    ),
):

    # ------------------------------------------------------------
    # Read uploaded PDF
    # ------------------------------------------------------------

    file_bytes = await file.read()

    if len(file_bytes) > MAX_UPLOAD_BYTES:

        raise HTTPException(
            status_code=413,
            detail=(
                f"PDF exceeds the "
                f"{MAX_UPLOAD_BYTES // (1024 * 1024)} "
                f"MB upload limit."
            ),
        )

    filename = (
        file.filename
        or "upload.pdf"
    )

    content_type = (
        file.content_type or ""
    ).split(";")[0].strip().lower()

    name_looks_pdf = (
        filename.lower().endswith(".pdf")
    )

    type_ok = content_type in {
        "application/pdf",
        "application/octet-stream",
        "binary/octet-stream",
        "",
    }

    # ------------------------------------------------------------
    # Validate PDF
    # ------------------------------------------------------------

    if not file_bytes.startswith(
        b"%PDF"
    ):

        if not (
            name_looks_pdf
            or type_ok
            or content_type == "application/pdf"
        ):

            raise HTTPException(
                status_code=400,
                detail="Only PDF files are allowed.",
            )

        raise HTTPException(
            status_code=400,
            detail="File is not a valid PDF.",
        )

    source_hash = hashlib.sha256(
        file_bytes
    ).hexdigest()

    # ------------------------------------------------------------
    # Extract text from PDF
    # ------------------------------------------------------------

    try:

        extracted_text = await run_in_threadpool(
            extract_text_from_pdf,
            file_bytes,
        )

    except Exception as e:

        raise HTTPException(
            status_code=400,
            detail=(
                f"Failed to read PDF: {str(e)}"
            ),
        )

    if not extracted_text.strip():

        raise HTTPException(
            status_code=400,
            detail=(
                "No text could be extracted "
                "from this PDF."
            ),
        )

    # ------------------------------------------------------------
    # NER
    # ------------------------------------------------------------

    try:

        entities = await run_in_threadpool(
            extract_entities,
            extracted_text,
        )

    except Exception as e:

        raise HTTPException(
            status_code=500,
            detail=(
                f"Entity extraction failed: {str(e)}"
            ),
        )

    # ------------------------------------------------------------
    # Extract important entity groups
    # ------------------------------------------------------------

    case_id = (
        _first_of_type(
            entities,
            "CASE_ID",
        )
        or f"CASE-{filename}"[:100]
    )

    fir_number = _first_of_type(
        entities,
        "FIR_NUMBER",
    )

    persons = _texts_for_type(
        entities,
        "PERSON",
    )

    vehicles = _texts_for_type(
        entities,
        "VEHICLE",
    )

    phones = _texts_for_type(
        entities,
        "PHONE",
    )

    orgs = _texts_for_type(
        entities,
        "ORGANIZATION",
        "ORG",
    )

    locations = _texts_for_type(
        entities,
        "LOCATION",
    )

    # ------------------------------------------------------------
    # Create FIR record
    # ------------------------------------------------------------

    try:

        fir = FIRRecord(
            case_id=case_id,
            fir_number=fir_number,
            description=extracted_text,
            source_file=filename,
            source_hash=source_hash,
            persons_mentioned=persons,
            vehicles_mentioned=vehicles,
            phones_mentioned=phones,
            organizations_mentioned=orgs,
            locations_mentioned=locations,
        )

        db.add(fir)

        # Flush so fir_id is generated before
        # normalized entities and cross lookup.
        db.flush()

        # --------------------------------------------------------
        # Persist normalized NER entities
        # --------------------------------------------------------

        for entity in entities:

            entity_text = get_entity_text(
                entity
            )

            entity_type = get_entity_type(
                entity
            )

            if (
                not entity_text
                or not entity_type
            ):
                continue

            extracted_entity = ExtractedEntity(
                fir_id=fir.fir_id,
                entity_type=entity_type,
                entity_value=entity_text,
                confidence=entity.get(
                    "confidence"
                ),
                extraction_source=entity.get(
                    "source"
                ),
            )

            db.add(
                extracted_entity
            )

        db.flush()

        # --------------------------------------------------------
        # Blockchain / provenance logging
        # --------------------------------------------------------
        #
        # The source PDF hash is recorded inside
        # the tamper-evident audit chain.
        #
        # No raw PDF content is placed into
        # the ledger.
        #
        # This is the centralized blockchain/provenance
        # implementation.
        # --------------------------------------------------------

        record_fir_event(
            db=db,
            fir_id=fir.fir_id,
            event_type="FIR_INGESTED",
            metadata={
                "source_file": filename,
                "source_hash": source_hash,
                "entity_count": len(entities),
            },
            actor_id=current_user.user_id,
            actor_role=current_user.role,
        )

        # --------------------------------------------------------
        # Cross-database lookup
        # --------------------------------------------------------

        cross_result = await run_in_threadpool(
            run_cross_lookup,
            db,
            fir.fir_id,
            entities,
            current_user.user_id,
            current_user.role,
        )

        # Convert deterministic lookup result
        # into the evidence structure expected by the LLM.
        groq_payload = result_to_groq_payload(
            cross_result
        )

        # --------------------------------------------------------
        # LLM reasoning
        # --------------------------------------------------------

        try:

            llm_service = LLMReasoningService()

            llm_response = await (
                llm_service.get_response_llm(
                    cross_result,
                    fir_context=(
                        fir.description or ""
                    ),
                )
            )

            # ----------------------------------------------------
            # Persist validated LLM reasoning result
            # ----------------------------------------------------

            llm_row = llm_service.save_result(
                db=db,
                fir_id=fir.fir_id,
                reasoning_response=llm_response,
            )

            db.flush()

        except LLMReasoningError as e:

            raise HTTPException(
                status_code=502,
                detail=(
                    f"LLM reasoning failed: {str(e)}"
                ),
            )

        # --------------------------------------------------------
        # Commit PostgreSQL investigation
        #
        # FIR
        # + normalized entities
        # + blockchain/provenance
        # + cross lookup changes
        # + LLM reasoning
        #
        # Neo4j is NOT handled here anymore.
        # --------------------------------------------------------

        db.commit()

    except HTTPException:

        db.rollback()
        raise

    except Exception as e:

        db.rollback()

        raise HTTPException(
            status_code=500,
            detail=(
                "FIR upload pipeline failed: "
                f"{str(e)}"
            ),
        )

    # ------------------------------------------------------------
    # Final response
    # ------------------------------------------------------------

    return {
        "fir_id": fir.fir_id,
        "filename": filename,
        "content_type": file.content_type,
        "case_id": case_id,
        "fir_number": fir_number,
        "source_hash": source_hash,
        "entities": entities,

        "cross_lookup": groq_payload,

        "llm_reasoning": {
            "reasoning_id": (
                llm_row.reasoning_id
            ),
            "relations": (
                llm_response["result"]["relations"]
            ),
            "suspicious_flags": (
                llm_response["result"][
                    "suspicious_flags"
                ]
            ),
            "summary": (
                llm_response["result"]["summary"]
            ),
            "model_used": (
                llm_response["model_used"]
            ),
            "prompt_tokens": (
                llm_response["prompt_tokens"]
            ),
            "completion_tokens": (
                llm_response["completion_tokens"]
            ),
        },
    }