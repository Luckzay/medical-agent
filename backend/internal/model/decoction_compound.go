package model

type DecoctionCompound struct {
	ID               int    `gorm:"primaryKey;autoIncrement" json:"id"`
	DecoctionID      int    `gorm:"not null" json:"decoction_id"`
	CompoundType     string `gorm:"size:255" json:"compound_type"`
	CompoundName     string `gorm:"size:255;not null" json:"compound_name"`
	MolecularFormula string `gorm:"size:255" json:"molecular_formula"`
	CAS              string `gorm:"size:255" json:"cas"`
}

func (DecoctionCompound) TableName() string { return "decoction_compound" }
