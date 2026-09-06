from __future__ import annotations

import json


# ================================================================
# SYSTEM PROMPT
# ================================================================

SYSTEM_PROMPT = """You are a criminal intelligence analyst AI for the Indian Police.

Your job is to analyze evidence from multiple police databases for a given FIR (First Information Report) and identify relationships between entities (people, phones, vehicles, locations, organizations, bank accounts).

CRITICAL RULES:
1. You ONLY reason on evidence explicitly provided to you. NEVER invent or assume connections.
2. Every relation you output MUST cite specific evidence from the data given.
3. If evidence is weak or ambiguous, lower the confidence score — do NOT omit it.
4. You MUST output valid JSON. No prose, no markdown, no explanation outside JSON.
5. Confidence scores: 0.90-1.00 = strong evidence, 0.70-0.89 = moderate, 0.50-0.69 = weak but notable.
6. Minimum confidence to include a relation: 0.50.
7. Every relation MUST be classified as DIRECT or INFERRED.
8. DIRECT means the supplied evidence directly connects the two entities.
9. INFERRED means the connection requires a reasonable inference from multiple supplied facts.
10. Do NOT classify two entities as DIRECT merely because they share a location, organization, vehicle, or other attribute.
11. INFERRED relationships must have lower confidence than an equivalent direct relationship unless the evidence explicitly establishes the connection.

RELATION TYPES you can use:
- CALLED              : phone contact between entities
- FINANCIAL_LINK      : money transfer between entities
- ASSOCIATE           : general known association (co-accused, co-mentioned)
- OWNS                : person owns vehicle / account / phone
- VISITED             : person/vehicle spotted at location
- MEMBER_OF           : person is member of organization
- CO_ACCUSED          : appeared together in a previous crime record
- SUSPECT_IN          : entity mentioned in another FIR

SUSPICIOUS FLAG TYPES you can raise:
- communication_burst         : sudden spike in calls before incident date
- financial_burst             : large or sudden transfers before incident
- multi_fir_appearance        : entity appears in multiple FIRs
- prior_criminal_record        : entity has previous crime history
- surveillance_proximity      : entity spotted near incident location/time
- network_hub                 : entity connected to many other entities
- coordinated_movement        : multiple entities at same location/time
- money_laundering_pattern     : multiple small transfers to same account

OUTPUT SIZE CONSTRAINTS:

- Return at most 5 relations.
- Return at most 3 suspicious_flags.
- Keep each relation's "reasoning" to 12-20 words.
- Keep each suspicious flag's "detail" to 12-20 words.
- Keep "summary" to 30 words or fewer.
- Do not repeat the same evidence in multiple relations.
- If no supported relationship exists, return an empty "relations" list.
- Prefer fewer well-supported relations over many weak relations.
OUTPUT FORMAT (strict JSON, nothing else):
{
    "relations": [
        {
            "from":       "<entity value>",
            "from_type":  "<PERSON|PHONE|VEHICLE|LOCATION|ORGANIZATION|ACCOUNT>",
            "to":         "<entity value>",
            "to_type":    "<PERSON|PHONE|VEHICLE|LOCATION|ORGANIZATION|ACCOUNT>",
            "relation":   "<RELATION_TYPE>",
            "reasoning":  "<specific evidence that justifies this relation>",
            "evidence_level": "<DIRECT|INFERRED>",
            "confidence": <0.50 to 1.00>
        }
    ],
    "suspicious_flags": [
        {
            "flag":     "<flag_type>",
            "entities": ["<entity1>", "<entity2>"],
            "detail":   "<specific detail with numbers/dates from evidence>"
        }
    ],
    "summary": "<2-3 sentence paragraph summarizing the criminal network structure>"
}

If no relations are found, return:
{
    "relations": [],
    "suspicious_flags": [],
    "summary": "No significant cross-database connections found for the entities in this FIR."
}"""


# ================================================================
# EVIDENCE BUDGET
# ================================================================

# The observed Groq account rejected a request containing ~11.7K
# input tokens with an effective ITPM limit around 7K.
#
# Keep database evidence substantially below that limit so that
# system prompt, FIR context, instructions, and model output still
# have sufficient room.
#
# Approximation:
#     14,000 characters / 4 ~= 3,500 tokens
#
# This is a GLOBAL budget across the complete cross-database
# evidence section, not a per-entity budget.
MAX_EVIDENCE_CHARS = 14_000


# Evidence priority.
#
# Direct communication and financial records are generally stronger
# relationship evidence than generic location/social co-occurrence.
EVIDENCE_PRIORITY = (
    "contact",
    "bank",
    "crime",
    "surveillance",
    "social",
    "other_firs",
)


