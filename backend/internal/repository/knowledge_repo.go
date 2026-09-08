package repository

import (
	"context"
	"fmt"
	"strings"

	"gorm.io/gorm"
)

type KnowledgeResult struct {
	Type      string  `json:"type"`
	ID        string  `json:"id"`
	Title     string  `json:"title"`
	Summary   string  `json:"summary"`
	Reference *string `json:"reference,omitempty"`
}

type KnowledgeRepository interface {
	Search(ctx context.Context, query string, types []string, limit int) ([]KnowledgeResult, error)
}

type KnowledgeRepo struct{ db *gorm.DB }

func NewKnowledgeRepo() *KnowledgeRepo { return &KnowledgeRepo{db: DB} }

func (r *KnowledgeRepo) Search(ctx context.Context, query string, types []string, limit int) ([]KnowledgeResult, error) {
	like := "%" + escapeLike(query) + "%"
	perType := limit
	results := make([]KnowledgeResult, 0, limit)
	for _, kind := range types {
		if len(results) >= limit {
			break
		}
		var rows []KnowledgeResult
		var sql string
		switch kind {
		case "herbs":
			sql = `SELECT 'herbs' AS type, CAST(id AS CHAR) AS id, herb_name AS title, functionality AS summary, NULL AS reference FROM herb_basic WHERE herb_name LIKE ? ESCAPE '\\' OR functionality LIKE ? ESCAPE '\\' ORDER BY id LIMIT ?`
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
		if err := r.db.WithContext(ctx).Raw(sql, like, like, perType).Scan(&rows).Error; err != nil {
			return nil, err
		}
		remaining := limit - len(results)
		if len(rows) > remaining {
			rows = rows[:remaining]
		}
		results = append(results, rows...)
	}
	return results, nil
}

func escapeLike(value string) string {
	replacer := strings.NewReplacer(`\`, `\\`, `%`, `\%`, `_`, `\_`)
	return replacer.Replace(value)
}
