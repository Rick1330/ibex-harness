package anthropic

import (
	"fmt"

	"github.com/Rick1330/ibex-harness/packages/crypto"
)

func newFallbackCompletionID() string {
	return fmt.Sprintf("chatcmpl-anthropic-%s", crypto.GenerateRandomBase62(8))
}
