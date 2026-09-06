"""
LLM reasoning test suite.

Tests:
1. Payload + FIR context compatibility
2. Prompt contains FIR context
3. Low-confidence relation filtering
4. Invalid JSON retry
5. Full pipeline with an injected fake LLM
6. Optional real LLM test against an existing FIR

Run:
    python -m tests.test_llm

The real LLM test is disabled by default.

To enable:
    $env:RUN_REAL_LLM="1"
    python -m tests.test_llm
"""

from __future__ import annotations

import asyncio
import os
from types import SimpleNamespace


# ---------------------------------------------------------------------------
# Imports
# ---------------------------------------------------------------------------

from services.llm_reasoning import (
    LLMReasoningError,
    LLMReasoningService,
)


# ---------------------------------------------------------------------------
# Test constants
# ---------------------------------------------------------------------------

FIR_ID = 2

TEST_FIR_CONTEXT = (
    "The FIR concerns an alleged coordinated theft involving "
    "two persons. The incident occurred near Cuttack railway station "
    "on 2026-01-10."
)


VALID_LLM_JSON = """
{
    "relations": [
                {
            "from": "Rahul Sharma",
            "from_type": "PERSON",
            "to": "9876543210",
            "to_type": "PHONE",
            "relation": "CALLED",
            "reasoning": "Contact evidence shows Rahul Sharma called 9876543210.",
            "evidence_level": "DIRECT",
            "confidence": 0.85
        },
        {
            "from": "Rahul Sharma",
            "from_type": "PERSON",
            "to": "Priya Nair",
            "to_type": "PERSON",
            "relation": "ASSOCIATE",
            "reasoning": "The supplied evidence indicates an association.",
            "evidence_level": "INFERRED",
            "confidence": 0.45
        }],
    "suspicious_flags": [
        {
            "flag": "communication_burst",
            "entities": ["Rahul Sharma", "9876543210"],
            "detail": "Repeated contact activity was found in the supplied evidence."
        }
    ],
    "summary": "The supplied evidence indicates a communication relationship involving Rahul Sharma."
}
"""


# ---------------------------------------------------------------------------
# Fake LLM
# ---------------------------------------------------------------------------

class FakeLLM:
    """
    Small LangChain-compatible fake.

    It implements only the method our service actually calls:
        ainvoke(messages)
    """

    def __init__(
        self,
        responses: list[str],
        usage: dict | None = None,
    ):
        self.responses = list(responses)
        self.calls = []
        self.usage = usage or {
            "input_tokens": 123,
            "output_tokens": 45,
        }

    async def ainvoke(self, messages):

        self.calls.append(messages)

        if not self.responses:
            raise RuntimeError(
                "FakeLLM has no response remaining."
            )

        content = self.responses.pop(0)

        return SimpleNamespace(
            content=content,
            usage_metadata=self.usage,
        )


# ---------------------------------------------------------------------------
# Test payload
# ---------------------------------------------------------------------------

