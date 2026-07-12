package model

type DecoctionToxicCompound struct {
	ID               int    `gorm:"primaryKey;autoIncrement" json:"id"`
	DecoctionID      int    `gorm:"not null" json:"decoction_id"`
	RecordNumber     int64  `gorm:"not null" json:"record_number"`
	CompoundType     string `gorm:"size:255" json:"compound_type"`
	CompoundName     string `gorm:"size:255" json:"compound_name"`
	MolecularFormula string `gorm:"size:255" json:"molecular_formula"`
	CAS              string `gorm:"size:255" json:"cas"`
}

func (DecoctionToxicCompound) TableName() string { return "decoction_toxiccompound" }
