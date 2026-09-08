package repository

import (
	"fmt"

	"medicalagent/internal/model"

	"gorm.io/gorm"
)

const guestRecordLimit = 20

var publicTableKeys = map[string]string{
	"herb_basic":         "id",
	"decoction_basic":    "id",
	"herb_couplet_basic": "id",
	"molecular_info":     "record_number",
	"cases":              "case_id",
	"clauses":            "clause_id",
	"papers":             "id",
}

// IsPublicRecord returns whether keyValue belongs to the first 20 rows in the
// table's canonical ascending order. Table/key identifiers come only from the
// whitelist above; callers cannot inject SQL identifiers.
func IsPublicRecord(table string, keyValue any) (bool, error) {
	key, ok := publicTableKeys[table]
	if !ok {
		return false, fmt.Errorf("unsupported public table %q", table)
	}
	var ids []int64
	if err := DB.Table(table).Order(key+" ASC").Limit(guestRecordLimit).Pluck(key, &ids).Error; err != nil {
		return false, err
	}
	return IsWithinGuestRecords(ids, keyValue), nil
}

func IsWithinGuestRecords(ids []int64, keyValue any) bool {
	wanted := fmt.Sprint(keyValue)
	for _, id := range ids {
		if fmt.Sprint(id) == wanted {
			return true
		}
	}
	return false
}

type ImportedContentRepo struct {
	db *gorm.DB
}

func NewImportedContentRepo() *ImportedContentRepo { return &ImportedContentRepo{db: DB} }

func (r *ImportedContentRepo) List(table string, page, pageSize int) ([]map[string]any, int64, error) {
	if table != "cases" && table != "clauses" {
		return nil, 0, fmt.Errorf("unsupported imported table %q", table)
	}
	var total int64
	if err := r.db.Table(table).Count(&total).Error; err != nil {
		return nil, 0, err
	}
	key := publicTableKeys[table]
	list := make([]map[string]any, 0)
	err := r.db.Table(table).Order(key + " ASC").Offset((page - 1) * pageSize).Limit(pageSize).Find(&list).Error
	normalizeRows(list)
	return list, total, err
}

func (r *ImportedContentRepo) Detail(kind string, id int64) (map[string]any, []model.HerbBasic, []model.DecoctionBasic, error) {
	if kind != "case" && kind != "clause" {
		return nil, nil, nil, fmt.Errorf("unsupported imported content kind %q", kind)
	}
	table := kind + "s"
	foreignKey := kind + "_id"

	record := make(map[string]any)
	if err := r.db.Table(table).Where(foreignKey+" = ?", id).Take(&record).Error; err != nil {
		return nil, nil, nil, err
	}
	normalizeRow(record)

	herbs := make([]model.HerbBasic, 0)
	herbJoin := fmt.Sprintf("JOIN %s_herbs AS links ON links.herb_id = herb_basic.id", kind)
	if err := r.db.Table("herb_basic").Joins(herbJoin).Where("links."+foreignKey+" = ?", id).Order("herb_basic.id ASC").Find(&herbs).Error; err != nil {
		return nil, nil, nil, err
	}

	decoctions := make([]model.DecoctionBasic, 0)
	decoctionJoin := fmt.Sprintf("JOIN %s_decoctions AS links ON links.decoction_id = decoction_basic.id", kind)
	if err := r.db.Table("decoction_basic").Joins(decoctionJoin).Where("links."+foreignKey+" = ?", id).Order("decoction_basic.id ASC").Find(&decoctions).Error; err != nil {
		return nil, nil, nil, err
	}
	return record, herbs, decoctions, nil
}

func normalizeRows(rows []map[string]any) {
	for _, row := range rows {
		normalizeRow(row)
	}
}

func normalizeRow(row map[string]any) {
	for key, value := range row {
		if bytes, ok := value.([]byte); ok {
			row[key] = string(bytes)
		}
	}
}