def make_test_payload() -> dict:
    """
    Minimal payload compatible with the current prompts.py contract.

    This avoids requiring PostgreSQL for the unit tests.
    """

    return {
        "fir_id": FIR_ID,
        "total_entities": 2,
        "processed_at": "2026-09-04T16:00:00",
        "fir_context": TEST_FIR_CONTEXT,
        "entities": [
            {
                "entity_type": "PERSON",
                "entity_value": "Rahul Sharma",
                "entity_score": 0.87,
                "db_hit_count": 2,
                "hits": {
                    "contact": [
                        {
                            "caller_name": "Rahul Sharma",
                            "caller_phone": "9876543210",
                            "receiver_name": "Priya Nair",
                            "receiver_phone": "9876543211",
                            "call_timestamp": "2026-01-09 21:15:00",
                            "duration_seconds": 312,
                            "call_type": "outgoing",
                        }
                    ],
                    "bank": [],
                    "crime": [],
                    "surveillance": [],
                    "social": [],
                    "other_firs": [],
                },
            },
            {
                "entity_type": "PERSON",
                "entity_value": "Priya Nair",
                "entity_score": 0.62,
                "db_hit_count": 1,
                "hits": {
                    "contact": [],
                    "bank": [],
                    "crime": [],
                    "surveillance": [],
                    "social": [],
                    "other_firs": [],
                },
            },
        ],
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_service(fake_llm) -> LLMReasoningService:
    """
    Construct the service without initializing a real provider.

    This lets us test llm_reasoning.py independently of API keys.
    """

    service = LLMReasoningService.__new__(
        LLMReasoningService
    )

    service.provider = "test"
    service.model = "fake-test-model"
    service.temperature = 0.0
    service.llm = fake_llm

    return service


def assert_true(condition, message):

    if not condition:
        raise AssertionError(message)


# ---------------------------------------------------------------------------
# TEST 1
# Payload + FIR context
# ---------------------------------------------------------------------------

def test_payload_and_fir_context():

    print("\n[TEST 1] Payload + FIR context")

    fake_llm = FakeLLM(
        responses=[VALID_LLM_JSON]
    )

    service = make_service(fake_llm)

    payload = make_test_payload()

    normalised = service._normalise_input(
        payload,
        fir_context=TEST_FIR_CONTEXT,
    )

    assert_true(
        normalised["fir_context"] == TEST_FIR_CONTEXT,
        "fir_context was not preserved.",
    )

    assert_true(
        normalised["fir_id"] == FIR_ID,
        "FIR ID was changed.",
    )

    assert_true(
        len(normalised["entities"]) == 2,
        "Entity count changed unexpectedly.",
    )

    print("PASS")


# ---------------------------------------------------------------------------
# TEST 2
# FIR context reaches the actual prompt
# ---------------------------------------------------------------------------

def test_fir_context_reaches_prompt():

    print("\n[TEST 2] FIR context reaches prompt")

    fake_llm = FakeLLM(
        responses=[VALID_LLM_JSON]
    )

    service = make_service(fake_llm)

    payload = make_test_payload()

    prepared_payload, messages, estimate = (
        service.prepare(
            payload,
            fir_context=TEST_FIR_CONTEXT,
        )
    )

    assert_true(
        prepared_payload["fir_context"]
        == TEST_FIR_CONTEXT,
        "Prepared payload lost FIR context.",
    )

    assert_true(
        len(messages) == 2,
        "Expected system + user messages.",
    )

    user_prompt = messages[1]["content"]

    assert_true(
        TEST_FIR_CONTEXT in user_prompt,
        "FIR context is NOT present in the user prompt.",
    )

    assert_true(
        "Rahul Sharma" in user_prompt,
        "Entity evidence is missing from prompt.",
    )

    print("Estimated tokens:", estimate)
    print("PASS")


# ---------------------------------------------------------------------------
# TEST 3
# Low confidence relation is filtered
# ---------------------------------------------------------------------------

def test_low_confidence_filtering():

    print("\n[TEST 3] Low-confidence relation filtering")

    fake_llm = FakeLLM(
        responses=[VALID_LLM_JSON]
    )

    service = make_service(fake_llm)

    parsed = service._parse_json(
        VALID_LLM_JSON
    )

    result = service._validate_output(
        parsed
    )

    relations = result["relations"]

    assert_true(
        len(relations) == 1,
        (
            "Expected the 0.45 relation to be "
            "filtered out."
        ),
    )

    assert_true(
        relations[0]["confidence"] == 0.85,
        "Wrong relation remained after filtering.",
    )

    print(
        "Remaining relations:",
        len(relations),
    )

    print("PASS")


# ---------------------------------------------------------------------------
# TEST 4
# Invalid JSON triggers exactly one retry
# ---------------------------------------------------------------------------

async def test_json_retry():

    print("\n[TEST 4] JSON retry")

    fake_llm = FakeLLM(
        responses=[
            "This is not JSON.",
            VALID_LLM_JSON,
        ]
    )

    service = make_service(
        fake_llm
    )

    payload = make_test_payload()

    result = await service.get_response_llm(
        payload,
        fir_context=TEST_FIR_CONTEXT,
    )

    assert_true(
        len(fake_llm.calls) == 2,
        (
            "Expected exactly two LLM calls "
            "(initial + retry)."
        ),
    )

    assert_true(
        result["result"]["relations"],
        "Retry result contains no valid relations.",
    )

    assert_true(
        result["model_used"] == "fake-test-model",
        "model_used was not preserved.",
    )

    assert_true(
        result["prompt_tokens"] == 123,
        "Prompt token usage was not captured.",
    )

    assert_true(
        result["completion_tokens"] == 45,
        "Completion token usage was not captured.",
    )

    # The second request must contain the strict JSON instruction.
    retry_messages = fake_llm.calls[1]

    retry_prompt = retry_messages[-1]["content"]

    assert_true(
        "Return ONLY one valid JSON object"
        in retry_prompt,
        "Strict JSON instruction was not added to retry.",
    )

    print(
        "LLM calls:",
        len(fake_llm.calls),
    )

    print(
        "Prompt tokens:",
        result["prompt_tokens"],
    )

    print(
        "Completion tokens:",
        result["completion_tokens"],
    )

    print("PASS")


# ---------------------------------------------------------------------------
# TEST 5
# Invalid JSON twice -> controlled error
# ---------------------------------------------------------------------------

async def test_double_json_failure():

    print("\n[TEST 5] Double JSON failure")

    fake_llm = FakeLLM(
        responses=[
            "broken response",
            "still broken response",
        ]
    )

    service = make_service(
        fake_llm
    )

    payload = make_test_payload()

    try:

        await service.get_response_llm(
            payload,
            fir_context=TEST_FIR_CONTEXT,
        )

    except LLMReasoningError as exc:

        assert_true(
            len(fake_llm.calls) == 2,
            "Expected exactly two attempts.",
        )

        assert_true(
            "both attempts" in str(exc),
            "Unexpected retry error message.",
        )

        print(
            "Controlled error:",
            exc,
        )

        print("PASS")
        return

    raise AssertionError(
        "Expected LLMReasoningError."
    )


# ---------------------------------------------------------------------------
# TEST 6
# Full fake LLM pipeline
# ---------------------------------------------------------------------------

async def test_full_fake_pipeline():

    print("\n[TEST 6] Full fake LLM pipeline")

    fake_llm = FakeLLM(
        responses=[VALID_LLM_JSON]
    )

    service = make_service(
        fake_llm
    )

    payload = make_test_payload()

    result = await service.get_response_llm(
        payload,
        fir_context=TEST_FIR_CONTEXT,
    )

    output = result["result"]

    assert_true(
        isinstance(output, dict),
        "Result is not a dictionary.",
    )

    assert_true(
        "relations" in output,
        "relations missing.",
    )

    assert_true(
        "suspicious_flags" in output,
        "suspicious_flags missing.",
    )

    assert_true(
        "summary" in output,
        "summary missing.",
    )

    assert_true(
        isinstance(output["relations"], list),
        "relations is not a list.",
    )

    assert_true(
        isinstance(
            output["suspicious_flags"],
            list,
        ),
        "suspicious_flags is not a list.",
    )

    assert_true(
        isinstance(
            output["summary"],
            str,
        ),
        "summary is not a string.",
    )

    print(
        "Relations:",
        len(output["relations"]),
    )

    print(
        "Suspicious flags:",
        len(output["suspicious_flags"]),
    )

    print(
        "Summary:",
        output["summary"],
    )

    print("PASS")


# ---------------------------------------------------------------------------
# REAL LLM TEST
# ---------------------------------------------------------------------------

async def test_real_llm():

    print("\n[REAL TEST] Existing FIR -> real LLM")

    from data_base.database import SessionLocal, init_db
    from models import fir, entities
    from models.fir import FIRRecord

    init_db()
    db = SessionLocal()

    try:

        # ---------------------------------------------------------------
        # Prefer the requested FIR if it has extracted entities.
        # Otherwise, fall back to any FIR that has extracted entities.
        # ---------------------------------------------------------------

        fir_record = (
            db.query(FIRRecord)
            .join(FIRRecord.extracted_entities)
            .filter(
                FIRRecord.fir_id == FIR_ID
            )
            .first()
        )

        if fir_record is None:
            fir_record = (
                db.query(FIRRecord)
                .join(FIRRecord.extracted_entities)
                .first()
            )

        if fir_record is None:

            print(
                "SKIP: No FIR with extracted entities exists."
            )

            return

        selected_fir_id = fir_record.fir_id

        extracted_entities = [
            {
                "text": entity.entity_value,
                "type": entity.entity_type,
                "confidence": entity.confidence,
                "source": entity.extraction_source,
            }
            for entity in fir_record.extracted_entities
        ]

        if not extracted_entities:

            print(
                "SKIP: Selected FIR has no extracted entities."
            )

            return

        print(
            "FIR ID:",
            selected_fir_id,
        )

        print(
            "Extracted entities:",
            len(extracted_entities),
        )

        from services.cross_lookup import (
            run_cross_lookup,
        )

        cross_result = run_cross_lookup(
            db=db,
            fir_id=selected_fir_id,
            entities=extracted_entities,
        )

        # ---------------------------------------------------------------
        # Prefer the actual FIR description when available.
        # ---------------------------------------------------------------

        fir_context = (
            fir_record.description
            or ""
        )

        if not fir_context.strip():

            print(
                "WARNING: FIR description is empty."
            )

        service = LLMReasoningService()

        print(
            "Provider:",
            service.provider,
        )

        print(
            "Model:",
            service.model,
        )

        result = await service.get_response_llm(
            cross_result,
            fir_context=fir_context,
        )

        output = result["result"]

        print("\n========== REAL LLM RESULT ==========")

        print(
            "Model:",
            result["model_used"],
        )

        print(
            "Prompt tokens:",
            result["prompt_tokens"],
        )

        print(
            "Completion tokens:",
            result["completion_tokens"],
        )

        print(
            "\nRelations:",
            len(output["relations"]),
        )

        for relation in output["relations"]:
            print(
                " ",
                relation,
            )

        print(
            "\nSuspicious flags:",
            len(
                output["suspicious_flags"]
            ),
        )

        for flag in output["suspicious_flags"]:
            print(
                " ",
                flag,
            )

        print(
            "\nSummary:",
            output["summary"],
        )

        print("\nREAL LLM TEST: PASS")

    finally:

        db.rollback()
        db.close()


# ---------------------------------------------------------------------------
# Test runner
# ---------------------------------------------------------------------------

async def run_async_tests():

    await test_json_retry()

    await test_double_json_failure()

    await test_full_fake_pipeline()


def main():

    print("=" * 70)
    print("LLM REASONING TEST SUITE")
    print("=" * 70)

    # Synchronous tests
    test_payload_and_fir_context()
    test_fir_context_reaches_prompt()
    test_low_confidence_filtering()

    # Async fake-LLM tests
    asyncio.run(
        run_async_tests()
    )

    print("\n" + "=" * 70)
    print("ALL LOCAL LLM TESTS PASSED")
    print("=" * 70)

    # ---------------------------------------------------------------
    # Real API test is explicitly opt-in.
    # ---------------------------------------------------------------

    if os.getenv(
        "RUN_REAL_LLM"
    ) == "1":

        asyncio.run(
            test_real_llm()
        )

    else:

        print(
            "\nREAL LLM TEST: SKIPPED"
        )

        print(
            "To enable it:"
        )

        print(
            "  $env:RUN_REAL_LLM='1'"
        )

        print(
            "  python -m tests.test_llm"
        )


if __name__ == "__main__":
    main()