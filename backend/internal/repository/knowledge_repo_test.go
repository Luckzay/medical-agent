package repository

import (
	"testing"

	"medicalagent/internal/model"
)

func TestEscapeLikeEscapesWildcards(t *testing.T) {
	if got, want := escapeLike(`a%b_c\d`), `a\%b\_c\\d`; got != want {
		t.Fatalf("escapeLike() = %q, want %q", got, want)
	}
}

func TestHerbKnowledgeResultContainsToxicologyFieldsAndTraceableSource(t *testing.T) {
	herb := model.HerbBasic{
		ID: 7, HerbName: "附子", Virulence: "有毒", ToxicityMechanism: "机制记录",
		PathologicalExamination: "病理记录", CrowdTaboo: "人群禁忌",
		SymptomContraindications: "证候禁忌", ADR: "不良反应",
		TypicalCasesOfADR: "典型案例", ClinicalSuggestion: "临床建议",
		ClinicalSuggestionBasis: "依据记录", LinkToClinicalSuggestion: "https://example.test/source",
	}
	got := herbKnowledgeResult(herb, []model.HerbToxicCompound{{
		HerbID: 7, CompoundName: "乌头碱", MolecularFormula: "C34H47NO11", CAS: "302-27-2",
	}})
	if got.Reference == nil || *got.Reference != "herb_basic:7" {
		t.Fatalf("reference = %v", got.Reference)
	}
	if got.Virulence == "" || got.ToxicityMechanism == "" || got.PathologicalExamination == "" ||
		got.CrowdTaboo == "" || got.SymptomContraindications == "" || got.ADR == "" ||
		got.TypicalCasesOfADR == "" || got.ClinicalSuggestion == "" ||
		got.ClinicalSuggestionBasis == "" || got.LinkToClinicalSuggestion == "" {
		t.Fatalf("missing toxicology field: %+v", got)
	}
	if len(got.ToxicCompounds) != 1 || got.ToxicCompounds[0].CompoundName != "乌头碱" ||
		got.ToxicCompounds[0].Formula != "C34H47NO11" || got.ToxicCompounds[0].CAS != "302-27-2" {
		t.Fatalf("toxic compounds = %+v", got.ToxicCompounds)
	}
}
