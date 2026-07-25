package session

import (
	"errors"

	"github.com/lib/pq"
)

// uniqueViolationSQLState is Postgres SQLSTATE unique_violation.
const uniqueViolationSQLState = "23505"

func isUniqueViolation(err error) bool {
	var pqErr *pq.Error
	if !errors.As(err, &pqErr) {
		return false
	}
	return pqErr.Code == uniqueViolationSQLState
}
