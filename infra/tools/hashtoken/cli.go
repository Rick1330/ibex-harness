package main

import (
	"fmt"
	"io"
	"os"

	"github.com/Rick1330/ibex-harness/packages/crypto"
)

func parseArgs(args []string) (string, error) {
	if len(args) != 1 || args[0] == "" {
		return "", fmt.Errorf("usage: hashtoken <bearer-token>")
	}
	return args[0], nil
}

var (
	hashBearerFn = func(bearer string) (string, error) {
		return crypto.HashToken(bearer, crypto.ProductionParams())
	}
	exitFn = os.Exit
)

func run(args []string, stdout, stderr io.Writer) int {
	bearer, err := parseArgs(args)
	if err != nil {
		fmt.Fprintln(stderr, err)
		return 2
	}
	hash, err := hashBearerFn(bearer)
	if err != nil {
		fmt.Fprintln(stderr, err)
		return 2
	}
	fmt.Fprintln(stdout, hash)
	return 0
}

func main() {
	exitFn(run(os.Args[1:], os.Stdout, os.Stderr))
}
