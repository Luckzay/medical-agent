package repository

import (
	"medicalagent/internal/config"
	"medicalagent/internal/model"

	"gorm.io/driver/mysql"
	"gorm.io/gorm"
	"gorm.io/gorm/logger"
)

var DB *gorm.DB

func InitDB(cfg config.DBConfig) error {
	var err error
	DB, err = gorm.Open(mysql.Open(cfg.DSN()), &gorm.Config{
		Logger: logger.Default.LogMode(logger.Info),
	})
	if err != nil {
		return err
	}

	tables := []any{
		&model.User{},
		&model.MolecularInfo{},
		&model.HerbBasic{},
		&model.HerbToxicCompound{},
		&model.DecoctionBasic{},
		&model.DecoctionCompound{},
		&model.DecoctionToxicCompound{},
		&model.DecoctionMeta{},
		&model.HerbCoupletBasic{},
		&model.HerbCoupletToxicCompound{},
		&model.Expertise{},
		&model.Paper{},
		&model.PaperTag{},
	}

	for _, t := range tables {
		if !DB.Migrator().HasTable(t) {
			return err
		}
	}
	return nil
}
