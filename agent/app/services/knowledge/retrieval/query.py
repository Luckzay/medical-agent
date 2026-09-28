from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RetrievalQuery:
    lexical: str
    vector: str
    exact_doi: tuple[str, ...]
    exact_smiles: tuple[str, ...]


def build_retrieval_query(
    *,
    query: str | None = None,
    research_goal: str | None = None,
    herbs: list[str] | None = None,
    compounds: list[str] | None = None,
    smiles: list[str] | None = None,
) -> RetrievalQuery:
    """Build stable lexical/E5 inputs without discarding exact identifiers."""

    def clean(values: list[str] | None) -> tuple[str, ...]:
        return tuple(dict.fromkeys(value.strip() for value in (values or []) if value.strip()))

    herbs_clean, compounds_clean, smiles_clean = clean(herbs), clean(compounds), clean(smiles)
    natural = " ".join(part.strip() for part in (research_goal, query) if part and part.strip())
    parts = [natural, *herbs_clean, *compounds_clean, *smiles_clean]
    lexical = " ".join(dict.fromkeys(part for part in parts if part))
    vector_parts = [
        natural,
        f"中药：{'、'.join(herbs_clean)}" if herbs_clean else "",
        f"候选成分：{'、'.join(compounds_clean)}" if compounds_clean else "",
        f"SMILES：{' '.join(smiles_clean)}" if smiles_clean else "",
    ]
    vector = "；".join(part for part in vector_parts if part) or lexical
    dois = tuple(
        token.rstrip(".,;)") for token in lexical.split() if token.lower().startswith("10.")
    )
    return RetrievalQuery(lexical=lexical, vector=vector, exact_doi=dois, exact_smiles=smiles_clean)
