package directive

import (
	"go.opentelemetry.io/otel/attribute"
)

const (
	attrDBSystem    = "db.system"
	attrDBOperation = "db.operation"
	dbSystemRedis   = "redis"
)

func redisSpanAttrs(operation string) []attribute.KeyValue {
	return []attribute.KeyValue{
		attribute.String(attrDBSystem, dbSystemRedis),
		attribute.String(attrDBOperation, operation),
	}
}
