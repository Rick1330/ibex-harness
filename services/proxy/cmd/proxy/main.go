package main

import (
	"os"

	"github.com/Rick1330/ibex-harness/services/proxy/internal/bootstrap"
)

func main() {
	os.Exit(bootstrap.Run(os.Args[1:]))
}
