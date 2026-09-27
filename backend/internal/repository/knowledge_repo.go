package repository

import (
	"context"
	"fmt"
	"strings"

	"medicalagent/internal/model"

	"gorm.io/gorm"
)

type ToxicCompoundResult struct {
	CompoundName string `json:"compound_name"`
	Formula      string `json:"formula"`
	CAS          string `json:"cas"`
}

type KnowledgeResult struct {
	Type                     string                `json:"type"`
	ID                       string                `json:"id"`
	Title                    string                `json:"title"`
	Summary                  string                `json:"summary"`
	Reference                *string               `json:"reference,omitempty"`
	Virulence                string                `json:"virulence,omitempty"`
	ToxicityMechanism        string                `json:"toxicity_mechanism,omitempty"`
	PathologicalExamination  string                `json:"pathological_examination,omitempty"`
	CrowdTaboo               string                `json:"crowd_taboo,omitempty"`
	SymptomContraindications string                `json:"symptom_contraindications,omitempty"`
	ADR                      string                `json:"adr,omitempty"`
	TypicalCasesOfADR        string                `json:"typical_cases_of_adr,omitempty"`
	ClinicalSuggestion       string                `json:"clinical_suggestion,omitempty"`
	ClinicalSuggestionBasis  string                `json:"clinical_suggestion_basis,omitempty"`
	LinkToClinicalSuggestion string                `json:"link_to_clinical_suggestion,omitempty"`
	ToxicCompounds           []ToxicCompoundResult `json:"toxic_compounds,omitempty"`
}

type KnowledgeRepository interface {
	Search(ctx context.Context, query string, types []string, limit int) ([]KnowledgeResult, error)
}

type KnowledgeRepo struct{ db *gorm.DB }

func NewKnowledgeRepo() *KnowledgeRepo { return &KnowledgeRepo{db: DB} }

func (r *KnowledgeRepo) Search(ctx context.Context, query string, types []string, limit int) ([]KnowledgeResult, error) {
	like := "%" + escapeLike(query) + "%"
	results := make([]KnowledgeResult, 0, limit)
	for _, kind := range types {
		if len(results) >= limit {
			break
		}
		remaining := limit - len(results)
		if kind == "herbs" {
			rows, err := r.searchToxicologyHerbs(ctx, like, remaining)
			if err != nil {
				return nil, err
			}
			results = append(results, rows...)
			continue
		}
		var rows []KnowledgeResult
		var sql string
		switch kind {
		case "decoctions":
			sql = `SELECT 'decoctions' AS type, CAST(id AS CHAR) AS id, decoction_name AS title, functionality AS summary, NULL AS reference FROM decoction_basic WHERE decoction_name LIKE ? ESCAPE '\\' OR functionality LIKE ? ESCAPE '\\' ORDER BY id LIMIT ?`
		case "couplets":
			sql = `SELECT 'couplets' AS type, CAST(id AS CHAR) AS id, herb_couplet_name AS title, functionality AS summary, NULL AS reference FROM herb_couplet_basic WHERE herb_couplet_name LIKE ? ESCAPE '\\' OR functionality LIKE ? ESCAPE '\\' ORDER BY id LIMIT ?`
		case "compounds":
			sql = `SELECT 'compounds' AS type, CAST(record_number AS CHAR) AS id, record_title AS title, record_description AS summary, NULL AS reference FROM molecular_info WHERE record_title LIKE ? ESCAPE '\\' OR record_description LIKE ? ESCAPE '\\' ORDER BY record_number LIMIT ?`
		case "papers":
			sql = `SELECT 'papers' AS type, CAST(id AS CHAR) AS id, title, abstract AS summary, NULLIF(doi, '') AS reference FROM papers WHERE title LIKE ? ESCAPE '\\' OR abstract LIKE ? ESCAPE '\\' ORDER BY id LIMIT ?`
		default:
			return nil, fmt.Errorf("unsupported knowledge type %q", kind)
		}
		if err := r.db.WithContext(ctx).Raw(sql, like, like, remaining).Scan(&rows).Error; err != nil {
			return nil, err
		}
		results = append(results, rows...)
	}
	return results, nil
}

