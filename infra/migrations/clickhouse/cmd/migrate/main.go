package main

import (
	"flag"
	"fmt"
	"os"

	chmigrate "github.com/Rick1330/ibex-harness/infra/migrations/clickhouse"
)

func main() {
	os.Exit(run(os.Args[1:]))
}

func run(args []string) int {
	fs := flag.NewFlagSet("clickhouse-migrate", flag.ContinueOnError)
	command := fs.String("command", "", "migration command: up, down, version, force")
	version := fs.Int("version", 0, "target version for force")
	if err := fs.Parse(args); err != nil {
		return 2
	}
	if *command == "" && fs.NArg() > 0 {
		*command = fs.Arg(0)
	}
	if *command == "" {
		fmt.Fprintln(os.Stderr, "usage: migrate -command up|down|version|force [-version N]")
		return 2
	}
	return runCommand(*command, *version, chmigrate.ResolveDSN())
}

func runCommand(command string, version int, dsn string) int {
	switch command {
	case "up":
		return printMigrateErr("up", chmigrate.Up(dsn))
	case "down":
		return printMigrateErr("down", chmigrate.Down(dsn))
	case "version":
		return printVersion(dsn)
	case "force":
		return runForce(dsn, version)
	default:
		fmt.Fprintf(os.Stderr, "unknown command: %s\n", command)
		return 2
	}
}

func printMigrateErr(op string, err error) int {
	if err != nil {
		fmt.Fprintf(os.Stderr, "clickhouse migrate %s: %v\n", op, err)
		return 1
	}
	fmt.Printf("clickhouse migrate %s: ok\n", op)
	return 0
}

func printVersion(dsn string) int {
	v, dirty, err := chmigrate.Version(dsn)
	if err != nil {
		fmt.Fprintf(os.Stderr, "clickhouse migrate version: %v\n", err)
		return 1
	}
	fmt.Printf("version=%d dirty=%v\n", v, dirty)
	return 0
}

func runForce(dsn string, version int) int {
	if version <= 0 {
		fmt.Fprintln(os.Stderr, "clickhouse migrate force requires -version N")
		return 2
	}
	if err := chmigrate.Force(dsn, version); err != nil {
		fmt.Fprintf(os.Stderr, "clickhouse migrate force: %v\n", err)
		return 1
	}
	fmt.Printf("clickhouse migrate force: ok (version=%d)\n", version)
	return 0
}
