//go:build linux || darwin || freebsd || openbsd

package tokenizer

import "syscall"

func openFlagNoFollow() int {
	return syscall.O_NOFOLLOW
}
