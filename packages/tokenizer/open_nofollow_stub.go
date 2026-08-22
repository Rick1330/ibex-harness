//go:build !linux && !darwin && !freebsd && !openbsd

package tokenizer

func openFlagNoFollow() int {
	return 0
}
