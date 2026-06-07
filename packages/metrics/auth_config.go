package metrics

import "database/sql"

// AuthConfig configures auth service metric registration.
type AuthConfig struct {
	ServiceName string
	DB          *sql.DB
}
