"""
LLM reasoning service for criminal-network analysis.

Pipeline:
    CrossLookupResult
        -> result_to_groq_payload()
        -> add FIR context
        -> build_messages()
        -> selected chat model
        -> raw response
        -> JSON extraction/parsing
        -> schema validation/filtering
        -> predictable Python dict
        -> optional DB persistence

The service does not access the database to obtain FIR context.
The caller supplies the FIR context explicitly.
"""

from __future__ import annotations

import json
import logging
import os
from copy import deepcopy
from pathlib import Path
import sys
from typing import Any

from dotenv import load_dotenv

sys.path.append(str(Path(__file__).resolve().parent.parent))

from services.cross_lookup import (
    CrossLookupResult,
    result_to_groq_payload,
)

from data_base.prompts import (
    build_messages,
    estimate_tokens,
)


load_dotenv()

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DEFAULT_PROVIDER = "groq"
DEFAULT_GROQ_MODEL = "qwen/qwen3.8-27b"
DEFAULT_OPENROUTER_MODEL = "nvidia/nemotron-3.5-lightning:free"

MAX_INPUT_TOKENS = 32_000


STRICT_JSON_INSTRUCTION = """
CRITICAL OUTPUT REQUIREMENT:

Return ONLY one valid JSON object.

Do not return:
- markdown
- ```json fences
- explanations before the JSON
- explanations after the JSON
- comments
- extra text

The first character of your response must be '{'.
The last character of your response must be '}'.

Follow the required JSON schema exactly.
"""


class LLMReasoningError(RuntimeError):
    """Controlled error raised for LLM reasoning failures."""


