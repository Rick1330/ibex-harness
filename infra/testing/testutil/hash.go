//go:build integration

package testutil

import (
	"os"

	"github.com/Rick1330/ibex-harness/packages/crypto"
)

func hashBearerForTest(bearer string) (string, error) {
	if os.Getenv("IBEX_TEST_FAST_ARGON2") == "1" {
		return crypto.HashToken(bearer, crypto.TestParams())
	}
	return crypto.HashToken(bearer, crypto.ProductionParams())
}
