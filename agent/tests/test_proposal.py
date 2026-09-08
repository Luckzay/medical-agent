from __future__ import annotations

from copy import deepcopy

import pytest
from pydantic import ValidationError

from app.models.proposal import ConditionValue
from app.models.run import (
    CandidateScore,
    ClaimEvidence,
    CompoundResult,
    Evidence,
    MolecularDescriptors,
    RuleHit,
)
from app.services.proposal_service import (
    generate_experiment_proposal,
    review_experiment_proposal,
)


def compound(*, candidate: bool = True) -> CompoundResult:
    score = 8 if candidate else 2
    return CompoundResult(
        compound_id="ferulic-acid",
        name="阿魏酸（Ferulic acid）",
        herb="当归",
        smiles="COC1=CC=CC=C1O",
        descriptors=MolecularDescriptors(),
        candidate_score=CandidateScore(
            rules=[
                RuleHit(
                    rule_id="deterministic",
                    description="fixture",
                    status="hit",
                    points=score,
                    observed="fixture",
                )
            ],
            total_score=score,
            candidate_threshold=6,
            is_candidate=candidate,
        ),
        evidence_ids=["seed:ferulic"],
    )


def artifacts(
    *, literature_conditions: dict[str, str | None] | None = None
) -> tuple[list[CompoundResult], list[ClaimEvidence], list[Evidence]]:
    compounds = [compound()]
    claims = [
        ClaimEvidence(
            claim_id="candidate:ferulic-acid",
            claim_text="确定性评分为 8。",
            claim_type="deterministic_candidate_score",
            evidence_ids=["seed:ferulic"],
            confidence=1.0,
            basis="确定性计算",
        )
    ]
    evidence = [
        Evidence(
            evidence_id="seed:ferulic",
            source="seed",
            source_type="local_seed",
            reference="seed://ferulic",
        )
    ]
    if literature_conditions is not None:
        evidence.append(
            Evidence(
                evidence_id="literature:1",
                source="dataset",
                source_type="literature",
                reference="doi:fixture",
                conditions=literature_conditions,
            )
        )
    return compounds, claims, evidence


def test_literature_conditions_are_raw_deduplicated_and_do_not_invent_concentration() -> None:
    compounds, claims, evidence = artifacts(
        literature_conditions={
            "solvent_type": "PBS",
            "ph": "pH 7.4",
            "temperature": "25 ± 1 °C",
        }
    )
    proposal = generate_experiment_proposal(compounds, claims, evidence, max_conditions=12)
    cell = proposal.condition_matrix[0]

    assert cell.source_type == "literature"
    assert cell.evidence_ids == ["literature:1"]
    assert cell.temperature is not None and cell.temperature.raw_text == "25 ± 1 °C"
    assert cell.temperature.value is None and not cell.temperature.parsed
    assert cell.concentration_or_ratio is None
    assert all(item.evidence_ids for item in proposal.hypotheses)
    assert all(item.evidence_ids for item in proposal.condition_matrix)


def test_exploratory_fallback_is_explicit_and_needs_revision() -> None:
    compounds, claims, evidence = artifacts()
    proposal = generate_experiment_proposal(compounds, claims, evidence, max_conditions=2)
    review = review_experiment_proposal(
        proposal.model_dump(mode="json"), [item.evidence_id for item in evidence]
    )

    assert proposal.condition_matrix[0].source_type == "exploratory_default"
    assert proposal.condition_matrix[0].concentration_or_ratio is None
    assert proposal.risks[0].category == "evidence_gap"
    assert review.status == "needs_revision"
    assert "exploratory_default" in {item.code for item in review.issues}


def test_unparsed_text_cannot_be_disguised_as_numeric() -> None:
    with pytest.raises(ValidationError):
        ConditionValue(
            raw_text="approximately warm",
            value=25.0,
            unit="°C",
            parsed=False,
            from_literature=True,
        )


def test_reviewer_finds_missing_reference_control_and_measurement() -> None:
    compounds, claims, evidence = artifacts(
        literature_conditions={"solvent_type": "water", "ph": "7", "temperature": "25 °C"}
    )
    proposal = generate_experiment_proposal(compounds, claims, evidence, max_conditions=12)
    payload = deepcopy(proposal.model_dump(mode="json"))
    payload["hypotheses"][0]["evidence_ids"] = ["missing:1"]
    payload["controls"] = []
    payload["measurement_plan"] = []

    review = review_experiment_proposal(payload, [item.evidence_id for item in evidence])
    codes = {item.code for item in review.issues}
    assert review.status in {"needs_revision", "rejected"}
    assert {
        "missing_evidence_reference",
        "missing_negative_or_blank_control",
        "missing_measurement_plan",
    } <= codes


def test_reviewer_flags_below_threshold_candidate() -> None:
    compounds, claims, evidence = artifacts()
    compounds[0] = compound(candidate=False)
    proposal = generate_experiment_proposal(compounds, claims, evidence, max_conditions=1)
    review = review_experiment_proposal(
        proposal.model_dump(mode="json"), [item.evidence_id for item in evidence]
    )
    assert "below_candidate_threshold" in {item.code for item in review.issues}
