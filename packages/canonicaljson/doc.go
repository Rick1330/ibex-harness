// Package canonicaljson implements the evidence/idempotency JCS contract.
//
// This package is deliberately not used by packages/privacyaudit, whose
// canonical bytes must match PostgreSQL jsonb::text, or by session hashing,
// whose contract is encoding/json checkpoint state. Evidence payload digests
// are RFC 8785-compatible UTF-8 JSON and are identified as jcs/v1.
package canonicaljson
