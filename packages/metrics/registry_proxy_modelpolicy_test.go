package metrics

import "testing"

func TestProxyRegistry_ModelPolicyMetrics(t *testing.T) {
	t.Parallel()
	reg := NewProxy("model-policy-metrics-test")
	reg.IncCacheHit("lru")
	reg.IncCacheMiss("lru")
	reg.IncDeny()
	reg.IncInvalidate()
	reg.SetLRUSize(3)

	var nilReg *ProxyRegistry
	nilReg.IncCacheHit("lru")
	nilReg.IncCacheMiss("lru")
	nilReg.IncDeny()
	nilReg.IncInvalidate()
	nilReg.SetLRUSize(0)
}
