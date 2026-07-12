package model

import "time"

type DecoctionBasic struct {
	ID                           int       `gorm:"primaryKey;autoIncrement" json:"id"`
	DecoctionName                string    `gorm:"unique;not null;size:255" json:"decoction_name"`
	DecoctionNamePinyin          string    `gorm:"size:255" json:"decoction_name_pinyin"`
	DosageForm                   string    `gorm:"size:255" json:"dosage_form"`
	Functionality                string    `gorm:"type:text" json:"functionality"`
	FunctionalityBasis           string    `gorm:"type:text" json:"functionality_basis"`
	LinkToFunctionalityBasis     string    `gorm:"size:512" json:"link_to_functionality_basis"`
	UsageAndDosage               string    `gorm:"type:text" json:"usage_and_dosage"`
	BasisForUsageAndDosage       string    `gorm:"size:255" json:"basis_for_usage_and_dosage"`
	LinkToUsageAndDosage         string    `gorm:"size:512" json:"link_to_usage_and_dosage"`
	Virulence                    string    `gorm:"type:text" json:"virulence"`
	ToxicityMechanism            string    `gorm:"type:text" json:"toxicity_mechanism"`
	PathologicalExamination      string    `gorm:"type:text" json:"pathological_examination"`
	CrowdTaboo                   string    `gorm:"type:text" json:"crowd_taboo"`
	SymptomContraindications     string    `gorm:"type:text" json:"symptom_contraindications"`
	RelatedToxicHerbs            string    `gorm:"type:text" json:"related_toxic_herbs"`
	ADR                          string    `gorm:"type:text" json:"adr"`
	TypicalCasesOfADR            string    `gorm:"type:text" json:"typical_cases_of_adr"`
	ClinicalSuggestion           string    `gorm:"type:text" json:"clinical_suggestion"`
	ClinicalSuggestionBasis      string    `gorm:"type:text" json:"clinical_suggestion_basis"`
	LinkToClinicalSuggestion     string    `gorm:"size:512" json:"link_to_clinical_suggestion"`
	RelatedStudies               string    `gorm:"type:text" json:"related_studies"`
	LinkToRelatedStudies         string    `gorm:"size:512" json:"link_to_related_studies"`
	ConclusionOfRelatedStudies   string    `gorm:"type:text" json:"conclusion_of_related_studies"`
	CreatedAt                    time.Time `gorm:"autoCreateTime" json:"created_at"`
	UpdatedAt                    time.Time `gorm:"autoUpdateTime" json:"updated_at"`
}

func (DecoctionBasic) TableName() string { return "decoction_basic" }
