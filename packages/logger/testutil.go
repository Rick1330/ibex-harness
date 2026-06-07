package logger

import "io"

// Discard returns a logger that writes to io.Discard for tests.
func Discard(service string) *Logger {
	log, err := New(Config{Service: service, Writer: io.Discard})
	if err != nil {
		panic(err)
	}
	return log
}
