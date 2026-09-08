from app.core.config import Settings
from app.models.run import MolecularDescriptors
from app.services.analysis_service import AnalysisService, normalize_herb, score_candidate


class UnavailableDescriptors:
    available = False

    def calculate(self, smiles: str) -> MolecularDescriptors:
        return MolecularDescriptors()


class FixedDescriptors:
    available = True

    def calculate(self, smiles: str) -> MolecularDescriptors:
        return MolecularDescriptors(
            molecular_weight=194.18,
            logp=1.5,
            tpsa=66.76,
            hbd=2,
            hba=4,
        )


class FailingPubChem:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def lookup(self, name: str) -> tuple[int, str, str] | None:
        self.calls.append(name)
        return None


class StubPubChem:
    def lookup(self, name: str) -> tuple[int, str, str] | None:
        return 123, "测试成分", "CC(=O)O"


def settings(*, offline_mode: bool) -> Settings:
    return Settings(
        internal_token="test-only-agent-token",
        offline_mode=offline_mode,
    )


def test_normalization_is_basic_deterministic_and_deduplicated() -> None:
    assert normalize_herb("  黃耆 ") == "黄芪"
    service = AnalysisService(settings(offline_mode=True), descriptors=UnavailableDescriptors())
    result = service.analyze([" 黄芪 ", "黄耆", "炙甘草", "甘草"])
    assert result.normalized_herbs == ["黄芪", "甘草"]
    assert result.summary.compound_count == 2


def test_all_required_seed_herbs_have_traceable_evidence() -> None:
    service = AnalysisService(settings(offline_mode=True), descriptors=UnavailableDescriptors())
    result = service.analyze(["黄芪", "当归", "甘草"])

    assert result.summary.compound_count == 3
    assert len(result.evidence) == 3
    evidence_ids = {item.evidence_id for item in result.evidence}
    assert all(set(compound.evidence_ids) <= evidence_ids for compound in result.compounds)
    assert all(item.reference.startswith("seed://") for item in result.evidence)


def test_missing_rdkit_keeps_descriptors_null_and_skips_descriptor_rules() -> None:
    service = AnalysisService(settings(offline_mode=True), descriptors=UnavailableDescriptors())
    result = service.analyze(["当归"])
    compound = result.compounds[0]

    assert result.capabilities["rdkit"].status == "degraded"
    assert compound.descriptors.model_dump() == {
        "molecular_weight": None,
        "logp": None,
        "tpsa": None,
        "hbd": None,
        "hba": None,
    }
    assert [rule.status for rule in compound.candidate_score.rules[:5]] == ["skipped"] * 5
    assert compound.candidate_score.total_score == 2
    assert not compound.candidate_score.is_candidate


def test_scoring_is_transparent_and_deterministic() -> None:
    descriptors = FixedDescriptors().calculate("COC1=CC=CC=C1O")
    first = score_candidate("COC1=CC=CC=C1O", descriptors)
    second = score_candidate("COC1=CC=CC=C1O", descriptors)

    assert first == second
    assert first.total_score == 10
    assert first.is_candidate
    assert all(rule.status == "hit" for rule in first.rules)


def test_offline_mode_never_calls_pubchem() -> None:
    pubchem = FailingPubChem()
    service = AnalysisService(
        settings(offline_mode=True),
        pubchem=pubchem,
        descriptors=UnavailableDescriptors(),
    )
    result = service.analyze(["未知药材"])

    assert pubchem.calls == []
    assert result.summary.unresolved_herbs == ["未知药材"]
    assert result.capabilities["pubchem"].status == "offline"


def test_unknown_herb_is_not_misused_as_pubchem_compound_query() -> None:
    pubchem = FailingPubChem()
    service = AnalysisService(
        settings(offline_mode=False),
        pubchem=pubchem,
        descriptors=UnavailableDescriptors(),
    )
    result = service.analyze(["未知药材"])

    assert pubchem.calls == []
    assert result.summary.unresolved_herbs == ["未知药材"]


def test_online_failure_does_not_fail_analysis() -> None:
    pubchem = FailingPubChem()
    service = AnalysisService(
        settings(offline_mode=False),
        pubchem=pubchem,
        descriptors=UnavailableDescriptors(),
    )
    result = service.analyze(["当归"])

    assert pubchem.calls == ["Ferulic acid"]
    assert len(result.compounds) == 1
    assert result.compounds[0].pubchem_cid is None
    assert result.summary.unresolved_herbs == []
    assert result.capabilities["pubchem"].status == "degraded"


def test_online_pubchem_result_retains_source() -> None:
    service = AnalysisService(
        settings(offline_mode=False),
        pubchem=StubPubChem(),
        descriptors=UnavailableDescriptors(),
    )
    result = service.analyze(["当归"])

    assert result.compounds[0].pubchem_cid == 123
    assert result.compounds[0].evidence_ids == ["seed:当归:ferulic-acid", "pubchem:123"]
    assert result.evidence[-1].reference.endswith("/123")


def test_claims_are_traceable_when_literature_is_not_invoked() -> None:
    analysis = AnalysisService(settings(offline_mode=True), descriptors=UnavailableDescriptors())
    result = analysis.analyze(["黄芪"])
    evidence_ids = {item.evidence_id for item in result.evidence}
    assert result.capabilities["literature_retrieval"].status == "degraded"
    assert result.claims
    assert all(claim.evidence_ids for claim in result.claims)
    assert all(set(claim.evidence_ids) <= evidence_ids for claim in result.claims)
    assert all("文献证明" not in claim.claim_text for claim in result.claims)
