package model

import "time"

type MolecularInfo struct {
	RecordNumber              int64   `gorm:"primaryKey;autoIncrement" json:"record_number"`
	RecordTitle               string  `gorm:"size:255" json:"record_title"`
	RecordDescription         string  `gorm:"type:text" json:"record_description"`
	FDAPharmacologySummary    string  `gorm:"type:text;column:fda_pharmacology_summary" json:"fda_pharmacology_summary"`
	LivertoxSummary           string  `gorm:"type:text;column:livertox_summary" json:"livertox_summary"`
	InChI                     string  `gorm:"size:255;column:inchi" json:"inchi"`
	InChIKey                  string  `gorm:"unique;size:255;column:inchi_key" json:"inchi_key"`
	SMILES                    string  `gorm:"size:255;column:smiles" json:"smiles"`
	MolecularFormula          string  `gorm:"size:255" json:"molecular_formula"`
	MolecularWeight           float64 `json:"molecular_weight"`
	XLogP3                    float64 `json:"xlogp3"`
	HydrogenBondDonorCount    int64   `json:"hydrogen_bond_donor_count"`
	HydrogenBondAcceptorCount int64   `json:"hydrogen_bond_acceptor_count"`
	RotatableBondCount        int64   `json:"rotatable_bond_count"`
	HeavyAtomCount            int64   `json:"heavy_atom_count"`
	CreatedAt                 time.Time `gorm:"autoCreateTime" json:"created_at"`
}

func (MolecularInfo) TableName() string { return "molecular_info" }
