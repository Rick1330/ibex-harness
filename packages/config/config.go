// Package config provides typed, validated environment variable loading for IBEX Go services.
package config

import (
	"fmt"
	"log/slog"
	"os"
	"reflect"
	"strings"

	"github.com/caarlos0/env/v11"
)

// Secret marks a field value as sensitive. Its value is redacted in debug logs.
type Secret string

// String returns the secret value.
func (s Secret) String() string { return string(s) }

// Load parses environment variables into T and validates required fields.
// Returns a descriptive error listing all missing/invalid variables.
func Load[T any]() (T, error) {
	var cfg T
	if err := env.Parse(&cfg); err != nil {
		return cfg, err
	}
	return cfg, nil
}

// MustLoad is Load with a fatal log on error. Use in main() only.
func MustLoad[T any]() T {
	cfg, err := Load[T]()
	if err != nil {
		slog.New(slog.NewJSONHandler(os.Stderr, nil)).Error("configuration error", "error", err)
		os.Exit(1)
	}
	return cfg
}

// LogDebug logs resolved config at DEBUG level, redacting secret-tagged fields.
func LogDebug[T any](cfg T) {
	slog.Default().Debug("resolved configuration", "config", redactConfig(cfg))
}

func redactConfig(v any) map[string]any {
	out := make(map[string]any)
	redactValue(reflect.ValueOf(v), out)
	return out
}

func redactValue(v reflect.Value, out map[string]any) {
	v, ok := derefValue(v)
	if !ok {
		return
	}
	if v.Kind() != reflect.Struct {
		out["value"] = fmt.Sprintf("%v", v.Interface())
		return
	}
	redactStructFields(v, out)
}

func derefValue(v reflect.Value) (reflect.Value, bool) {
	if !v.IsValid() {
		return v, false
	}
	for v.Kind() == reflect.Pointer {
		if v.IsNil() {
			return v, false
		}
		v = v.Elem()
	}
	return v, true
}

func redactStructFields(v reflect.Value, out map[string]any) {
	t := v.Type()
	for i := 0; i < v.NumField(); i++ {
		field := t.Field(i)
		if !field.IsExported() {
			continue
		}
		out[fieldName(field)] = redactFieldValue(field, v.Field(i))
	}
}

func redactFieldValue(field reflect.StructField, fv reflect.Value) any {
	if isSecretField(field, fv) {
		return "[REDACTED]"
	}
	if fv.Kind() == reflect.Struct && field.Type != reflect.TypeOf(Secret("")) {
		nested := make(map[string]any)
		redactValue(fv, nested)
		return nested
	}
	return fv.Interface()
}

func fieldName(field reflect.StructField) string {
	if tag := strings.TrimSpace(field.Tag.Get("env")); tag != "" {
		parts := strings.SplitN(tag, ",", 2)
		if parts[0] != "" {
			return parts[0]
		}
	}
	return field.Name
}

func isSecretField(field reflect.StructField, v reflect.Value) bool {
	if strings.EqualFold(field.Tag.Get("secret"), "true") {
		return true
	}
	return v.Type() == reflect.TypeOf(Secret(""))
}
