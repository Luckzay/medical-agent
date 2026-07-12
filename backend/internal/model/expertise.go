package model

type Expertise struct {
	ID                  int    `gorm:"primaryKey;autoIncrement" json:"id"`
	HerbID              int    `gorm:"not null" json:"herb_id"`
	RelatedArticle      string `gorm:"size:255" json:"related_article"`
	LinkArticle         string `gorm:"size:512" json:"link_article"`
	Author              string `gorm:"size:255" json:"author"`
	Abstract            string `gorm:"type:text" json:"abstract"`
	HerbOrDecoction     string `gorm:"type:text" json:"herb_or_decoction"`
	ApplicationSituation string `gorm:"type:text" json:"application_situation"`
	DosageCourseUsage   string `gorm:"type:text" json:"dosage_course_usage"`
	Couplet             string `gorm:"type:text" json:"couplet"`
	ClinicalCase        string `gorm:"type:text" json:"clinical_case"`
	RelatedLiterature   string `gorm:"type:text" json:"related_literature"`
}

func (Expertise) TableName() string { return "expertise" }
