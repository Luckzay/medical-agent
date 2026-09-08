from __future__ import annotations

import httpx

from app.core.config import get_settings
from app.models.evidence import LiteratureSearchInput
from app.models.knowledge import OwnershipScope
from app.models.proposal import ExperimentProposal, ProposalReview
from app.models.tooling import (
    CalculateDescriptorsInput,
    CalculateDescriptorsOutput,
    DescribedCompound,
    DiscoverCompoundsInput,
    DiscoverCompoundsOutput,
    DiscoveredCompoundModel,
    GenerateExperimentProposalInput,
    NormalizeHerbsInput,
    NormalizeHerbsOutput,
    RetryPolicy,
    ReviewExperimentProposalInput,
    ScoreCandidatesInput,
    ScoreCandidatesOutput,
    ScoredCompound,
    SearchLiteratureInput,
    SearchLiteratureOutput,
    SearchMedicalKnowledgeInput,
    SearchMedicalKnowledgeOutput,
    SkillDefinition,
    ToolDefinition,
)
from app.services.analysis_service import AnalysisService
from app.services.evidence_retrieval import EvidenceRetrievalService, get_retrieval_service
from app.services.evidence_store import EvidenceStore
from app.services.knowledge_repository import SQLiteCanonicalRepository
from app.services.proposal_service import generate_experiment_proposal, review_experiment_proposal
from app.services.tool_registry import ToolRegistry

TOOL_VERSION = "1.3.0"
INTERNAL_TOOL_PERMISSIONS = frozenset(
    {
        "herbs:normalize",
        "compounds:discover",
        "chemistry:calculate",
        "candidates:score",
        "evidence:search",
        "knowledge:search",
        "proposal:generate",
        "proposal:review",
    }
)
MCP_TOOL_PERMISSIONS = INTERNAL_TOOL_PERMISSIONS


