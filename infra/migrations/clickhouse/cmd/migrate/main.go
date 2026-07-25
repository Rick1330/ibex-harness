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
	cmd := resolveCommand(*command, fs)
	if cmd == "" {
		fmt.Fprintln(os.Stderr, "usage: migrate -command up|down|version|force [-version N]")
		return 2
	}
	return dispatch(cmd, *version, chmigrate.ResolveConn())
}

func resolveCommand(flagCmd string, fs *flag.FlagSet) string {
	if flagCmd != "" {
		return flagCmd
	}
	if fs.NArg() > 0 {
		return fs.Arg(0)
	}
	return ""
}

func dispatch(command string, version int, conn chmigrate.Conn) int {
	switch command {
	case "up":
		return printMigrateErr("up", chmigrate.Up(conn))
	case "down":
		return printMigrateErr("down", chmigrate.Down(conn))
	case "version":
		return printVersion(conn)
	case "force":
		return runForce(conn, version)
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

func printVersion(conn chmigrate.Conn) int {
	v, dirty, err := chmigrate.Version(conn)
	if err != nil {
		fmt.Fprintf(os.Stderr, "clickhouse migrate version: %v\n", err)
		return 1
	}
	fmt.Printf("version=%d dirty=%v\n", v, dirty)
	return 0
}

func runForce(conn chmigrate.Conn, version int) int {
	if version <= 0 {
		fmt.Fprintln(os.Stderr, "clickhouse migrate force requires -version N")
		return 2
	}
	if err := chmigrate.Force(conn, version); err != nil {
		fmt.Fprintf(os.Stderr, "clickhouse migrate force: %v\n", err)
		return 1
	}
	fmt.Printf("clickhouse migrate force: ok (version=%d)\n", version)
	return 0
}
