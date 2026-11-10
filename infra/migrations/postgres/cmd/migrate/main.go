package main

import (
	"errors"
	"flag"
	"fmt"
	"os"

	pgmigrate "github.com/Rick1330/ibex-harness/infra/migrations/postgres"
)

// errForceVersion signals the force command was called without -version.
var errForceVersion = errors.New("requires -version N")

// errUnknownCommand signals an unrecognised migration command.
var errUnknownCommand = errors.New("unknown command")

func main() {
	command := flag.String("command", "", "migration command: up, down, version, force, provision")
	version := flag.Int("version", 0, "target version for force")
	flag.Parse()

	if *command == "" && flag.NArg() > 0 {
		*command = flag.Arg(0)
	}
	if *command == "" {
		printUsage()
		os.Exit(2)
	}
	if err := run(*command, *version); err != nil {
		fmt.Fprintf(os.Stderr, "migrate %s: %v\n", *command, err)
		code := exitCode(err)
		if code == 2 {
			printUsage()
		}
		os.Exit(code)
	}
}

// exitCode maps a run error to the process exit status. Usage errors keep
// status 2; everything else is a failure.
func exitCode(err error) int {
	if errors.Is(err, errForceVersion) || errors.Is(err, errUnknownCommand) {
		return 2
	}
	return 1
}

// run dispatches one migration command. It is separate from main so the
// command set does not inflate main's complexity.
func run(command string, version int) error {
	dsn := pgmigrate.ResolveDSN()
	switch command {
	case "up":
		return runUp(dsn)
	case "down":
		return runDown(dsn)
	case "version":
		return runVersion(dsn)
	case "force":
		return runForce(dsn, version)
	case "provision":
		return runProvision(dsn)
	default:
		return fmt.Errorf("%w: %s", errUnknownCommand, command)
	}
}

// runUp applies pending migrations.
func runUp(dsn string) error {
	if err := pgmigrate.Up(dsn); err != nil {
		return err
	}
	fmt.Println("migrate up: ok")
	return nil
}

// runDown rolls back one migration step.
func runDown(dsn string) error {
	if err := pgmigrate.Down(dsn); err != nil {
		return err
	}
	fmt.Println("migrate down: ok")
	return nil
}

// runVersion prints the current version and dirty flag.
func runVersion(dsn string) error {
	v, dirty, err := pgmigrate.Version(dsn)
	if err != nil {
		return err
	}
	fmt.Printf("version=%d dirty=%v\n", v, dirty)
	return nil
}

// runForce sets the migration version without running SQL.
func runForce(dsn string, version int) error {
	if version <= 0 {
		return errForceVersion
	}
	if err := pgmigrate.Force(dsn, version); err != nil {
		return err
	}
	fmt.Printf("migrate force: ok (version=%d)\n", version)
	return nil
}

// runProvision sets the capability-login credentials.
func runProvision(dsn string) error {
	if err := pgmigrate.Provision(dsn); err != nil {
		return err
	}
	fmt.Println("migrate provision: ok")
	return nil
}

// printUsage writes the command and provisioning help.
func printUsage() {
	fmt.Fprintln(os.Stderr, "usage: migrate -command up|down|version|force|provision [-version N]")
	fmt.Fprintln(os.Stderr, "       provision sets the capability-login passwords from")
	fmt.Fprintln(os.Stderr, "       IBEX_RUNTIME_DB_PASSWORD, IBEX_WORKER_DB_PASSWORD and")
	fmt.Fprintln(os.Stderr, "       IBEX_BOOTSTRAP_DB_PASSWORD. Secrets must be printable")
	fmt.Fprintln(os.Stderr, "       ASCII without spaces, differ from the migration DSN")
	fmt.Fprintln(os.Stderr, "       credential, and differ from each other.")
}
