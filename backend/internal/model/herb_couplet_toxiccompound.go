package model

type HerbCoupletToxicCompound struct {
	ID               int    `gorm:"primaryKey;autoIncrement" json:"id"`
	CoupletID        int    `gorm:"not null" json:"couplet_id"`
	RecordNumber     int64  `gorm:"not null" json:"record_number"`
	CompoundType     string `gorm:"size:255" json:"compound_type"`
	CompoundName     string `gorm:"size:255" json:"compound_name"`
	MolecularFormula string `gorm:"size:255" json:"molecular_formula"`
	CAS              string `gorm:"size:255" json:"cas"`
}

func (HerbCoupletToxicCompound) TableName() string { return "herb_couplet_toxiccompound" }
