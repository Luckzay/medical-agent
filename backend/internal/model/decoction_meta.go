package model

type DecoctionMeta struct {
	ID                       int     `gorm:"primaryKey;autoIncrement" json:"id"`
	DecoctionID              int     `gorm:"not null" json:"decoction_id"`
	ReviewNumber             int     `gorm:"not null" json:"review_number"`
	SystematicReview         string  `gorm:"size:255" json:"systematic_review"`
	Link                     string  `gorm:"size:512" json:"link"`
	SortingNumber            int     `gorm:"not null" json:"sorting_number"`
	IndexValue               string  `gorm:"size:255" json:"index_value"`
	Study                    string  `gorm:"size:255" json:"study"`
	QualityScore             float64 `gorm:"type:decimal(6,2)" json:"quality_score"`
	QualityEvaluationCriteria string `gorm:"size:255" json:"quality_evaluation_criteria"`
	ExperimentalEvents       float64 `gorm:"type:decimal(10,4)" json:"experimental_events"`
	ExperimentalTotal        float64 `gorm:"type:decimal(10,4)" json:"experimental_total"`
	ControlEvents            float64 `gorm:"type:decimal(10,4)" json:"control_events"`
	ControlTotal             float64 `gorm:"type:decimal(10,4)" json:"control_total"`
	Weight                   string  `gorm:"size:255" json:"weight"`
	OrOrRR                   float64 `gorm:"type:decimal(10,4);column:or_or_rr" json:"or_or_rr"`
	CI95Lower                float64 `gorm:"type:decimal(10,4);column:ci_95_lower" json:"ci_95_lower"`
	CI95Upper                float64 `gorm:"type:decimal(10,4);column:ci_95_upper" json:"ci_95_upper"`
	IndexNumber              string  `gorm:"size:255" json:"index_number"`
	PValue                   float64 `gorm:"type:decimal(10,4);column:p_value" json:"p_value"`
	I2                       string  `gorm:"size:255" json:"i2"`
	Model                    string  `gorm:"size:255" json:"model"`
	TSAAnalysis              string  `gorm:"size:255;column:tsa_analysis" json:"tsa_analysis"`
}

func (DecoctionMeta) TableName() string { return "decoction_meta" }
