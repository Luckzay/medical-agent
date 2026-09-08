from __future__ import annotations

import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import NotRequired, Protocol, TypedDict, cast

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph

from app.core.config import get_settings
from app.models.proposal import ExperimentProposal, ProposalReview
from app.models.run import (
    AnalysisResult,
    ClaimEvidence,
    CompoundResult,
    Evidence,
    LLMStatus,
    ToolingMetadata,
    WorkflowMetadata,
    WorkflowStatus,
    WorkflowStep,
)
from app.models.tooling import (
    CalculateDescriptorsOutput,
    DiscoverCompoundsOutput,
    NormalizeHerbsOutput,
    ScoreCandidatesOutput,
    SearchLiteratureOutput,
    ToolExecutionContext,
)
from app.services.analysis_service import AnalysisService
from app.services.builtin_tools import INTERNAL_TOOL_PERMISSIONS, build_tool_registry
from app.services.llm_proxy import LLMProxyClient
from app.services.tool_runtime import ToolRuntime

NodeHook = Callable[[str], None]


class WorkflowState(TypedDict):
    herbs: list[str]
    research_goal: NotRequired[str | None]
    normalized_herbs: NotRequired[list[str]]
    discovered: NotRequired[list[dict[str, object]]]
    compounds: NotRequired[list[dict[str, object]]]
    evidence: NotRequired[list[dict[str, object]]]
    claims: NotRequired[list[dict[str, object]]]
    retrieval_mode: NotRequired[str]
    retrieval_diagnostics: NotRequired[list[dict[str, object]]]
    proposal: NotRequired[dict[str, object]]
    proposal_review: NotRequired[dict[str, object]]
    unresolved_herbs: NotRequired[list[str]]
    online_failures: NotRequired[int]
    analysis_result: NotRequired[dict[str, object]]
    llm_summary: NotRequired[str | None]
    llm_status: NotRequired[str]
    steps: list[dict[str, object]]


class AnalysisWorkflow(Protocol):
    def invoke(
        self, run_id: str, herbs: list[str], research_goal: str | None = None
    ) -> AnalysisResult: ...

    def resume(self, run_id: str) -> AnalysisResult: ...

    def has_checkpoint(self, run_id: str) -> bool: ...

    def metadata(self, run_id: str, status: WorkflowStatus) -> WorkflowMetadata: ...

    def cancel(self, run_id: str) -> None: ...

    def clear(self) -> None: ...

    def close(self) -> None: ...