# Existing per-category safety caps are retained.
PER_CATEGORY_CAPS = {
    "contact": 10,
    "bank": 10,
    "crime": 5,
    "surveillance": 5,
    "social": 5,
    "other_firs": 5,
}


EVIDENCE_LABELS = {
    "contact": "CONTACT EVIDENCE",
    "bank": "BANK EVIDENCE",
    "crime": "PREVIOUS CRIME EVIDENCE",
    "surveillance": "SURVEILLANCE EVIDENCE",
    "social": "SOCIAL MEDIA EVIDENCE",
    "other_firs": "OTHER FIR EVIDENCE",
}


# ================================================================
# EVIDENCE SERIALIZATION
# ================================================================

def _serialize_evidence(hit) -> str:
    """
    Serialize one database hit into one complete prompt line.

    A complete record is always kept intact. We never slice a JSON
    record in the middle.
    """
    return f"- {json.dumps(hit, default=str, separators=(',', ':'))}"


def _collect_evidence_candidates(groq_payload: dict) -> list[dict]:
    """
    Collect all evidence records into a single ranked candidate list.

    Ranking uses:
        1. Evidence type priority
        2. Entity risk score
        3. Entity order
        4. Evidence order

    This allows strong/direct evidence to survive a global budget while
    preventing a high-volume low-value entity such as a LOCATION from
    consuming the entire prompt.
    """

    candidates = []

    for entity_index, entity in enumerate(
        groq_payload.get("entities", []),
        start=1,
    ):
        entity_type = entity.get("entity_type", "")
        entity_value = entity.get("entity_value", "")
        entity_score = float(entity.get("entity_score", 0) or 0)

        hits = entity.get("hits", {}) or {}

        for priority_index, evidence_type in enumerate(EVIDENCE_PRIORITY):
            raw_hits = hits.get(evidence_type, []) or []

            category_cap = PER_CATEGORY_CAPS.get(
                evidence_type,
                len(raw_hits),
            )

            for hit_index, hit in enumerate(
                raw_hits[:category_cap],
                start=1,
            ):
                serialized = _serialize_evidence(hit)

                candidates.append(
                    {
                        "entity_index": entity_index,
                        "entity_type": entity_type,
                        "entity_value": entity_value,
                        "entity_score": entity_score,
                        "evidence_type": evidence_type,
                        "priority_index": priority_index,
                        "hit_index": hit_index,
                        "text": serialized,
                    }
                )

    candidates.sort(
        key=lambda item: (
            item["priority_index"],
            -item["entity_score"],
            item["entity_index"],
            item["hit_index"],
        )
    )

    return candidates


# ================================================================
# BUDGETED EVIDENCE BUILDER
# ================================================================