func (r *KnowledgeRepo) searchToxicologyHerbs(ctx context.Context, like string, limit int) ([]KnowledgeResult, error) {
	var herbs []model.HerbBasic
	toxicFields := []string{
		"herb_name", "virulence", "toxicity_mechanism", "pathological_examination",
		"crowd_taboo", "symptom_contraindications", "adr", "typical_cases_of_adr",
		"clinical_suggestion", "clinical_suggestion_basis", "link_to_clinical_suggestion",
	}
	clauses := make([]string, 0, len(toxicFields)+1)
	args := make([]any, 0, len(toxicFields)+4)
	for _, field := range toxicFields {
		clauses = append(clauses, field+` LIKE ? ESCAPE '\\'`)
		args = append(args, like)
	}
	clauses = append(clauses, `id IN (SELECT herb_id FROM herb_toxiccompound WHERE compound_name LIKE ? ESCAPE '\\' OR molecular_formula LIKE ? ESCAPE '\\' OR cas LIKE ? ESCAPE '\\')`)
	args = append(args, like, like, like)
	if err := r.db.WithContext(ctx).Where(strings.Join(clauses, " OR "), args...).Order("id").Limit(limit).Find(&herbs).Error; err != nil {
		return nil, err
	}
	if len(herbs) == 0 {
		return []KnowledgeResult{}, nil
	}
	ids := make([]int, 0, len(herbs))
	for _, herb := range herbs {
		ids = append(ids, herb.ID)
	}
	var compounds []model.HerbToxicCompound
	if err := r.db.WithContext(ctx).Where("herb_id IN ?", ids).Order("herb_id, id").Find(&compounds).Error; err != nil {
		return nil, err
	}
	byHerb := make(map[int][]model.HerbToxicCompound)
	for _, compound := range compounds {
		byHerb[compound.HerbID] = append(byHerb[compound.HerbID], compound)
	}
	results := make([]KnowledgeResult, 0, len(herbs))
	for _, herb := range herbs {
		results = append(results, herbKnowledgeResult(herb, byHerb[herb.ID]))
	}
	return results, nil
}

func herbKnowledgeResult(herb model.HerbBasic, compounds []model.HerbToxicCompound) KnowledgeResult {
	reference := fmt.Sprintf("herb_basic:%d", herb.ID)
	toxicCompounds := make([]ToxicCompoundResult, 0, len(compounds))
	for _, compound := range compounds {
		toxicCompounds = append(toxicCompounds, ToxicCompoundResult{
			CompoundName: compound.CompoundName,
			Formula:      compound.MolecularFormula,
			CAS:          compound.CAS,
		})
	}
	return KnowledgeResult{
		Type: "herbs", ID: fmt.Sprint(herb.ID), Title: herb.HerbName,
		Summary: herb.Virulence, Reference: &reference, Virulence: herb.Virulence,
		ToxicityMechanism: herb.ToxicityMechanism, PathologicalExamination: herb.PathologicalExamination,
		CrowdTaboo: herb.CrowdTaboo, SymptomContraindications: herb.SymptomContraindications,
		ADR: herb.ADR, TypicalCasesOfADR: herb.TypicalCasesOfADR,
		ClinicalSuggestion: herb.ClinicalSuggestion, ClinicalSuggestionBasis: herb.ClinicalSuggestionBasis,
		LinkToClinicalSuggestion: herb.LinkToClinicalSuggestion, ToxicCompounds: toxicCompounds,
	}
}

func escapeLike(value string) string {
	replacer := strings.NewReplacer(`\`, `\\`, `%`, `\%`, `_`, `\_`)
	return replacer.Replace(value)
}
