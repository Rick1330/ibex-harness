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

func defaultHashBearer(bearer string) (string, error) {
	return crypto.HashToken(bearer, crypto.ProductionParams())
}

func run(args []string, stdout, stderr io.Writer, hashBearer func(string) (string, error)) int {
	bearer, err := parseArgs(args)
	if err != nil {
		fmt.Fprintln(stderr, err)
		return 2
	}
	hash, err := hashBearer(bearer)
	if err != nil {
		fmt.Fprintln(stderr, err)
		return 2
	}
	fmt.Fprintln(stdout, hash)
	return 0
}

func runCLI(args []string) int {
	return run(args, os.Stdout, os.Stderr, defaultHashBearer)
}

func main() {
	os.Exit(runCLI(os.Args[1:]))
}
