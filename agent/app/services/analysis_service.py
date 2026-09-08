from __future__ import annotations

import importlib
import unicodedata
from dataclasses import dataclass
from typing import Any, Protocol, cast
from urllib.parse import quote

import httpx

from app.core.config import Settings
from app.models.run import (
    AnalysisResult,
    AnalysisSummary,
    CandidateScore,
    Capability,
    ClaimEvidence,
    CompoundResult,
    Evidence,
    LLMStatus,
    MolecularDescriptors,
    RuleHit,
)

_SCHEMA_VERSION = "2.0"
_CANDIDATE_THRESHOLD = 6


@dataclass(frozen=True)
class SeedCompound:
    compound_id: str
    name: str
    lookup_name: str
    smiles: str
    source: str
    reference: str


_SEED_DATA: dict[str, tuple[SeedCompound, ...]] = {
    "黄芪": (
        SeedCompound(
            compound_id="astragaloside-iv",
            name="黄芪甲苷（Astragaloside IV）",
            lookup_name="Astragaloside IV",
            smiles="CC1OC(OC2C(CO)OC(OC3CCC4(C)C(CCC5(C)C4CC=C4C6(C)CCC(OC7OC(CO)C(O)C(O)C7O)C(C)(C)C6CCC45C)C3(C)CO)C(O)C2O)C(O)C1O",
            source="本地确定性种子库",
            reference="seed://tcm/v1/huangqi/astragaloside-iv",
        ),
    ),
    "当归": (
        SeedCompound(
            compound_id="ferulic-acid",
            name="阿魏酸（Ferulic acid）",
            lookup_name="Ferulic acid",
            smiles="COC1=C(C=CC(=C1)C=CC(=O)O)O",
            source="本地确定性种子库",
            reference="seed://tcm/v1/danggui/ferulic-acid",
        ),
    ),
    "甘草": (
        SeedCompound(
            compound_id="glycyrrhizic-acid",
            name="甘草酸（Glycyrrhizic acid）",
            lookup_name="Glycyrrhizic acid",
            smiles="CC1(C2CCC3(C(C2(CCC1O)C)CCC4=CC(=O)CCC34C)C)C(=O)OCC5OC(OC6C(C(C(OC6C(=O)O)OC7C(C(C(OC7C(=O)O)O)O)O)O)O)C(C5O)O",
            source="本地确定性种子库",
            reference="seed://tcm/v1/gancao/glycyrrhizic-acid",
        ),
    ),
}

_ALIASES = {"黃耆": "黄芪", "黄耆": "黄芪", "炙甘草": "甘草", "生甘草": "甘草"}


class PubChemLookup(Protocol):
    def lookup(self, name: str) -> tuple[int, str, str] | None: ...


class PubChemClient:
    """Small, failure-tolerant PUG REST client."""

    def __init__(self, timeout_seconds: float) -> None:
        self._timeout = httpx.Timeout(timeout_seconds)

    def lookup(self, name: str) -> tuple[int, str, str] | None:
        url = (
            "https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/"
            f"{quote(name, safe='')}/property/CanonicalSMILES/JSON"
        )
        try:
            response = httpx.get(url, timeout=self._timeout, follow_redirects=True)
            response.raise_for_status()
            payload = cast(dict[str, object], response.json())
            table = payload.get("PropertyTable")
            if not isinstance(table, dict):
                return None
            properties = table.get("Properties")
            if not isinstance(properties, list) or not properties:
                return None
            first = properties[0]
            if not isinstance(first, dict):
                return None
            cid = first.get("CID")
            smiles = first.get("ConnectivitySMILES", first.get("CanonicalSMILES"))
            if not isinstance(cid, int) or not isinstance(smiles, str):
                return None
            return cid, name, smiles
        except (httpx.HTTPError, ValueError, TypeError):
            return None


class DescriptorProvider(Protocol):
    @property
    def available(self) -> bool: ...

    def calculate(self, smiles: str) -> MolecularDescriptors: ...


class DescriptorCalculator:
    """Optional RDKit facade; import or molecule failures produce only nulls."""

    def __init__(self) -> None:
        self._chem: Any | None = None
        self._descriptors: Any | None = None
        self._lipinski: Any | None = None
        try:
            self._chem = importlib.import_module("rdkit.Chem")
            self._descriptors = importlib.import_module("rdkit.Chem.Descriptors")
            self._lipinski = importlib.import_module("rdkit.Chem.Lipinski")
        except (ImportError, OSError):
            self._chem = None
            self._descriptors = None
            self._lipinski = None

    @property
    def available(self) -> bool:
        return all(module is not None for module in (self._chem, self._descriptors, self._lipinski))

    def calculate(self, smiles: str) -> MolecularDescriptors:
        chem = self._chem
        descriptors = self._descriptors
        lipinski = self._lipinski
        if chem is None or descriptors is None or lipinski is None:
            return MolecularDescriptors()
        try:
            molecule = chem.MolFromSmiles(smiles)
            if molecule is None:
                return MolecularDescriptors()
            return MolecularDescriptors(
                molecular_weight=round(float(descriptors.MolWt(molecule)), 4),
                logp=round(float(descriptors.MolLogP(molecule)), 4),
                tpsa=round(float(descriptors.TPSA(molecule)), 4),
                hbd=int(lipinski.NumHDonors(molecule)),
                hba=int(lipinski.NumHAcceptors(molecule)),
            )
        except (AttributeError, TypeError, ValueError, RuntimeError):
            return MolecularDescriptors()