def _build_budgeted_evidence(
    groq_payload: dict,
    max_chars: int = MAX_EVIDENCE_CHARS,
) -> list[str]:
    """
    Build the complete evidence section while respecting a global
    character budget.

    Important design rules:

    - Never split an individual database record.
    - Prefer direct evidence categories.
    - Give every entity an opportunity to contribute evidence.
    - Then use remaining budget for additional high-priority records.
    """

    entities = groq_payload.get("entities", [])

    if not entities or max_chars <= 0:
        return []

    candidates = _collect_evidence_candidates(groq_payload)

    if not candidates:
        return []

    selected = []
    selected_keys = set()
    used_chars = 0

    # ------------------------------------------------------------
    # PASS 1
    #
    # Give each entity its strongest available evidence.
    #
    # This prevents the first large/high-volume entity from consuming
    # the complete global budget.
    # ------------------------------------------------------------

    for entity_index in range(1, len(entities) + 1):

        entity_candidates = [
            candidate
            for candidate in candidates
            if candidate["entity_index"] == entity_index
        ]

        if not entity_candidates:
            continue

        candidate = entity_candidates[0]

        text = candidate["text"]

        # Account for newline between records.
        cost = len(text) + 1

        if used_chars + cost > max_chars:
            continue

        selected.append(candidate)
        selected_keys.add(
            (
                candidate["entity_index"],
                candidate["evidence_type"],
                candidate["hit_index"],
            )
        )
        used_chars += cost

    # ------------------------------------------------------------
    # PASS 2
    #
    # Fill remaining budget with the strongest remaining evidence.
    # ------------------------------------------------------------

    for candidate in candidates:

        key = (
            candidate["entity_index"],
            candidate["evidence_type"],
            candidate["hit_index"],
        )

        if key in selected_keys:
            continue

        text = candidate["text"]
        cost = len(text) + 1

        if used_chars + cost > max_chars:
            continue

        selected.append(candidate)
        selected_keys.add(key)
        used_chars += cost

        if used_chars >= max_chars:
            break

    # ------------------------------------------------------------
    # Sort selected records for readable prompt organization.
    # ------------------------------------------------------------

    selected.sort(
        key=lambda item: (
            item["entity_index"],
            item["priority_index"],
            item["hit_index"],
        )
    )

    # ------------------------------------------------------------
    # Convert records into the actual prompt.
    # ------------------------------------------------------------

    prompt_parts = []

    current_entity_index = None
    current_entity = None
    current_evidence_type = None

    for candidate in selected:

        entity_index = candidate["entity_index"]
        evidence_type = candidate["evidence_type"]

        # --------------------------------------------------------
        # Entity header
        # --------------------------------------------------------

        if entity_index != current_entity_index:

            if current_entity_index is not None:
                prompt_parts.extend([
                    "----------------------------------------",
                    "",
                ])

            current_entity_index = entity_index
            current_entity = entities[entity_index - 1]
            current_evidence_type = None

            entity_type = current_entity.get(
                "entity_type",
                "",
            )
            entity_value = current_entity.get(
                "entity_value",
                "",
            )
            entity_score = current_entity.get(
                "entity_score",
                0,
            )
            db_hit_count = current_entity.get(
                "db_hit_count",
                0,
            )

            prompt_parts.extend([
                f"ENTITY {entity_index}",
                f"Type: {entity_type}",
                f"Value: {entity_value}",
                f"Risk score: {entity_score}",
                f"Total database hits: {db_hit_count}",
                "",
            ])

        # --------------------------------------------------------
        # Evidence category header
        # --------------------------------------------------------

        if evidence_type != current_evidence_type:

            current_evidence_type = evidence_type

            prompt_parts.extend([
                EVIDENCE_LABELS[evidence_type] + ":",
            ])

        prompt_parts.append(candidate["text"])

    return prompt_parts


# ================================================================
# HUMAN PROMPT BUILDER
# ================================================================

def build_analysis_prompt(groq_payload):
    """
    Build the human analysis prompt from the cross-lookup payload.

    The FIR context is included separately from database evidence so
    the LLM understands what incident is being analyzed without
    treating the FIR description itself as relationship evidence.

    Cross-database evidence is subject to a GLOBAL evidence budget.
    """

    fir_id = groq_payload.get("fir_id")
    processed_at = groq_payload.get("processed_at")
    total_entities = groq_payload.get("total_entities", 0)
    fir_context = groq_payload.get("fir_context", "")

    prompt_parts = [
        "CRIMINAL NETWORK ANALYSIS REQUEST",
        "",
        f"FIR ID: {fir_id}",
        f"Analysis timestamp: {processed_at}",
        f"Total entities: {total_entities}",
        "",
        "========== FIR CONTEXT ==========",
    ]

    if fir_context:
        prompt_parts.extend([
            fir_context.strip(),
            "",
        ])
    else:
        prompt_parts.extend([
            "No FIR description/context was provided.",
            "",
        ])

    prompt_parts.extend([
        "IMPORTANT:",
        "- FIR context explains the incident being investigated.",
        "- FIR context is contextual information, not independent proof of a relationship.",
        "- Do not create a relationship unless the supplied evidence supports it.",
        "",
        "========== CROSS-DATABASE EVIDENCE ==========",
        "",
    ])

    evidence_parts = _build_budgeted_evidence(
        groq_payload,
        max_chars=MAX_EVIDENCE_CHARS,
    )

    if evidence_parts:
        prompt_parts.extend(evidence_parts)
        prompt_parts.extend([
            "",
            "NOTE:",
            "- Evidence shown above was selected from the cross-database results using a global size budget.",
            "- Absence of a displayed record does not mean that no record exists in the underlying database.",
            "- Use only the evidence actually shown above when forming a relationship.",
            "",
        ])
    else:
        prompt_parts.extend([
            "No cross-database evidence was available.",
            "",
        ])

    prompt_parts.extend([
        "========== ANALYSIS TASK ==========",
        "",
        "Analyze the supplied FIR context together with the supplied "
        "cross-database evidence.",
        "",
        "Identify relationships only when they are supported by the "
        "provided evidence.",
        "",
        "Distinguish between:",
        "1. Direct evidence-backed relationships.",
        "2. Reasonable but weaker inferred connections.",
        "3. Mere co-occurrence that is NOT sufficient to establish a relationship.",
        "",
        "A shared location alone does NOT prove that two people are associated.",
        "A shared organization, vehicle, location, or other attribute alone "
        "must not be treated as proof of a direct relationship.",
        "",
        "Every reported relationship must contain specific evidence in "
        "the reasoning field.",
        "",
        "Identify suspicious patterns only when the supplied evidence "
        "supports them.",
        "",
        "Return ONLY valid JSON using the required output schema.",
        "",
    ])

    return "\n".join(prompt_parts)


