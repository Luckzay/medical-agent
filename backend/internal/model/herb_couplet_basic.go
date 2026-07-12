package model

import "time"

type HerbCoupletBasic struct {
	ID                        int       `gorm:"primaryKey;autoIncrement" json:"id"`
	HerbCoupletName           string    `gorm:"unique;not null;size:255" json:"herb_couplet_name"`
	HerbCoupletNamePinyin     string    `gorm:"size:255" json:"herb_couplet_name_pinyin"`
	Functionality             string    `gorm:"type:text" json:"functionality"`
	FunctionalityBasis        string    `gorm:"type:text" json:"functionality_basis"`
	LinkToFunctionalityBasis  string    `gorm:"size:512" json:"link_to_functionality_basis"`
	Virulence                 string    `gorm:"type:text" json:"virulence"`
	ToxicityMechanism         string    `gorm:"type:text" json:"toxicity_mechanism"`
	PathologicalExamination   string    `gorm:"type:text" json:"pathological_examination"`
	CrowdTaboo                string    `gorm:"type:text" json:"crowd_taboo"`
	SymptomContraindications  string    `gorm:"type:text" json:"symptom_contraindications"`
	RelatedToxicHerbs         string    `gorm:"type:text" json:"related_toxic_herbs"`
	ADR                       string    `gorm:"type:text" json:"adr"`
	TypicalCasesOfADR         string    `gorm:"type:text" json:"typical_cases_of_adr"`
	ClinicalSuggestion        string    `gorm:"type:text" json:"clinical_suggestion"`
	ClinicalSuggestionBasis   string    `gorm:"type:text" json:"clinical_suggestion_basis"`
	LinkToClinicalSuggestion  string    `gorm:"size:512" json:"link_to_clinical_suggestion"`
	CreatedAt                 time.Time `gorm:"autoCreateTime" json:"created_at"`
	UpdatedAt                 time.Time `gorm:"autoUpdateTime" json:"updated_at"`
}

func (HerbCoupletBasic) TableName() string { return "herb_couplet_basic" }
