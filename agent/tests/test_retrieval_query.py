import pytest

from app.services.retrieval_query import build_retrieval_query


@pytest.mark.parametrize(
    ("goal", "herbs", "compounds", "smiles", "expected"),
    [
        ("机制", ["当归"], [], [], "当归"),
        ("组装", ["黄芪"], [], [], "黄芪"),
        (None, ["甘草"], [], [], "甘草"),
        ("药效", [], ["阿魏酸"], [], "阿魏酸"),
        ("筛选", [], ["黄芪甲苷"], [], "黄芪甲苷"),
        (None, [], ["甘草酸"], [], "甘草酸"),
        ("结构", [], [], ["CCO"], "CCO"),
        ("结构", [], [], ["C=O"], "C=O"),
        (None, [], [], ["N#N"], "N#N"),
        ("机制", ["当归", "当归"], [], [], "当归"),
        ("机制", [" 当归 "], [], [], "当归"),
        ("机制", [], [" 阿魏酸 "], [], "阿魏酸"),
        ("机制", [], [], [" CCO "], "CCO"),
        ("mechanism", ["Astragalus"], [], [], "Astragalus"),
        ("assembly", [], ["Ferulic acid"], [], "Ferulic acid"),
        ("检索", ["丹参"], ["丹参酮"], [], "丹参酮"),
        ("检索", ["人参"], [], ["CCC"], "CCC"),
        (None, ["川芎"], ["藁本内酯"], ["CO"], "藁本内酯"),
        ("温度条件", ["当归"], ["阿魏酸"], ["CCO"], "温度条件"),
        ("pH 条件", ["黄芪"], ["黄芪甲苷"], ["CCC"], "pH 条件"),
    ],
)
def test_query_builder_stable_compatibility_cases(
    goal: str | None,
    herbs: list[str],
    compounds: list[str],
    smiles: list[str],
    expected: str,
) -> None:
    result = build_retrieval_query(
        research_goal=goal, herbs=herbs, compounds=compounds, smiles=smiles
    )
    assert expected in result.lexical
    assert result.vector
    assert result.exact_smiles == tuple(dict.fromkeys(item.strip() for item in smiles))
