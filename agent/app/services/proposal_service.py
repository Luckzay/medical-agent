from __future__ import annotations

import hashlib
from collections.abc import Iterable

from app.models.proposal import (
    ConditionCell,
    ConditionValue,
    ControlGroup,
    ExperimentProposal,
    Hypothesis,
    MeasurementPlan,
    ProposalReview,
    ReviewIssue,
    ReviewStatus,
    RiskItem,
    SelectedCompound,
)
from app.models.run import ClaimEvidence, CompoundResult, Evidence


def _unique_existing(ids: Iterable[str], available: set[str]) -> list[str]:
    return list(dict.fromkeys(item for item in ids if item in available))


def _raw(value: str, *, literature: bool) -> ConditionValue:
    return ConditionValue(raw_text=value, parsed=False, from_literature=literature)


def generate_experiment_proposal(
    compounds: list[CompoundResult],
    claims: list[ClaimEvidence],
    evidence: list[Evidence],
    max_conditions: int,
) -> ExperimentProposal:
    """Build a deterministic proposal solely from serialized analysis artifacts."""
    if not compounds:
        raise ValueError("at least one scored compound is required")
    if max_conditions < 1:
        raise ValueError("max_conditions must be positive")

    available = {item.evidence_id for item in evidence}
    ranked = sorted(
        compounds,
        key=lambda item: (-item.candidate_score.total_score, item.compound_id),
    )
    candidates = [item for item in ranked if item.candidate_score.is_candidate]
    chosen = candidates or ranked[:1]
    selected: list[SelectedCompound] = []
    hypotheses: list[Hypothesis] = []
    claim_by_compound = {claim.claim_id.removeprefix("candidate:"): claim for claim in claims}
    for compound in chosen:
        references = _unique_existing(compound.evidence_ids, available)
        if not references:
            raise ValueError(f"compound '{compound.compound_id}' has no available evidence")
        selected.append(
            SelectedCompound(
                compound_id=compound.compound_id,
                name=compound.name,
                herb=compound.herb,
                candidate_score=compound.candidate_score.total_score,
                candidate_threshold=compound.candidate_score.candidate_threshold,
                is_candidate=compound.candidate_score.is_candidate,
                evidence_ids=references,
            )
        )
        claim = claim_by_compound.get(compound.compound_id)
        claim_refs = _unique_existing(claim.evidence_ids if claim else references, available)
        hypotheses.append(
            Hypothesis(
                hypothesis_id=f"hypothesis:{compound.compound_id}",
                statement=(
                    f"在证据所载或明确标记为探索性的条件下，筛查 {compound.name} "
                    "是否形成可重复检测的组装体。"
                ),
                basis=(
                    claim.basis
                    if claim is not None
                    else "基于当前候选评分和来源证据提出可证伪的组装筛查假设。"
                ),
                evidence_ids=claim_refs,
                claims_literature_support=False,
            )
        )

    cells: list[ConditionCell] = []
    seen: set[tuple[str | None, str | None, str | None]] = set()
    for item in evidence:
        if item.source_type != "literature" or not item.conditions:
            continue
        solvent = item.conditions.get("solvent_type")
        ph = item.conditions.get("ph")
        temperature = item.conditions.get("temperature")
        key = (solvent, ph, temperature)
        if not any(key) or key in seen:
            continue
        seen.add(key)
        cells.append(
            ConditionCell(
                condition_id=f"condition:{len(cells) + 1}",
                solvent=_raw(solvent, literature=True) if solvent else None,
                ph=_raw(ph, literature=True) if ph else None,
                temperature=_raw(temperature, literature=True) if temperature else None,
                concentration_or_ratio=None,
                assembly_method=None,
                source_type="literature",
                evidence_ids=[item.evidence_id],
                literature_supported=True,
            )
        )
        if len(cells) >= max_conditions:
            break

    risks: list[RiskItem] = []
    if not cells:
        fallback_evidence = selected[0].evidence_ids
        cells.append(
            ConditionCell(
                condition_id="condition:exploratory-baseline",
                solvent=_raw("水相（探索性基线；具体水质待人工批准）", literature=False),
                temperature=_raw("室温（探索性基线；未指定数值）", literature=False),
                source_type="exploratory_default",
                evidence_ids=fallback_evidence,
                literature_supported=False,
            )
        )
        risks.append(
            RiskItem(
                risk_id="risk:exploratory-default",
                severity="high",
                category="evidence_gap",
                description="未检索到可用文献条件，条件矩阵包含非文献支持的探索性基线。",
                mitigation="由研究人员补充原始文献、明确数值条件并批准后再执行实验。",
                evidence_ids=fallback_evidence,
            )
        )

    common_refs = list(dict.fromkeys(ref for item in selected for ref in item.evidence_ids))
    digest = hashlib.sha256("|".join(item.compound_id for item in selected).encode()).hexdigest()[
        :12
    ]
    return ExperimentProposal(
        proposal_id=f"proposal:{digest}",
        title="证据约束的候选组装筛查方案",
        selected_compounds=selected,
        hypotheses=hypotheses,
        condition_matrix=cells,
        measurement_plan=[
            MeasurementPlan(
                measurement_id="measurement:assembly-screen",
                endpoint="组装体粒径分布与形态的可重复性筛查",
                method="使用经人工确认可用的粒径或显微表征方法；不推断疗效",
                unit=None,
                raw_schedule_text="平行重复和采样时点由实验人员在执行前预注册",
                evidence_ids=common_refs,
            )
        ],
        controls=[
            ControlGroup(
                control_id="control:blank",
                control_type="blank",
                description="不加入候选化合物、其余经批准条件一致的空白对照。",
                evidence_ids=common_refs,
            )
        ],
        risks=risks,
        safety_disclaimer="本方案不构成临床、诊疗或人体用药建议；执行前须完成机构安全审查。",
        research_disclaimer=(
            "本方案仅用于科研假设与体外筛查设计，所有探索性条件、仪器参数和操作步骤须由"
            "合格研究人员核验并批准，不得将候选评分解释为疗效证据。"
        ),
    )