def build_tool_registry(
    analysis: AnalysisService, evidence_store: EvidenceStore | None = None
) -> ToolRegistry:
    registry = ToolRegistry()
    settings = get_settings()
    retrieval = (
        EvidenceRetrievalService(
            settings,
            evidence_store,
            SQLiteCanonicalRepository(settings.canonical_database_path),
        )
        if evidence_store is not None
        else get_retrieval_service(settings)
    )

    def normalize(request: NormalizeHerbsInput) -> NormalizeHerbsOutput:
        return NormalizeHerbsOutput(normalized_herbs=analysis.normalize(request.herbs))

    def discover(request: DiscoverCompoundsInput) -> DiscoverCompoundsOutput:
        result = analysis.discover(request.normalized_herbs)
        return DiscoverCompoundsOutput(
            compounds=[
                DiscoveredCompoundModel(
                    compound_id=item.compound_id,
                    name=item.name,
                    herb=item.herb,
                    smiles=item.smiles,
                    pubchem_cid=item.pubchem_cid,
                    evidence_ids=item.evidence_ids,
                )
                for item in result.compounds
            ],
            evidence=result.evidence,
            unresolved_herbs=result.unresolved_herbs,
            online_failures=result.online_failures,
        )

    def descriptors(request: CalculateDescriptorsInput) -> CalculateDescriptorsOutput:
        return CalculateDescriptorsOutput(
            compounds=[
                DescribedCompound(
                    compound=item,
                    descriptors=analysis.calculate_descriptors(item.smiles),
                )
                for item in request.compounds
            ]
        )

    def score(request: ScoreCandidatesInput) -> ScoreCandidatesOutput:
        return ScoreCandidatesOutput(
            compounds=[
                ScoredCompound(
                    compound=item.compound,
                    descriptors=item.descriptors,
                    candidate_score=analysis.score(item.compound.smiles, item.descriptors),
                )
                for item in request.compounds
            ]
        )

    def search_literature(request: SearchLiteratureInput) -> SearchLiteratureOutput:
        return retrieval.search(
            LiteratureSearchInput.model_validate(request.model_dump()),
            trusted_scope=OwnershipScope(
                tenant_id=settings.evidence_tenant_id,
                project_id=settings.evidence_project_id,
            ),
        )

    def search_medical_knowledge(
        request: SearchMedicalKnowledgeInput,
    ) -> SearchMedicalKnowledgeOutput:
        response = httpx.post(
            settings.knowledge_api_url,
            json=request.model_dump(mode="json"),
            headers={"X-Agent-Token": settings.internal_token},
            timeout=settings.knowledge_timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        if isinstance(payload, list):
            payload = {"results": payload}
        return SearchMedicalKnowledgeOutput.model_validate(payload)

    def generate_proposal(request: GenerateExperimentProposalInput) -> ExperimentProposal:
        return generate_experiment_proposal(
            request.compounds, request.claims, request.evidence, request.max_conditions
        )

    def review_proposal(request: ReviewExperimentProposalInput) -> ProposalReview:
        return review_experiment_proposal(
            request.proposal.model_dump(mode="json"), request.available_evidence_ids
        )

    registry.register_tool(
        ToolDefinition[NormalizeHerbsInput, NormalizeHerbsOutput](
            name="normalize_herbs",
            version=TOOL_VERSION,
            description="标准化、去重中药材名称。",
            input_model=NormalizeHerbsInput,
            output_model=NormalizeHerbsOutput,
            required_permissions=frozenset({"herbs:normalize"}),
            handler=normalize,
        )
    )
    registry.register_tool(
        ToolDefinition[DiscoverCompoundsInput, DiscoverCompoundsOutput](
            name="discover_compounds",
            version=TOOL_VERSION,
            description="从确定性种子库发现成分，并按配置可选补全 PubChem 证据。",
            input_model=DiscoverCompoundsInput,
            output_model=DiscoverCompoundsOutput,
            required_permissions=frozenset({"compounds:discover"}),
            timeout_seconds=10.0,
            retry_policy=RetryPolicy(max_retries=1),
            handler=discover,
        )
    )
    registry.register_tool(
        ToolDefinition[CalculateDescriptorsInput, CalculateDescriptorsOutput](
            name="calculate_descriptors",
            version=TOOL_VERSION,
            description="批量计算分子描述符；RDKit 不可用时返回空描述符。",
            input_model=CalculateDescriptorsInput,
            output_model=CalculateDescriptorsOutput,
            required_permissions=frozenset({"chemistry:calculate"}),
            handler=descriptors,
        )
    )
    registry.register_tool(
        ToolDefinition[ScoreCandidatesInput, ScoreCandidatesOutput](
            name="score_supramolecular_candidate",
            version=TOOL_VERSION,
            description="按确定性规则批量评分超分子候选成分。",
            input_model=ScoreCandidatesInput,
            output_model=ScoreCandidatesOutput,
            required_permissions=frozenset({"candidates:score"}),
            handler=score,
        )
    )

    registry.register_tool(
        ToolDefinition[SearchLiteratureInput, SearchLiteratureOutput](
            name="search_literature",
            version=TOOL_VERSION,
            description="离线检索可追溯的超分子中药文献证据。",
            input_model=SearchLiteratureInput,
            output_model=SearchLiteratureOutput,
            required_permissions=frozenset({"evidence:search"}),
            timeout_seconds=10.0,
            retry_policy=RetryPolicy(max_retries=0),
            handler=search_literature,
        )
    )
    registry.register_tool(
        ToolDefinition[SearchMedicalKnowledgeInput, SearchMedicalKnowledgeOutput](
            name="search_medical_knowledge",
            version=TOOL_VERSION,
            description="检索业务数据库中的医学知识，返回可引用的只读检索结果。",
            input_model=SearchMedicalKnowledgeInput,
            output_model=SearchMedicalKnowledgeOutput,
            required_permissions=frozenset({"knowledge:search"}),
            timeout_seconds=10.0,
            retry_policy=RetryPolicy(max_retries=1),
            handler=search_medical_knowledge,
        )
    )
    registry.register_tool(
        ToolDefinition[GenerateExperimentProposalInput, ExperimentProposal](
            name="generate_experiment_proposal",
            version=TOOL_VERSION,
            description="仅基于评分成分、声明和证据生成确定性的实验方案。",
            input_model=GenerateExperimentProposalInput,
            output_model=ExperimentProposal,
            required_permissions=frozenset({"proposal:generate"}),
            handler=generate_proposal,
        )
    )
    registry.register_tool(
        ToolDefinition[ReviewExperimentProposalInput, ProposalReview](
            name="review_experiment_proposal",
            version=TOOL_VERSION,
            description="独立审查序列化实验方案及其证据引用。",
            input_model=ReviewExperimentProposalInput,
            output_model=ProposalReview,
            required_permissions=frozenset({"proposal:review"}),
            handler=review_proposal,
        )
    )

    registry.register_skill(
        SkillDefinition(
            name="literature-research",
            version=TOOL_VERSION,
            description="离线混合检索真实文献数据并返回来源定位。",
            tool_names=("search_literature",),
            context_policy={
                "offline_network": "offline",
                "evidence_required": True,
                "max_results": 100,
            },
        )
    )
    registry.register_skill(
        SkillDefinition(
            name="compound-discovery",
            version=TOOL_VERSION,
            description="药材标准化与可追溯成分发现。",
            tool_names=("normalize_herbs", "discover_compounds"),
            context_policy={
                "offline_network": "respects_settings",
                "evidence_required": True,
                "max_compounds": 100,
            },
        )
    )
    registry.register_skill(
        SkillDefinition(
            name="molecular-analysis",
            version=TOOL_VERSION,
            description="描述符计算与确定性候选评分。",
            tool_names=("calculate_descriptors", "score_supramolecular_candidate"),
            context_policy={
                "offline_network": "offline",
                "evidence_required": False,
                "max_compounds": 100,
            },
        )
    )
    registry.register_skill(
        SkillDefinition(
            name="experiment-design",
            version=TOOL_VERSION,
            description="基于当前候选、声明和证据生成受约束的确定性实验方案。",
            tool_names=("generate_experiment_proposal",),
            context_policy={
                "offline_network": "offline",
                "evidence_required": True,
                "human_approval_required": True,
                "max_conditions": 100,
            },
        )
    )
    registry.register_skill(
        SkillDefinition(
            name="proposal-review",
            version=TOOL_VERSION,
            description="生成并独立审查证据约束的实验方案。",
            tool_names=(
                "generate_experiment_proposal",
                "review_experiment_proposal",
            ),
            context_policy={
                "offline_network": "offline",
                "evidence_required": True,
                "human_approval_required": True,
                "max_compounds": 100,
            },
        )
    )
    return registry