class LangGraphAnalysisWorkflow:
    """Seven-stage deterministic graph with durable, resumable per-run checkpoints."""

    def __init__(
        self,
        analysis: AnalysisService,
        checkpointer: BaseCheckpointSaver[str] | None = None,
        node_hook: NodeHook | None = None,
        checkpoint_path: str | Path | None = None,
        runtime: ToolRuntime | None = None,
        llm: LLMProxyClient | None = None,
    ) -> None:
        self._analysis = analysis
        self._runtime = runtime or ToolRuntime(
            build_tool_registry(analysis), get_settings().database_path
        )
        self._llm = llm or LLMProxyClient(get_settings())
        self._owns_runtime = runtime is None
        self._node_hook = node_hook
        self._owned_connection: sqlite3.Connection | None = None
        if checkpointer is None:
            path = Path(checkpoint_path or get_settings().checkpoint_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            connection = sqlite3.connect(path, check_same_thread=False, timeout=5.0)
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA busy_timeout=5000")
            self._owned_connection = connection
            self._checkpointer: BaseCheckpointSaver[str] = SqliteSaver(connection)
            self._checkpoint_backend = "sqlite"
        else:
            self._checkpointer = checkpointer
            self._checkpoint_backend = (
                "in_memory" if isinstance(checkpointer, InMemorySaver) else "external"
            )
        builder = StateGraph(WorkflowState)
        builder.add_node("normalize", self._normalize)
        builder.add_node("discover", self._discover)
        builder.add_node("chemistry", self._chemistry)
        builder.add_node("evidence", self._evidence)
        builder.add_node("proposal", self._proposal)
        builder.add_node("review", self._review)
        builder.add_node("finalize", self._finalize)
        builder.add_edge(START, "normalize")
        builder.add_edge("normalize", "discover")
        builder.add_edge("discover", "chemistry")
        builder.add_edge("chemistry", "evidence")
        builder.add_edge("evidence", "proposal")
        builder.add_edge("proposal", "review")
        builder.add_edge("review", "finalize")
        builder.add_edge("finalize", END)
        self._graph = builder.compile(checkpointer=self._checkpointer)

    @staticmethod
    def _config(run_id: str) -> RunnableConfig:
        return {"configurable": {"thread_id": run_id}}

    def _start(self, node: str) -> datetime:
        if self._node_hook is not None:
            self._node_hook(node)
        return datetime.now(UTC)

    @staticmethod
    def _step(node: str, started: datetime, detail: str) -> dict[str, object]:
        return cast(
            dict[str, object],
            WorkflowStep(
                node=node,
                status="completed",
                started_at=started,
                completed_at=datetime.now(UTC),
                detail=detail,
            ).model_dump(mode="json"),
        )

    @staticmethod
    def _run_id(config: RunnableConfig) -> str:
        thread_id = config.get("configurable", {}).get("thread_id")
        if not isinstance(thread_id, str):
            raise RuntimeError("LangGraph thread_id is missing")
        return thread_id

    def _tool_context(self, config: RunnableConfig, node: str) -> ToolExecutionContext:
        return ToolExecutionContext(
            run_id=self._run_id(config), node=node, permissions=INTERNAL_TOOL_PERMISSIONS
        )

    def _normalize(self, state: WorkflowState, config: RunnableConfig) -> dict[str, object]:
        started = self._start("normalize")
        output = NormalizeHerbsOutput.model_validate(
            self._runtime.execute(
                "normalize_herbs",
                {"herbs": state["herbs"]},
                self._tool_context(config, "normalize"),
            )
        )
        normalized = output.normalized_herbs
        return {
            "normalized_herbs": normalized,
            "steps": [
                *state["steps"],
                self._step("normalize", started, f"标准化 {len(normalized)} 味药材"),
            ],
        }

    def _discover(self, state: WorkflowState, config: RunnableConfig) -> dict[str, object]:
        started = self._start("discover")
        result = DiscoverCompoundsOutput.model_validate(
            self._runtime.execute(
                "discover_compounds",
                {"normalized_herbs": state["normalized_herbs"]},
                self._tool_context(config, "discover"),
            )
        )
        discovered = [item.model_dump(mode="json") for item in result.compounds]
        return {
            "discovered": discovered,
            "evidence": [item.model_dump(mode="json") for item in result.evidence],
            "unresolved_herbs": result.unresolved_herbs,
            "online_failures": result.online_failures,
            "steps": [
                *state["steps"],
                self._step("discover", started, f"发现 {len(discovered)} 个成分"),
            ],
        }

    def _chemistry(self, state: WorkflowState, config: RunnableConfig) -> dict[str, object]:
        started = self._start("chemistry")
        context = self._tool_context(config, "chemistry")
        described = CalculateDescriptorsOutput.model_validate(
            self._runtime.execute(
                "calculate_descriptors", {"compounds": state["discovered"]}, context
            )
        )
        scored = ScoreCandidatesOutput.model_validate(
            self._runtime.execute(
                "score_supramolecular_candidate",
                {"compounds": described.model_dump(mode="json")["compounds"]},
                context,
            )
        )
        compounds = [
            CompoundResult(
                **item.compound.model_dump(),
                descriptors=item.descriptors,
                candidate_score=item.candidate_score,
            )
            for item in scored.compounds
        ]
        return {
            "compounds": [item.model_dump(mode="json") for item in compounds],
            "steps": [
                *state["steps"],
                self._step("chemistry", started, f"完成 {len(compounds)} 个成分的化学计算"),
            ],
        }

    def _evidence(self, state: WorkflowState, config: RunnableConfig) -> dict[str, object]:
        started = self._start("evidence")
        compounds = [CompoundResult.model_validate(item) for item in state["compounds"]]
        output = SearchLiteratureOutput.model_validate(
            self._runtime.execute(
                "search_literature",
                {
                    "query": state.get("research_goal"),
                    "research_goal": state.get("research_goal"),
                    "herbs": state["normalized_herbs"],
                    "compounds": [item.name for item in compounds],
                    "smiles": [item.smiles for item in compounds if item.smiles],
                    "top_k": get_settings().evidence_top_k,
                    "retrieval_mode": get_settings().vector_mode,
                    "diagnostics": True,
                },
                self._tool_context(config, "evidence"),
            )
        )
        literature: list[Evidence] = []
        for hit in output.hits:
            evidence_id = f"literature:{hit.document_id}"
            literature.append(
                Evidence(
                    evidence_id=evidence_id,
                    source="TCM supramolecular literature dataset",
                    source_type="literature",
                    reference=hit.link_or_doi or f"source-row://{hit.source_row}",
                    title=hit.title,
                    link=hit.link_or_doi,
                    year=hit.year,
                    source_row=hit.source_row,
                    matched_fields=hit.matched_fields,
                    score=hit.final_score,
                    conditions=hit.conditions,
                )
            )
            hit_compounds = (hit.compounds or "").lower()
            for compound in compounds:
                names = [
                    part.strip().lower() for part in compound.name.replace("（", "(").split("(")
                ]
                if (compound.smiles and compound.smiles in hit.smiles) or any(
                    name and name in hit_compounds for name in names
                ):
                    compound.evidence_ids = list(
                        dict.fromkeys([*compound.evidence_ids, evidence_id])
                    )
        combined = [*state["evidence"], *(item.model_dump(mode="json") for item in literature)]
        claims = [
            ClaimEvidence(
                claim_id=f"candidate:{compound.compound_id}",
                claim_text=(
                    f"{compound.name} 的确定性候选规则得分为 "
                    f"{compound.candidate_score.total_score}。"
                ),
                claim_type="deterministic_candidate_score",
                evidence_ids=compound.evidence_ids,
                confidence=1.0,
                basis="本地种子来源与确定性规则计算；不表述为文献证明",
            )
            for compound in compounds
            if compound.evidence_ids
        ]
        return {
            "compounds": [item.model_dump(mode="json") for item in compounds],
            "evidence": combined,
            "claims": [item.model_dump(mode="json") for item in claims],
            "retrieval_mode": output.retrieval_mode,
            "retrieval_diagnostics": output.diagnostics,
            "steps": [
                *state["steps"],
                self._step("evidence", started, f"检索到 {len(literature)} 条文献证据"),
            ],
        }

    def _proposal(self, state: WorkflowState, config: RunnableConfig) -> dict[str, object]:
        started = self._start("proposal")
        proposal = ExperimentProposal.model_validate(
            self._runtime.execute(
                "generate_experiment_proposal",
                {
                    "compounds": state["compounds"],
                    "claims": state["claims"],
                    "evidence": state["evidence"],
                    "max_conditions": get_settings().proposal_max_conditions,
                },
                self._tool_context(config, "proposal"),
            )
        )
        return {
            "proposal": proposal.model_dump(mode="json"),
            "steps": [
                *state["steps"],
                self._step(
                    "proposal", started, f"生成 {len(proposal.condition_matrix)} 个条件单元"
                ),
            ],
        }

    def _review(self, state: WorkflowState, config: RunnableConfig) -> dict[str, object]:
        started = self._start("review")
        evidence = [Evidence.model_validate(item) for item in state["evidence"]]
        review = ProposalReview.model_validate(
            self._runtime.execute(
                "review_experiment_proposal",
                {
                    "proposal": state["proposal"],
                    "available_evidence_ids": [item.evidence_id for item in evidence],
                },
                self._tool_context(config, "review"),
            )
        )
        return {
            "proposal_review": review.model_dump(mode="json"),
            "steps": [
                *state["steps"],
                self._step("review", started, f"独立审查结果：{review.status}"),
            ],
        }

    def _finalize(self, state: WorkflowState, config: RunnableConfig) -> dict[str, object]:
        started = self._start("finalize")
        compounds = [CompoundResult.model_validate(item) for item in state["compounds"]]
        evidence = [Evidence.model_validate(item) for item in state["evidence"]]

        llm_summary = None
        llm_status = LLMStatus.DISABLED
        settings = get_settings()
        if settings.llm_mode != "disabled":
            system_prompt = (
                "你是一个专业的中药超分子化学研究员。请基于提供的实验发现、"
                "候选成分评分和文献证据，生成一段精炼的中文科研摘要。"
                "摘要应包含研究背景、核心发现（如关键候选成分及其评分理由）以及"
                "对后续实验的建议。"
            )
            max_score_compound = (
                max(compounds, key=lambda c: c.candidate_score.total_score).name
                if compounds
                else "N/A"
            )
            user_prompt = (
                f"研究目标: {state.get('research_goal', '未指定')}\n"
                f"涉及药材: {', '.join(state.get('normalized_herbs', []))}\n"
                f"发现成分数量: {len(compounds)}\n"
                f"候选评分最高成分: {max_score_compound}\n"
                f"文献证据条数: {len(evidence)}\n"
            )
            try:
                llm_summary = self._llm.chat(system_prompt, user_prompt)
                llm_status = LLMStatus.GENERATED
            except Exception as exc:
                if settings.llm_mode == "required":
                    raise exc
                llm_status = LLMStatus.DEGRADED
                llm_summary = None

        result = self._analysis.finalize(
            state["normalized_herbs"],
            compounds,
            evidence,
            state["unresolved_herbs"],
            state["online_failures"],
            llm_summary=llm_summary,
            llm_status=llm_status,
        )
        result.proposal = ExperimentProposal.model_validate(state["proposal"])
        result.proposal_review = ProposalReview.model_validate(state["proposal_review"])
        result.retrieval_mode = state.get("retrieval_mode")
        result.retrieval_diagnostics = state.get("retrieval_diagnostics", [])
        available_ids = {item.evidence_id for item in result.evidence}
        proposal_reference_groups = [
            *(item.evidence_ids for item in result.proposal.selected_compounds),
            *(item.evidence_ids for item in result.proposal.hypotheses),
            *(item.evidence_ids for item in result.proposal.condition_matrix),
            *(item.evidence_ids for item in result.proposal.measurement_plan),
            *(item.evidence_ids for item in result.proposal.controls),
            *(item.evidence_ids for item in result.proposal.risks),
        ]
        missing_ids = {
            evidence_id
            for group in proposal_reference_groups
            for evidence_id in group
            if evidence_id not in available_ids
        }
        if missing_ids:
            raise RuntimeError(f"proposal contains unavailable evidence IDs: {sorted(missing_ids)}")
        steps_data = [
            *state["steps"],
            self._step("finalize", started, "汇总分析结果与能力状态"),
        ]
        thread_id = self._run_id(config)
        audits = self._runtime.audits_for_run(thread_id)
        result.workflow = WorkflowMetadata(
            thread_id=thread_id,
            checkpoint_backend=self._checkpoint_backend,
            status=WorkflowStatus.COMPLETED,
            steps=[WorkflowStep.model_validate(item) for item in steps_data],
            tooling=ToolingMetadata(
                skills=[
                    "compound-discovery",
                    "molecular-analysis",
                    "literature-research",
                    "experiment-design",
                    "proposal-review",
                ],
                audit_ids=[audit.audit_id for audit in audits],
            ),
        )
        return {"analysis_result": result.model_dump(mode="json"), "steps": steps_data}

    def invoke(
        self, run_id: str, herbs: list[str], research_goal: str | None = None
    ) -> AnalysisResult:
        output = self._graph.invoke(
            WorkflowState(herbs=herbs, research_goal=research_goal, steps=[]),
            config=self._config(run_id),
        )
        return AnalysisResult.model_validate(output["analysis_result"])

    def resume(self, run_id: str) -> AnalysisResult:
        output = self._graph.invoke(None, config=self._config(run_id))
        return AnalysisResult.model_validate(output["analysis_result"])

    def has_checkpoint(self, run_id: str) -> bool:
        return self._checkpointer.get_tuple(self._config(run_id)) is not None

    def metadata(self, run_id: str, status: WorkflowStatus) -> WorkflowMetadata:
        snapshot = self._graph.get_state(self._config(run_id))
        values = cast(WorkflowState, snapshot.values)
        steps = [WorkflowStep.model_validate(item) for item in values.get("steps", [])]
        if status is WorkflowStatus.FAILED and snapshot.next:
            now = datetime.now(UTC)
            steps.append(
                WorkflowStep(
                    node=snapshot.next[0],
                    status="failed",
                    started_at=now,
                    completed_at=now,
                    detail="节点执行异常；已保留前序 checkpoint，可从此节点恢复",
                )
            )
        return WorkflowMetadata(
            thread_id=run_id,
            checkpoint_backend=self._checkpoint_backend,
            status=status,
            steps=steps,
        )

    def cancel(self, run_id: str) -> None:
        self.metadata(run_id, WorkflowStatus.CANCELLED)

    def clear(self) -> None:
        thread_ids = {
            str(item.config["configurable"]["thread_id"]) for item in self._checkpointer.list(None)
        }
        for thread_id in thread_ids:
            self._checkpointer.delete_thread(thread_id)

    def close(self) -> None:
        if self._owned_connection is not None:
            self._owned_connection.close()
            self._owned_connection = None
        if self._owns_runtime:
            self._runtime.close()