def normalize_herb(name: str) -> str:
    normalized = "".join(unicodedata.normalize("NFKC", name).split())
    return _ALIASES.get(normalized, normalized)


def _numeric_rule(
    rule_id: str,
    description: str,
    observed: float | int | None,
    predicate: bool | None,
    points: int,
) -> RuleHit:
    if observed is None or predicate is None:
        return RuleHit(
            rule_id=rule_id,
            description=description,
            status="skipped",
            points=0,
            observed=None,
        )
    return RuleHit(
        rule_id=rule_id,
        description=description,
        status="hit" if predicate else "miss",
        points=points if predicate else 0,
        observed=observed,
    )


def score_candidate(smiles: str | None, descriptors: MolecularDescriptors) -> CandidateScore:
    mw = descriptors.molecular_weight
    logp = descriptors.logp
    tpsa = descriptors.tpsa
    hbd = descriptors.hbd
    hba = descriptors.hba
    rules = [
        _numeric_rule(
            "mw-window",
            "150 ≤ molecular_weight ≤ 800",
            mw,
            None if mw is None else 150 <= mw <= 800,
            2,
        ),
        _numeric_rule(
            "logp-window", "-1 ≤ logp ≤ 6", logp, None if logp is None else -1 <= logp <= 6, 2
        ),
        _numeric_rule(
            "tpsa-window", "20 ≤ tpsa ≤ 180", tpsa, None if tpsa is None else 20 <= tpsa <= 180, 2
        ),
        _numeric_rule("hbd", "hbd ≥ 1", hbd, None if hbd is None else hbd >= 1, 1),
        _numeric_rule("hba", "hba ≥ 2", hba, None if hba is None else hba >= 2, 1),
    ]
    if smiles is None:
        rules.extend(
            [
                RuleHit(
                    rule_id="cyclic-scaffold",
                    description="SMILES contains a ring closure",
                    status="skipped",
                    points=0,
                    observed=None,
                ),
                RuleHit(
                    rule_id="heteroatom",
                    description="SMILES contains O, N, or S",
                    status="skipped",
                    points=0,
                    observed=None,
                ),
            ]
        )
    else:
        has_ring = any(character.isdigit() for character in smiles)
        has_heteroatom = any(character in smiles for character in ("O", "N", "S"))
        rules.extend(
            [
                RuleHit(
                    rule_id="cyclic-scaffold",
                    description="SMILES contains a ring closure",
                    status="hit" if has_ring else "miss",
                    points=1 if has_ring else 0,
                    observed=str(has_ring).lower(),
                ),
                RuleHit(
                    rule_id="heteroatom",
                    description="SMILES contains O, N, or S",
                    status="hit" if has_heteroatom else "miss",
                    points=1 if has_heteroatom else 0,
                    observed=str(has_heteroatom).lower(),
                ),
            ]
        )
    total = sum(rule.points for rule in rules)
    return CandidateScore(
        rules=rules,
        total_score=total,
        candidate_threshold=_CANDIDATE_THRESHOLD,
        is_candidate=total >= _CANDIDATE_THRESHOLD,
    )


@dataclass(frozen=True)
class DiscoveredCompound:
    compound_id: str
    name: str
    herb: str
    smiles: str
    pubchem_cid: int | None
    evidence_ids: list[str]


@dataclass(frozen=True)
class DiscoveryResult:
    compounds: list[DiscoveredCompound]
    evidence: list[Evidence]
    unresolved_herbs: list[str]
    online_failures: int


