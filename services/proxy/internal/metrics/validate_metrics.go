package metrics

import (
	"sort"
	"strconv"
	"strings"
)

type resultMetricStore struct {
	total   map[string]uint64
	buckets map[string][]uint64
	sums    map[string]float64
}

func newResultMetricStore() resultMetricStore {
	return resultMetricStore{
		total:   make(map[string]uint64),
		buckets: make(map[string][]uint64),
		sums:    make(map[string]float64),
	}
}

func (s *resultMetricStore) observe(result string, seconds float64) {
	s.total[result]++
	if _, ok := s.buckets[result]; !ok {
		s.buckets[result] = make([]uint64, len(durationBuckets)+1)
	}
	recordHistogram(s.buckets[result], durationBuckets, seconds)
	s.sums[result] += seconds
}

type resultMetricSnap struct {
	total   map[string]uint64
	buckets map[string][]uint64
	sums    map[string]float64
}

func snapResultMetrics(s resultMetricStore) resultMetricSnap {
	total := make(map[string]uint64, len(s.total))
	for k, v := range s.total {
		total[k] = v
	}
	buckets := make(map[string][]uint64, len(s.buckets))
	for k, v := range s.buckets {
		a := make([]uint64, len(v))
		copy(a, v)
		buckets[k] = a
	}
	sums := make(map[string]float64, len(s.sums))
	for k, v := range s.sums {
		sums[k] = v
	}
	return resultMetricSnap{total: total, buckets: buckets, sums: sums}
}

type resultValidateSectionOpts struct {
	metricPrefix string
	helpTotal    string
	helpDuration string
	snap         resultMetricSnap
}

func writeResultValidateSection(b *strings.Builder, opts resultValidateSectionOpts) {
	b.WriteString("# HELP ")
	b.WriteString(opts.metricPrefix)
	b.WriteString("_total ")
	b.WriteString(opts.helpTotal)
	b.WriteString("\n# TYPE ")
	b.WriteString(opts.metricPrefix)
	b.WriteString("_total counter\n")
	for _, result := range sortedStringKeys(opts.snap.total) {
		b.WriteString(opts.metricPrefix)
		b.WriteString("_total{result=")
		writeQuoted(b, result)
		b.WriteString("} ")
		b.WriteString(strconv.FormatUint(opts.snap.total[result], 10))
		b.WriteString("\n")
	}

	b.WriteString("# HELP ")
	b.WriteString(opts.metricPrefix)
	b.WriteString("_duration_seconds ")
	b.WriteString(opts.helpDuration)
	b.WriteString("\n# TYPE ")
	b.WriteString(opts.metricPrefix)
	b.WriteString("_duration_seconds histogram\n")
	for _, result := range sortedStringKeysFromBuckets(opts.snap.buckets) {
		writeAuthHistogramLines(b, opts.metricPrefix+"_duration_seconds", result, opts.snap.buckets[result], opts.snap.sums[result], durationBuckets)
	}
}

func sortedStringKeys(m map[string]uint64) []string {
	keys := make([]string, 0, len(m))
	for k := range m {
		keys = append(keys, k)
	}
	sort.Strings(keys)
	return keys
}

func sortedStringKeysFromBuckets(m map[string][]uint64) []string {
	keys := make([]string, 0, len(m))
	for k := range m {
		keys = append(keys, k)
	}
	sort.Strings(keys)
	return keys
}