_CHECKED_RULES = [
    "references_exist",
    "literature_support_consistency",
    "condition_matrix_completeness",
    "blank_or_negative_control",
    "measurement_plan_present",
    "candidate_scores",
    "unparsed_conditions",
    "exploratory_defaults",
    "safety_disclaimer",
    "research_disclaimer",
]


def review_experiment_proposal(
    serialized_proposal: dict[str, object], available_evidence_ids: list[str]
) -> ProposalReview:
    """Review only the supplied serialization and evidence-ID allowlist."""
    proposal = ExperimentProposal.model_validate(serialized_proposal)
    available = set(available_evidence_ids)
    issues: list[ReviewIssue] = []

    def issue(
        severity: str, code: str, message: str, field_path: str, ids: list[str] | None = None
    ) -> None:
        issues.append(
            ReviewIssue.model_validate(
                {
                    "severity": severity,
                    "code": code,
                    "message": message,
                    "field_path": field_path,
                    "evidence_ids": ids or [],
                }
            )
        )

    referenced: list[tuple[str, list[str]]] = []
    referenced.extend(
        (f"selected_compounds.{index}.evidence_ids", item.evidence_ids)
        for index, item in enumerate(proposal.selected_compounds)
    )
    referenced.extend(
        (f"hypotheses.{index}.evidence_ids", item.evidence_ids)
        for index, item in enumerate(proposal.hypotheses)
    )
    referenced.extend(
        (f"condition_matrix.{index}.evidence_ids", item.evidence_ids)
        for index, item in enumerate(proposal.condition_matrix)
    )
    referenced.extend(
        (f"measurement_plan.{index}.evidence_ids", item.evidence_ids)
        for index, item in enumerate(proposal.measurement_plan)
    )
    referenced.extend(
        (f"controls.{index}.evidence_ids", item.evidence_ids)
        for index, item in enumerate(proposal.controls)
    )
    referenced.extend(
        (f"risks.{index}.evidence_ids", item.evidence_ids)
        for index, item in enumerate(proposal.risks)
    )
    for field_path, ids in referenced:
        missing = [item for item in ids if item not in available]
        if missing:
            issue(
                "critical",
                "missing_evidence_reference",
                "引用 ID 不在可用证据集合中。",
                field_path,
                missing,
            )

    for index, cell in enumerate(proposal.condition_matrix):
        path = f"condition_matrix.{index}"
        values = [
            cell.solvent,
            cell.ph,
            cell.temperature,
            cell.concentration_or_ratio,
            cell.assembly_method,
        ]
        if cell.literature_supported != (cell.source_type == "literature"):
            issue(
                "error",
                "literature_support_mismatch",
                "文献支持标记与来源类型不一致。",
                path,
                cell.evidence_ids,
            )
        if cell.literature_supported and any(
            value and not value.from_literature for value in values
        ):
            issue(
                "error",
                "literature_value_mismatch",
                "文献支持条件含非文献来源值。",
                path,
                cell.evidence_ids,
            )
        missing_core = [
            name
            for name, value in (
                ("solvent", cell.solvent),
                ("ph", cell.ph),
                ("temperature", cell.temperature),
            )
            if value is None
        ]
        if missing_core:
            issue(
                "warning",
                "incomplete_condition_cell",
                f"条件缺少：{', '.join(missing_core)}。",
                path,
                cell.evidence_ids,
            )
        if any(value is not None and not value.parsed for value in values):
            issue(
                "info",
                "unparsed_condition",
                "保留了未解析的原始条件文本；执行前需人工标准化。",
                path,
                cell.evidence_ids,
            )
        if cell.source_type == "exploratory_default":
            issue(
                "warning",
                "exploratory_default",
                "包含无文献条件支持的探索性默认值，不得自动批准。",
                path,
                cell.evidence_ids,
            )

    if not any(item.control_type in {"blank", "negative"} for item in proposal.controls):
        issue(
            "error", "missing_negative_or_blank_control", "至少需要一个阴性或空白对照。", "controls"
        )
    if not proposal.measurement_plan:
        issue("error", "missing_measurement_plan", "缺少测量计划。", "measurement_plan")
    for index, compound in enumerate(proposal.selected_compounds):
        if compound.candidate_score < compound.candidate_threshold or not compound.is_candidate:
            issue(
                "warning",
                "below_candidate_threshold",
                "所选成分未达到候选评分阈值。",
                f"selected_compounds.{index}",
                compound.evidence_ids,
            )
    if not proposal.safety_disclaimer.strip():
        issue("error", "missing_safety_disclaimer", "缺少安全免责声明。", "safety_disclaimer")
    if not proposal.research_disclaimer.strip():
        issue("error", "missing_research_disclaimer", "缺少科研免责声明。", "research_disclaimer")

    penalty = {"critical": 35, "error": 18, "warning": 7, "info": 0}
    score = max(0, 100 - sum(penalty[item.severity] for item in issues))
    status: ReviewStatus
    if any(item.severity == "critical" for item in issues) or score < 40:
        status = "rejected"
    elif any(item.severity in {"error", "warning"} for item in issues):
        status = "needs_revision"
    else:
        status = "approved"
    return ProposalReview(status=status, score=score, issues=issues, checked_rules=_CHECKED_RULES)