class AnalysisService:
    def __init__(
        self,
        settings: Settings,
        pubchem: PubChemLookup | None = None,
        descriptors: DescriptorProvider | None = None,
    ) -> None:
        self._settings = settings
        self._pubchem = pubchem or PubChemClient(settings.pubchem_timeout_seconds)
        self._descriptors = descriptors or DescriptorCalculator()

    def normalize(self, herbs: list[str]) -> list[str]:
        normalized = list(dict.fromkeys(normalize_herb(herb) for herb in herbs))
        return [herb for herb in normalized if herb]

    def discover(self, normalized: list[str]) -> DiscoveryResult:
        compounds: list[DiscoveredCompound] = []
        evidence: list[Evidence] = []
        unresolved: list[str] = []
        online_failures = 0
        for herb in normalized:
            seeds = _SEED_DATA.get(herb)
            if seeds is None:
                unresolved.append(herb)
                continue
            for seed in seeds:
                seed_evidence_id = f"seed:{herb}:{seed.compound_id}"
                evidence.append(
                    Evidence(
                        evidence_id=seed_evidence_id,
                        source=seed.source,
                        source_type="local_seed",
                        reference=seed.reference,
                    )
                )
                smiles = seed.smiles
                cid: int | None = None
                evidence_ids = [seed_evidence_id]
                if not self._settings.offline_mode:
                    online = self._pubchem.lookup(seed.lookup_name)
                    if online is None:
                        online_failures += 1
                    else:
                        cid, _, smiles = online
                        pubchem_evidence_id = f"pubchem:{cid}"
                        evidence.append(
                            Evidence(
                                evidence_id=pubchem_evidence_id,
                                source="PubChem PUG REST",
                                source_type="online_database",
                                reference=f"https://pubchem.ncbi.nlm.nih.gov/compound/{cid}",
                            )
                        )
                        evidence_ids.append(pubchem_evidence_id)
                compounds.append(
                    DiscoveredCompound(
                        compound_id=seed.compound_id,
                        name=seed.name,
                        herb=herb,
                        smiles=smiles,
                        pubchem_cid=cid,
                        evidence_ids=evidence_ids,
                    )
                )
        return DiscoveryResult(compounds, evidence, unresolved, online_failures)

    def calculate_descriptors(self, smiles: str) -> MolecularDescriptors:
        """Single deterministic descriptor seam used by registered tools."""
        return self._descriptors.calculate(smiles)

    def score(self, smiles: str | None, descriptors: MolecularDescriptors) -> CandidateScore:
        """Single deterministic scoring seam used by registered tools."""
        return score_candidate(smiles, descriptors)

    def chemistry(self, discovered: list[DiscoveredCompound]) -> list[CompoundResult]:
        return [
            self._compound(
                item.compound_id,
                item.name,
                item.herb,
                item.smiles,
                item.pubchem_cid,
                item.evidence_ids,
            )
            for item in discovered
        ]

    def finalize(
        self,
        normalized: list[str],
        compounds: list[CompoundResult],
        evidence: list[Evidence],
        unresolved: list[str],
        online_failures: int,
        llm_summary: str | None = None,
        llm_status: LLMStatus = LLMStatus.DISABLED,
    ) -> AnalysisResult:
        candidate_count = sum(compound.candidate_score.is_candidate for compound in compounds)
        if self._settings.offline_mode:
            pubchem = Capability(status="offline", detail="offline_mode=true；未执行网络请求")
        elif online_failures:
            pubchem = Capability(
                status="degraded", detail=f"{online_failures} 个名称未查询到；分析已继续"
            )
        else:
            pubchem = Capability(status="available", detail="在线补全已启用")
        literature_count = sum(item.source_type == "literature" for item in evidence)
        literature_capability = Capability(
            status="available" if literature_count else "degraded",
            detail=(
                f"离线索引召回 {literature_count} 条文献证据"
                if literature_count
                else "离线索引未召回文献；结论仅引用种子或确定性计算证据"
            ),
        )
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
        return AnalysisResult(
            schema_version=_SCHEMA_VERSION,
            normalized_herbs=normalized,
            compounds=compounds,
            summary=AnalysisSummary(
                herb_count=len(normalized),
                compound_count=len(compounds),
                candidate_count=candidate_count,
                unresolved_herbs=unresolved,
            ),
            capabilities={
                "rdkit": Capability(
                    status="available" if self._descriptors.available else "degraded",
                    detail="RDKit 描述符计算可用"
                    if self._descriptors.available
                    else "RDKit 未安装；描述符保持 null，未进行推测",
                ),
                "pubchem": pubchem,
                "literature_retrieval": literature_capability,
            },
            evidence=evidence,
            claims=claims,
            llm_summary=llm_summary,
            llm_status=llm_status,
        )

    def analyze(self, herbs: list[str]) -> AnalysisResult:
        """Compatibility facade; production runs execute these stages as graph nodes."""
        normalized = self.normalize(herbs)
        discovery = self.discover(normalized)
        compounds = self.chemistry(discovery.compounds)
        return self.finalize(
            normalized,
            compounds,
            discovery.evidence,
            discovery.unresolved_herbs,
            discovery.online_failures,
        )

    def _compound(
        self,
        compound_id: str,
        name: str,
        herb: str,
        smiles: str,
        cid: int | None,
        evidence_ids: list[str],
    ) -> CompoundResult:
        descriptors = self.calculate_descriptors(smiles)
        return CompoundResult(
            compound_id=compound_id,
            name=name,
            herb=herb,
            smiles=smiles,
            pubchem_cid=cid,
            descriptors=descriptors,
            candidate_score=self.score(smiles, descriptors),
            evidence_ids=evidence_ids,
        )