# ================================================================
# FULL MESSAGES BUILDER
# ================================================================

def build_messages(groq_payload: dict) -> list[dict]:
    """
    Build the complete messages list for the LLM API call.

    Returns:
        [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": <built human prompt>}
        ]

    Compatible with:
        - Groq API
        - OpenRouter API
        - LangChain ChatPromptTemplate
        - Direct Anthropic/OpenAI messages format
    """

    return [
        {
            "role": "system",
            "content": SYSTEM_PROMPT,
        },
        {
            "role": "user",
            "content": build_analysis_prompt(groq_payload),
        },
    ]


# ================================================================
# TOKEN ESTIMATOR
# ================================================================

def estimate_tokens(groq_payload: dict) -> dict:
    """
    Rough token estimate before sending to LLM.

    Uses the existing approximation:
        1 token ~= 4 characters

    This estimator reflects the actual budgeted prompt generated by
    build_analysis_prompt().
    """

    human = build_analysis_prompt(groq_payload)

    system_tokens = len(SYSTEM_PROMPT) // 4
    human_tokens = len(human) // 4
    total_tokens = system_tokens + human_tokens

    return {
        "system_tokens": system_tokens,
        "human_tokens": human_tokens,
        "total_estimated": total_tokens,
        "evidence_budget_chars": MAX_EVIDENCE_CHARS,
        "evidence_budget_tokens_est": MAX_EVIDENCE_CHARS // 4,
        "within_7k_limit": total_tokens < 7000,
        "within_8k_limit": total_tokens < 8000,
        "within_32k_limit": total_tokens < 32000,
    }


# ================================================================
# QUICK TEST
# ================================================================

if __name__ == "__main__":

    # Simulate what
    # cross_lookup_service.result_to_groq_payload()
    # returns.

    mock_payload = {
        "fir_id": 42,
        "total_entities": 2,
        "processed_at": "2026-09-03T10:30:00",
        "entities": [
            {
                "entity_type": "PERSON",
                "entity_value": "Rahul Sharma",
                "entity_score": 0.8750,
                "db_hit_count": 7,
                "hits": {
                    "contact": [
                        {
                            "caller_name": "Rahul Sharma",
                            "caller_phone": "9123456789",
                            "receiver_name": "Priya Nair",
                            "receiver_phone": "9876543211",
                            "call_timestamp": "2026-09-08 21:15:00",
                            "duration_seconds": 312,
                            "call_type": "outgoing",
                        }
                    ],
                    "bank": [
                        {
                            "sender_account_holder_name": "Rahul Sharma",
                            "receiver_account_holder_name": "Priya Nair",
                            "transaction_amount": 125000,
                            "transaction_date": "2026-09-09 11:00:00",
                            "transaction_type": "transfer",
                        }
                    ],
                    "crime": [
                        {
                            "offense": "Theft",
                            "offense_category": "property",
                            "case_status": "convicted",
                            "case_date": "2023-03-15",
                            "district": "Cuttack",
                        }
                    ],
                    "surveillance": [],
                    "social": [],
                    "other_firs": [],
                },
            },
            {
                "entity_type": "PERSON",
                "entity_value": "Priya Nair",
                "entity_score": 0.6200,
                "db_hit_count": 3,
                "hits": {
                    "contact": [],
                    "bank": [],
                    "crime": [],
                    "surveillance": [
                        {
                            "location": "Cuttack Railway Station",
                            "location_name": "Platform 2",
                            "observed_at": "2026-09-10 20:45:00",
                            "source_type": "CCTV",
                            "event_description": "Seen with unidentified male",
                        }
                    ],
                    "social": [],
                    "other_firs": [],
                },
            },
        ],
    }

    print("=" * 60)
    print("SYSTEM PROMPT")
    print("=" * 60)
    print(SYSTEM_PROMPT)

    print()
    print("=" * 60)
    print("HUMAN PROMPT")
    print("=" * 60)
    print(build_analysis_prompt(mock_payload))

    print()
    print("=" * 60)
    print("TOKEN ESTIMATE")
    print("=" * 60)

    estimate = estimate_tokens(mock_payload)

    for key, value in estimate.items():
        print(f"  {key}: {value}")