class LLMReasoningService:
    """Build prompts, call the configured LLM, parse and validate JSON."""

    def __init__(
        self,
        provider: str | None = None,
        model: str | None = None,
        temperature: float = 0.0,
        llm: Any | None = None,
    ) -> None:

        self.provider = (
            provider
            or os.getenv("LLM_PROVIDER")
            or DEFAULT_PROVIDER
        ).strip().lower()

        self.model = (
            model
            or os.getenv("LLM_MODEL")
            or self._default_model()
        )

        self.temperature = temperature

        # Allows tests to inject a fake LangChain-compatible model.
        self.llm = (
            llm
            if llm is not None
            else self._build_llm()
        )

    # -----------------------------------------------------------------------
    # Provider configuration
    # -----------------------------------------------------------------------

    def _default_model(self) -> str:

        if self.provider == "openrouter":
            return (
                os.getenv("OPENROUTER_MODEL")
                or DEFAULT_OPENROUTER_MODEL
            )

        return (
            os.getenv("GROQ_MODEL")
            or DEFAULT_GROQ_MODEL
        )

    def _build_llm(self) -> Any:
        """Create the configured provider client."""

        try:

            if self.provider == "groq":

                from langchain_groq import ChatGroq

                api_key = os.getenv("GROQ_API_KEY")

                if not api_key:
                    raise LLMReasoningError(
                        "GROQ_API_KEY is not configured."
                    )

                return ChatGroq(
                    model=self.model,
                    temperature=self.temperature,
                    api_key=api_key,
                    max_tokens=900,
                )

            if self.provider == "openrouter":

                from langchain_openrouter import ChatOpenRouter

                api_key = os.getenv("OPENROUTER_API_KEY")

                if not api_key:
                    raise LLMReasoningError(
                        "OPENROUTER_API_KEY is not configured."
                    )

                return ChatOpenRouter(
                    model=self.model,
                    temperature=self.temperature,
                    api_key=api_key,
                )

            raise LLMReasoningError(
                f"Unsupported LLM_PROVIDER '{self.provider}'. "
                "Use 'groq' or 'openrouter'."
            )

        except LLMReasoningError:
            raise

        except ImportError as exc:
            raise LLMReasoningError(
                f"LLM provider package is unavailable "
                f"for '{self.provider}': {exc}"
            ) from exc

        except Exception as exc:
            raise LLMReasoningError(
                f"Failed to initialize LLM provider "
                f"'{self.provider}' with model "
                f"'{self.model}': {exc}"
            ) from exc

    # -----------------------------------------------------------------------
    # Payload preparation
    # -----------------------------------------------------------------------

    @staticmethod
    def _normalise_input(
        cross_lookup_result: CrossLookupResult | dict[str, Any],
        fir_context: str | None = None,
    ) -> dict[str, Any]:
        """
        Convert CrossLookupResult into the LLM payload.

        fir_context contains the crime/FIR description supplied by the
        caller. It is intentionally kept separate from cross-database hits.
        """

        if isinstance(
            cross_lookup_result,
            CrossLookupResult,
        ):

            payload = result_to_groq_payload(
                cross_lookup_result
            )

        elif isinstance(
            cross_lookup_result,
            dict,
        ):

            payload = deepcopy(
                cross_lookup_result
            )

        else:

            raise TypeError(
                "cross_lookup_result must be "
                "CrossLookupResult or dict payload"
            )

        # Always provide the field so the prompt contract is predictable.
        payload["fir_context"] = (
            fir_context.strip()
            if isinstance(fir_context, str)
            else ""
        )

        return payload

    @staticmethod
    def _reduce_payload(
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Reduce evidence deterministically when the prompt exceeds 32k tokens.
        """

        reduced = deepcopy(payload)

        entities = reduced.get(
            "entities"
        ) or []

        caps = {
            "contact": 10,
            "bank": 10,
            "crime": 5,
            "surveillance": 5,
            "social": 5,
            "other_firs": 5,
        }

        for entity in entities:

            hits = entity.get(
                "hits"
            ) or {}

            for key, cap in caps.items():

                rows = hits.get(key)

                if isinstance(rows, list):
                    hits[key] = rows[:cap]

        # Progressively reduce the number of entities.
        while entities:

            reduced["entities"] = entities

            if estimate_tokens(
                reduced
            )["within_32k_limit"]:

                return reduced

            new_length = max(
                1,
                len(entities) // 2,
            )

            entities = entities[:new_length]

        reduced["entities"] = []

        return reduced

    def prepare(
        self,
        cross_lookup_result: CrossLookupResult | dict[str, Any],
        fir_context: str | None = None,
    ):
        """
        Prepare payload, messages and token estimate.

        fir_context is the FIR description/crime context that the LLM needs
        in addition to cross-database evidence.
        """

        payload = self._normalise_input(
            cross_lookup_result,
            fir_context=fir_context,
        )

        estimate = estimate_tokens(
            payload
        )

        if not estimate["within_32k_limit"]:

            payload = self._reduce_payload(
                payload
            )

            estimate = estimate_tokens(
                payload
            )

        if not estimate["within_32k_limit"]:

            raise LLMReasoningError(
                "LLM reasoning evidence is still above "
                "the 32k input-token limit after "
                "deterministic reduction."
            )

        messages = build_messages(
            payload
        )

        return (
            payload,
            messages,
            estimate,
        )

    # -----------------------------------------------------------------------
    # Strict retry prompt
    # -----------------------------------------------------------------------

    @staticmethod
    def _make_strict_retry_messages(
        messages: list[Any],
    ) -> list[Any]:
        """
        Add a strict JSON-only instruction for the second attempt.
        """

        retry_messages = deepcopy(
            messages
        )

        if not retry_messages:
            return retry_messages

        # Add the strict instruction to the user message.
        user_message = retry_messages[-1]

        if isinstance(user_message, dict):

            current_content = user_message.get(
                "content",
                "",
            )

            user_message["content"] = (
                f"{current_content}\n\n"
                f"{STRICT_JSON_INSTRUCTION}"
            )

        else:

            # Supports message-like objects where content can be changed.
            current_content = getattr(
                user_message,
                "content",
                "",
            )

            try:

                user_message.content = (
                    f"{current_content}\n\n"
                    f"{STRICT_JSON_INSTRUCTION}"
                )

            except Exception:
                pass

        return retry_messages

    # -----------------------------------------------------------------------
    # Response extraction
    # -----------------------------------------------------------------------

    @staticmethod
    def _extract_content(
        response: Any,
    ) -> str:
        """
        Extract text from a LangChain AIMessage or compatible response.
        """

        content = getattr(
            response,
            "content",
            response,
        )

        if isinstance(
            content,
            str,
        ):

            return content.strip()

        if isinstance(
            content,
            list,
        ):

            parts: list[str] = []

            for item in content:

                if isinstance(
                    item,
                    str,
                ):

                    parts.append(item)

                elif isinstance(
                    item,
                    dict,
                ):

                    text = item.get(
                        "text"
                    )

                    if isinstance(
                        text,
                        str,
                    ):

                        parts.append(text)

            return "".join(parts).strip()

        raise LLMReasoningError(
            "LLM returned an unsupported "
            "response content type."
        )

    # -----------------------------------------------------------------------
    # JSON parsing
    # -----------------------------------------------------------------------

    @staticmethod
    def _parse_json(
        raw_text: str,
    ) -> dict[str, Any]:
        """
        Parse a JSON-only response.

        Markdown fences are tolerated because some models still return them,
        but arbitrary prose is not accepted.
        """

        text = raw_text.strip()

        if not text:

            raise LLMReasoningError(
                "LLM returned an empty response."
            )

        # Handle accidental markdown fences.
        if (
            text.startswith("```")
            and text.endswith("```")
        ):

            lines = text.splitlines()

            if (
                lines
                and lines[0].strip().startswith("```")
            ):

                lines = lines[1:]

            if (
                lines
                and lines[-1].strip() == "```"
            ):

                lines = lines[:-1]

            text = "\n".join(
                lines
            ).strip()

            if text.lower().startswith(
                "json\n"
            ):

                text = text[5:].lstrip()

        try:

            data = json.loads(
                text
            )

        except json.JSONDecodeError as exc:

            raise LLMReasoningError(
                f"LLM response is not valid JSON: "
                f"{exc.msg}"
            ) from exc

        if not isinstance(
            data,
            dict,
        ):

            raise LLMReasoningError(
                "LLM JSON root must be an object."
            )

        return data

    # -----------------------------------------------------------------------
    # Output validation
    # -----------------------------------------------------------------------

    @staticmethod
    def _validate_output(
        data: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Validate the reasoning output.

        Relations below 0.50 confidence are filtered rather than causing
        the entire reasoning result to fail.
        """

        required = {
            "relations",
            "suspicious_flags",
            "summary",
        }

        missing = (
            required - data.keys()
        )

        if missing:

            raise LLMReasoningError(
                "LLM JSON is missing required fields: "
                f"{sorted(missing)}"
            )

        relations = data[
            "relations"
        ]

        flags = data[
            "suspicious_flags"
        ]

        summary = data[
            "summary"
        ]

        if not isinstance(
            relations,
            list,
        ):

            raise LLMReasoningError(
                "'relations' must be a list."
            )

        if not isinstance(
            flags,
            list,
        ):

            raise LLMReasoningError(
                "'suspicious_flags' must be a list."
            )

        if not isinstance(
            summary,
            str,
        ):

            raise LLMReasoningError(
                "'summary' must be a string."
            )

        allowed_types = {
            "PERSON",
            "PHONE",
            "VEHICLE",
            "LOCATION",
            "ORGANIZATION",
            "ACCOUNT",
        }

        allowed_relations = {
            "CALLED",
            "FINANCIAL_LINK",
            "ASSOCIATE",
            "OWNS",
            "VISITED",
            "MEMBER_OF",
            "CO_ACCUSED",
            "SUSPECT_IN",
        }

        allowed_evidence_levels = {
            "DIRECT",
            "INFERRED",
        }

        valid_relations: list[
            dict[str, Any]
        ] = []

        filtered_count = 0

        for index, relation in enumerate(
            relations
        ):

            if not isinstance(
                relation,
                dict,
            ):

                raise LLMReasoningError(
                    f"relations[{index}] "
                    "must be an object."
                )

            required_relation = {
                "from",
                "from_type",
                "to",
                "to_type",
                "relation",
                "reasoning",
                "evidence_level",
                "confidence",
            }

            missing_relation = (
                required_relation
                - relation.keys()
            )

            if missing_relation:

                raise LLMReasoningError(
                    f"relations[{index}] "
                    f"missing fields: "
                    f"{sorted(missing_relation)}"
                )

            evidence_level = relation[
                "evidence_level"
            ]

            if evidence_level not in allowed_evidence_levels:

                raise LLMReasoningError(
                    f"relations[{index}].evidence_level "
                    f"is invalid: {evidence_level}"
                )

            if relation[
                "from_type"
            ] not in allowed_types:

                raise LLMReasoningError(
                    f"relations[{index}].from_type "
                    f"is invalid: "
                    f"{relation['from_type']}"
                )

            if relation[
                "to_type"
            ] not in allowed_types:

                raise LLMReasoningError(
                    f"relations[{index}].to_type "
                    f"is invalid: "
                    f"{relation['to_type']}"
                )

            if relation[
                "relation"
            ] not in allowed_relations:

                raise LLMReasoningError(
                    f"relations[{index}].relation "
                    f"is invalid: "
                    f"{relation['relation']}"
                )

            if (
                not isinstance(
                    relation["reasoning"],
                    str,
                )
                or not relation[
                    "reasoning"
                ].strip()
            ):

                raise LLMReasoningError(
                    f"relations[{index}].reasoning "
                    "must be a non-empty string."
                )

            confidence = relation[
                "confidence"
            ]

            if (
                isinstance(
                    confidence,
                    bool,
                )
                or not isinstance(
                    confidence,
                    (int, float),
                )
            ):

                raise LLMReasoningError(
                    f"relations[{index}].confidence "
                    "must be numeric."
                )

            confidence = float(
                confidence
            )

            # ---------------------------------------------------------------
            # IMPORTANT:
            # Low-confidence relations are discarded individually.
            # They do NOT kill the entire LLM response.
            # ---------------------------------------------------------------
            if confidence < 0.50:

                filtered_count += 1
                continue

            if confidence > 1.00:

                raise LLMReasoningError(
                    f"relations[{index}].confidence "
                    "must not exceed 1.00."
                )

            relation[
                "confidence"
            ] = confidence

            valid_relations.append(
                relation
            )

        # Replace original relations with filtered relations.
        data[
            "relations"
        ] = valid_relations

        # Keep useful diagnostic information without making it part of the
        # persisted LLM output contract.
        if filtered_count:

            logger.info(
                "Filtered %d low-confidence "
                "LLM relations below 0.50.",
                filtered_count,
            )

        # ---------------------------------------------------------------
        # Suspicious flags
        # ---------------------------------------------------------------

        for index, flag in enumerate(
            flags
        ):

            if not isinstance(
                flag,
                dict,
            ):

                raise LLMReasoningError(
                    f"suspicious_flags[{index}] "
                    "must be an object."
                )

            for key in (
                "flag",
                "entities",
                "detail",
            ):

                if key not in flag:

                    raise LLMReasoningError(
                        f"suspicious_flags[{index}] "
                        f"missing field: {key}"
                    )

            if not isinstance(
                flag["flag"],
                str,
            ):

                raise LLMReasoningError(
                    f"suspicious_flags[{index}].flag "
                    "must be a string."
                )

            if not isinstance(
                flag["entities"],
                list,
            ):

                raise LLMReasoningError(
                    f"suspicious_flags[{index}].entities "
                    "must be a list."
                )

            if not isinstance(
                flag["detail"],
                str,
            ):

                raise LLMReasoningError(
                    f"suspicious_flags[{index}].detail "
                    "must be a string."
                )

        return data

    # -----------------------------------------------------------------------
    # Token usage
    # -----------------------------------------------------------------------

    @staticmethod
    def _extract_usage(
        response: Any,
    ) -> tuple[int | None, int | None]:
        """
        Read actual token usage from common LangChain response formats.
        """

        usage = getattr(
            response,
            "usage_metadata",
            None,
        )

        if not isinstance(
            usage,
            dict,
        ):

            metadata = getattr(
                response,
                "response_metadata",
                {},
            )

            if isinstance(
                metadata,
                dict,
            ):

                usage = (
                    metadata.get(
                        "token_usage"
                    )
                    or metadata.get(
                        "usage"
                    )
                )

        if not isinstance(
            usage,
            dict,
        ):

            return None, None

        prompt = usage.get(
            "input_tokens",
            usage.get(
                "prompt_tokens"
            ),
        )

        completion = usage.get(
            "output_tokens",
            usage.get(
                "completion_tokens"
            ),
        )

        try:

            prompt = (
                int(prompt)
                if prompt is not None
                else None
            )

        except (
            TypeError,
            ValueError,
        ):

            prompt = None

        try:

            completion = (
                int(completion)
                if completion is not None
                else None
            )

        except (
            TypeError,
            ValueError,
        ):

            completion = None

        return (
            prompt,
            completion,
        )

    # -----------------------------------------------------------------------
    # LLM call
    # -----------------------------------------------------------------------

    async def get_response_llm(
        self,
        cross_lookup_result: CrossLookupResult | dict[str, Any],
        fir_context: str | None = None,
    ) -> dict[str, Any]:
        """
        Run LLM reasoning.

        Attempt 1:
            Normal prompt.

        Attempt 2:
            Only performed when JSON parsing fails.
            Adds a strict JSON-only instruction.

        Returns a predictable Python dictionary.
        """

        (
            payload,
            messages,
            estimate,
        ) = self.prepare(
            cross_lookup_result,
            fir_context=fir_context,
        )

        # ---------------------------------------------------------------
        # ATTEMPT 1
        # ---------------------------------------------------------------

        try:

            response = await self.llm.ainvoke(
                messages
            )

        except Exception as exc:

            raise LLMReasoningError(
                f"LLM request failed for provider "
                f"'{self.provider}' and model "
                f"'{self.model}': {exc}"
            ) from exc

        raw_response = self._extract_content(
            response
        )

        # ---------------------------------------------------------------
        # Try to parse the first response.
        # ---------------------------------------------------------------

        try:

            parsed = self._parse_json(
                raw_response
            )

        except LLMReasoningError as first_error:

            logger.warning(
                "LLM returned invalid JSON on "
                "first attempt. Retrying with "
                "strict JSON instruction."
            )

            # -----------------------------------------------------------
            # ATTEMPT 2 — STRICT JSON
            # -----------------------------------------------------------

            retry_messages = (
                self._make_strict_retry_messages(
                    messages
                )
            )

            try:

                retry_response = (
                    await self.llm.ainvoke(
                        retry_messages
                    )
                )

            except Exception as exc:

                raise LLMReasoningError(
                    "LLM retry request failed after "
                    f"JSON parse failure: {exc}"
                ) from exc

            raw_response = (
                self._extract_content(
                    retry_response
                )
            )

            try:

                parsed = self._parse_json(
                    raw_response
                )

            except LLMReasoningError as retry_error:

                raise LLMReasoningError(
                    "LLM returned invalid JSON on "
                    "both attempts. "
                    f"First error: {first_error}. "
                    f"Retry error: {retry_error}"
                ) from retry_error

            response = retry_response

        # ---------------------------------------------------------------
        # VALIDATE
        # ---------------------------------------------------------------

        validated = self._validate_output(
            parsed
        )

        # ---------------------------------------------------------------
        # ACTUAL TOKEN USAGE
        # ---------------------------------------------------------------

        prompt_tokens, completion_tokens = (
            self._extract_usage(
                response
            )
        )

        return {
            "result": validated,
            "raw_response": raw_response,
            "model_used": self.model,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "estimated_tokens": estimate,
            "payload": payload,
        }

    # -----------------------------------------------------------------------
    # Persistence
    # -----------------------------------------------------------------------

    @staticmethod
    def save_result(
        db: Any,
        fir_id: int,
        reasoning_response: dict[str, Any],
    ) -> Any:
        """
        Persist a validated reasoning result.

        The caller owns commit/rollback.
        """

        from models.llm_results import (
            LLMReasoningResult,
        )

        result = reasoning_response[
            "result"
        ]

        row = LLMReasoningResult(
            fir_id=fir_id,
            raw_response=reasoning_response.get(
                "raw_response"
            ),
            relations=result.get(
                "relations",
                [],
            ),
            suspicious_flags=result.get(
                "suspicious_flags",
                [],
            ),
            model_used=reasoning_response.get(
                "model_used"
            ),
            prompt_tokens=reasoning_response.get(
                "prompt_tokens"
            ),
            completion_tokens=reasoning_response.get(
                "completion_tokens"
            ),
        )

        db.add(row)
        db.flush()

        return row


# ---------------------------------------------------------------------------
# Backward-compatible class name
# ---------------------------------------------------------------------------

models_init = LLMReasoningService


__all__ = [
    "LLMReasoningError",
    "LLMReasoningService",
    "models_init",
]