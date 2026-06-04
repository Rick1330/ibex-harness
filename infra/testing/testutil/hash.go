//go:build integration

package testutil

import (
	"github.com/Rick1330/ibex-harness/packages/crypto"
)

func hashBearerForTest(bearer string) (string, error) {
	return crypto.HashToken(bearer, crypto.ProductionParams())
}
