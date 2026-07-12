package model

import "time"

type Paper struct {
	ID        int       `gorm:"primaryKey;autoIncrement" json:"id"`
	Title     string    `gorm:"size:1000" json:"title"`
	Authors   string    `gorm:"size:2000" json:"authors"`
	Journal   string    `gorm:"size:200" json:"journal"`
	Year      int       `json:"year"`
	Abstract  string    `gorm:"type:text" json:"abstract"`
	DOI       string    `gorm:"unique;size:100" json:"doi"`
	SourceDB  string    `gorm:"size:100" json:"source_db"`
	CreatedAt time.Time `gorm:"autoCreateTime" json:"created_at"`
}

func (Paper) TableName() string { return "papers" }

type PaperTag struct {
	PaperID int    `gorm:"primaryKey" json:"paper_id"`
	Tag     string `gorm:"primaryKey;size:100" json:"tag"`
}

func (PaperTag) TableName() string { return "paper_tags" }
