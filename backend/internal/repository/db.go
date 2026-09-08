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
		Logger: logger.Default.LogMode(logger.Warn),
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
		&model.DecoctionToxicCompound{},
		&model.HerbCoupletBasic{},
		&model.HerbCoupletToxicCompound{},
		&model.Paper{},
		&model.PaperTag{},
		&model.AgentRun{},
		&model.AgentSession{},
		&model.AgentChatMessage{},
		&model.AgentChatTurn{},
		&model.LLMConfig{},
	}

	if err := DB.AutoMigrate(tables...); err != nil {
		return err
	}

	return nil
}
