// Package evidence contains the reviewed positive-list sanitizer used by the
// proxy session evidence producer. It deliberately copies only fields named in
// the versioned session-metadata-allowlist-v1 contract.
package evidence

import (
	"math"
	"regexp"
	"sort"
	"strings"

	"github.com/Rick1330/ibex-harness/packages/evidenceoutbox"
	"github.com/google/uuid"
)

const RedactionProofVersion = "session-metadata-allowlist/v1"

var (
	requestIDPattern = regexp.MustCompile(`^[A-Za-z0-9._:-]{1,128}$`)
	modelIDPattern   = regexp.MustCompile(`^[A-Za-z0-9._:+/-]{1,128}$`)
	schemaPattern    = regexp.MustCompile(`^[A-Za-z0-9._/-]{1,64}$`)
	digestPattern    = regexp.MustCompile(`^(sha256:)?[A-Fa-f0-9]{64}$`)
	imagePattern     = regexp.MustCompile(`^sha256:[A-Fa-f0-9]{64}$`)
)

// SanitizationResult is a fresh, positive-list RunInput plus its classification.
type SanitizationResult struct {
	Input          evidenceoutbox.RunInput
	RedactionClass evidenceoutbox.RedactionClass
	DroppedFields  []string
	Withheld       bool
}

// SanitizeRunInput is pure: it does not mutate the input or consult ambient
// state. It withholds rows missing their required tenant, agent, session,
// request, or W3C trace identity. Any unsafe/unlisted value is removed and
// downgrades the entire row to redacted.
func SanitizeRunInput(in evidenceoutbox.RunInput) SanitizationResult {
	if !validSessionEvidenceIdentity(in) {
		return withheldEvidenceInput()
	}
	dropped := make(map[string]struct{})
	markDropped := func(name string) { dropped[name] = struct{}{} }
	out := copySessionEvidenceIdentity(in)
	sanitizeModelUsage(in, &out, markDropped)
	sanitizeTraceReferences(in, &out, markDropped)
	sanitizeStatusAndCompleteness(in, &out, markDropped)
	sanitizeCapturePolicy(in, &out, markDropped)
	sanitizeTimingAndImage(in, &out, markDropped)
	sanitizeNestedEvidence(in, &out, markDropped)
	copySessionEvidenceProof(in, &out)
	return finishSanitization(out, dropped)
}

func validSessionEvidenceIdentity(in evidenceoutbox.RunInput) bool {
	return in.OrgID != uuid.Nil && in.AgentID != nil && *in.AgentID != uuid.Nil &&
		in.SessionID != nil && *in.SessionID != uuid.Nil && requestIDPattern.MatchString(in.RequestID) &&
		validW3C(in.TraceID, 32) && validSessionFence(in)
}

func withheldEvidenceInput() SanitizationResult {
	return SanitizationResult{
		RedactionClass: evidenceoutbox.RedactionClassRedacted, Withheld: true,
		DroppedFields: []string{"org_id", "agent_id", "session_id", "request_id", "trace_id", "producer_or_fence"},
	}
}

func copySessionEvidenceIdentity(in evidenceoutbox.RunInput) evidenceoutbox.RunInput {
	return evidenceoutbox.RunInput{
		OrgID: in.OrgID, AgentID: cloneUUID(in.AgentID), SessionID: cloneUUID(in.SessionID),
		RequestID: in.RequestID, TraceID: strings.ToLower(in.TraceID),
		StartedAt: in.StartedAt, EndedAt: in.EndedAt,
	}
}

func sanitizeModelUsage(in evidenceoutbox.RunInput, out *evidenceoutbox.RunInput, markDropped func(string)) {
	if in.ModelID != "" {
		if modelIDPattern.MatchString(in.ModelID) {
			out.ModelID = in.ModelID
		} else {
			markDropped("model_id")
		}
	}
	if in.TokenUsage == nil {
		return
	}
	usage := in.TokenUsage
	if usage.InputTokens < 0 || usage.OutputTokens < 0 || usage.TotalTokens < 0 ||
		usage.InputTokens > 1_000_000_000_000 || usage.OutputTokens > 1_000_000_000_000 ||
		usage.TotalTokens > 1_000_000_000_000 || usage.TotalTokens < usage.InputTokens+usage.OutputTokens {
		markDropped("token_usage")
		return
	}
	copy := *usage
	out.TokenUsage = &copy
}

func sanitizeTraceReferences(in evidenceoutbox.RunInput, out *evidenceoutbox.RunInput, markDropped func(string)) {
	if validW3C(in.RootSpanID, 16) {
		out.RootSpanID = strings.ToLower(in.RootSpanID)
	} else if in.RootSpanID != "" {
		markDropped("root_span_id")
	}
	if validW3C(in.MetricsSpanID, 16) {
		out.MetricsSpanID = strings.ToLower(in.MetricsSpanID)
	} else if in.MetricsSpanID != "" {
		markDropped("metrics_span_id")
	}
	if in.CheckpointID != nil && *in.CheckpointID != uuid.Nil {
		out.CheckpointID = cloneUUID(in.CheckpointID)
	} else if in.CheckpointID != nil {
		markDropped("checkpoint_id")
	}
	if in.TurnID != nil && *in.TurnID >= 0 {
		value := *in.TurnID
		out.TurnID = &value
	} else if in.TurnID != nil {
		markDropped("turn_id")
	}
}

func sanitizeStatusAndCompleteness(in evidenceoutbox.RunInput, out *evidenceoutbox.RunInput, markDropped func(string)) {
	if (in.RedactionClass != "" && in.RedactionClass != evidenceoutbox.RedactionClassMetadata) ||
		(in.Producer.RedactionClass != "" && in.Producer.RedactionClass != evidenceoutbox.RedactionClassMetadata) ||
		in.Completeness == "redacted" {
		markDropped("pre_redacted_or_prohibited")
	}
	out.Status = in.Status
	if out.Status != "ok" && out.Status != "error" {
		out.Status = "ok"
		markDropped("status")
	}
	out.Completeness = in.Completeness
	if !oneOf(out.Completeness, "complete", "partial", "sampled", "late", "redacted", "expired", "deleted", "simulated") {
		out.Completeness = "partial"
		markDropped("completeness")
	}
}

func sanitizeCapturePolicy(in evidenceoutbox.RunInput, out *evidenceoutbox.RunInput, markDropped func(string)) {
	if oneOf(in.CaptureMode, "metadata", "redacted", "off") {
		out.CaptureMode = in.CaptureMode
	} else if in.CaptureMode != "" {
		markDropped("capture_mode")
	}
	if oneOf(in.SampleDecision, "included", "sampled", "excluded") {
		out.SampleDecision = in.SampleDecision
	} else if in.SampleDecision != "" {
		markDropped("sample_decision")
	}
}

func sanitizeTimingAndImage(in evidenceoutbox.RunInput, out *evidenceoutbox.RunInput, markDropped func(string)) {
	if !in.EndedAt.IsZero() && !in.StartedAt.IsZero() && in.EndedAt.Before(in.StartedAt) {
		out.EndedAt = in.StartedAt
		markDropped("ended_at")
	}
	if in.DeployImageDigest != "" {
		if imagePattern.MatchString(in.DeployImageDigest) {
			out.DeployImageDigest = strings.ToLower(in.DeployImageDigest)
		} else {
			markDropped("deploy_image_digest")
		}
	}
	if in.ErrorCode != "" {
		markDropped("error_code")
	}
}

func sanitizeNestedEvidence(in evidenceoutbox.RunInput, out *evidenceoutbox.RunInput, markDropped func(string)) {
	out.Spans = sanitizeSpans(in.Spans, markDropped)
	out.Metrics = sanitizeMetrics(in.Metrics, markDropped)
	out.Candidates = sanitizeCandidates(in.Candidates, markDropped)
	out.Directive = sanitizeDirective(in.Directive, markDropped)
	if len(in.Tools) != 0 {
		markDropped("tools")
	}
	if len(in.SessionEvents) != 0 {
		markDropped("session_events")
	}
}

func copySessionEvidenceProof(in evidenceoutbox.RunInput, out *evidenceoutbox.RunInput) {
	producer := *in.Producer
	fence := *in.TombstoneFence
	out.Producer = &producer
	out.TombstoneFence = &fence
}

func finishSanitization(out evidenceoutbox.RunInput, dropped map[string]struct{}) SanitizationResult {
	result := SanitizationResult{Input: out, RedactionClass: evidenceoutbox.RedactionClassMetadata}
	for field := range dropped {
		result.DroppedFields = append(result.DroppedFields, field)
	}
	sort.Strings(result.DroppedFields)
	if len(result.DroppedFields) != 0 {
		result.RedactionClass = evidenceoutbox.RedactionClassRedacted
		result.Input.Completeness = "redacted"
	}
	result.Input.RedactionClass = result.RedactionClass
	result.Input.Producer.RedactionClass = result.RedactionClass
	return result
}

func validSessionFence(in evidenceoutbox.RunInput) bool {
	producer, fence := in.Producer, in.TombstoneFence
	if producer == nil || fence == nil || producer.ResourceType != "session" || fence.ResourceType != "session" ||
		producer.RedactionProofVersion != RedactionProofVersion || producer.Source != "proxy.session.evidence" ||
		producer.ResourceID == "" || fence.ResourceID == "" || producer.ResourceVersion <= 0 || fence.ResourceVersion <= 0 {
		return false
	}
	return producer.ResourceID == in.SessionID.String() && fence.ResourceID == in.SessionID.String() &&
		producer.ResourceID == fence.ResourceID && producer.ResourceVersion == fence.ResourceVersion
}

func sanitizeSpans(in []evidenceoutbox.SpanInput, markDropped func(string)) []evidenceoutbox.SpanInput {
	out := make([]evidenceoutbox.SpanInput, 0, len(in))
	for _, span := range in {
		clean, ok := sanitizeSpan(span, markDropped)
		if ok {
			out = append(out, clean)
		}
	}
	return out
}

func sanitizeSpan(span evidenceoutbox.SpanInput, markDropped func(string)) (evidenceoutbox.SpanInput, bool) {
	if !validSpan(span) {
		markDropped("span")
		return evidenceoutbox.SpanInput{}, false
	}
	if span.ErrorCode != "" {
		markDropped("span.error_code")
	}
	if len(span.Attributes) != 0 {
		markDropped("span.attributes")
	}
	clean := evidenceoutbox.SpanInput{
		SpanID: strings.ToLower(span.SpanID), OperationKind: span.OperationKind,
		Status: span.Status, StartedAt: span.StartedAt, EndedAt: span.EndedAt,
	}
	if span.ParentSpanID != "" {
		clean.ParentSpanID = strings.ToLower(span.ParentSpanID)
	}
	if !clean.EndedAt.IsZero() && !clean.StartedAt.IsZero() && clean.EndedAt.Before(clean.StartedAt) {
		clean.EndedAt = clean.StartedAt
		markDropped("span.ended_at")
	}
	return clean, true
}

func validSpan(span evidenceoutbox.SpanInput) bool {
	return validW3C(span.SpanID, 16) &&
		(span.ParentSpanID == "" || validW3C(span.ParentSpanID, 16)) &&
		oneOf(span.OperationKind, "proxy.chat", "context.assemble") && oneOf(span.Status, "ok", "error")
}

func sanitizeMetrics(in *evidenceoutbox.AssemblyMetrics, markDropped func(string)) *evidenceoutbox.AssemblyMetrics {
	if in == nil {
		return nil
	}
	values := []int{in.BudgetCalculationMs, in.DirectiveLoadMs, in.HotMemoryRetrievalMs,
		in.ColdMemoryRetrievalMs, in.RankingMs, in.PackingMs, in.FormattingMs,
		in.TotalMs, in.CandidatesEvaluated}
	for _, value := range values {
		if value < 0 || value > 1_000_000_000 {
			markDropped("metrics")
			return nil
		}
	}
	return &evidenceoutbox.AssemblyMetrics{
		BudgetCalculationMs: in.BudgetCalculationMs, DirectiveLoadMs: in.DirectiveLoadMs,
		HotMemoryRetrievalMs: in.HotMemoryRetrievalMs, ColdMemoryRetrievalMs: in.ColdMemoryRetrievalMs,
		RankingMs: in.RankingMs, PackingMs: in.PackingMs, FormattingMs: in.FormattingMs,
		TotalMs: in.TotalMs, CandidatesEvaluated: in.CandidatesEvaluated,
	}
}

func sanitizeCandidates(in []evidenceoutbox.ScoreCandidate, markDropped func(string)) []evidenceoutbox.ScoreCandidate {
	if len(in) == 0 {
		return nil
	}
	out := make([]evidenceoutbox.ScoreCandidate, 0, len(in))
	for _, candidate := range in {
		clean, ok := sanitizeCandidate(candidate, markDropped)
		if ok {
			out = append(out, clean)
		}
	}
	return out
}

func sanitizeCandidate(in evidenceoutbox.ScoreCandidate, markDropped func(string)) (evidenceoutbox.ScoreCandidate, bool) {
	if in.MemoryID == uuid.Nil || in.RetrievalRank < 0 {
		markDropped("candidates")
		return evidenceoutbox.ScoreCandidate{}, false
	}
	clean := evidenceoutbox.ScoreCandidate{MemoryID: in.MemoryID, RetrievalRank: in.RetrievalRank}
	sanitizeCandidateCategory(in, &clean, markDropped)
	sanitizeCandidateRanks(in, &clean, markDropped)
	sanitizeCandidateScores(in, &clean, markDropped)
	sanitizeCandidateComponents(in, &clean, markDropped)
	sanitizeCandidateExclusion(in, &clean, markDropped)
	sanitizeCandidateTokenEstimate(in, &clean, markDropped)
	return clean, true
}

func sanitizeCandidateCategory(in evidenceoutbox.ScoreCandidate, out *evidenceoutbox.ScoreCandidate, markDropped func(string)) {
	if in.Category == "" {
		return
	}
	if oneOf(in.Category, "factual", "preference", "behavioral", "episodic", "procedural") {
		out.Category = in.Category
	} else {
		markDropped("candidate.category")
	}
}

func sanitizeCandidateRanks(in evidenceoutbox.ScoreCandidate, out *evidenceoutbox.ScoreCandidate, markDropped func(string)) {
	if in.FinalRank != nil && *in.FinalRank >= 0 {
		value := *in.FinalRank
		out.FinalRank = &value
	} else if in.FinalRank != nil {
		markDropped("candidate.final_rank")
	}
	if in.DeltaRank != nil {
		value := *in.DeltaRank
		out.DeltaRank = &value
	}
}

func sanitizeCandidateScores(in evidenceoutbox.ScoreCandidate, out *evidenceoutbox.ScoreCandidate, markDropped func(string)) {
	out.Similarity = safeScore(in.Similarity, "candidate.similarity", markDropped)
	out.Confidence = safeScore(in.Confidence, "candidate.confidence", markDropped)
	out.CompositeScore = safeScore(in.CompositeScore, "candidate.composite_score", markDropped)
	if in.ScoreSchema == "" {
		return
	}
	if schemaPattern.MatchString(in.ScoreSchema) {
		out.ScoreSchema = in.ScoreSchema
	} else {
		markDropped("candidate.score_schema")
	}
}

func sanitizeCandidateComponents(in evidenceoutbox.ScoreCandidate, out *evidenceoutbox.ScoreCandidate, markDropped func(string)) {
	if len(in.ScoreComponents) == 0 {
		return
	}
	out.ScoreComponents = make(map[string]float64)
	for key, value := range in.ScoreComponents {
		if !validScoreComponent(key, value) {
			markDropped("candidate.score_components")
			continue
		}
		out.ScoreComponents[key] = value
	}
	if len(out.ScoreComponents) == 0 {
		out.ScoreComponents = nil
	}
}

func validScoreComponent(key string, value float64) bool {
	return oneOf(key, "similarity", "confidence", "composite", "recency", "token_fit", "coverage") &&
		!math.IsNaN(value) && !math.IsInf(value, 0) && math.Abs(value) <= 1_000_000
}

func sanitizeCandidateExclusion(in evidenceoutbox.ScoreCandidate, out *evidenceoutbox.ScoreCandidate, markDropped func(string)) {
	if in.Exclusion == "" {
		return
	}
	if oneOf(in.Exclusion, "included", "none", "budget", "filter", "deduplicated", "filtered", "low_confidence", "not_selected") {
		out.Exclusion = in.Exclusion
	} else {
		markDropped("candidate.exclusion")
	}
}

func sanitizeCandidateTokenEstimate(in evidenceoutbox.ScoreCandidate, out *evidenceoutbox.ScoreCandidate, markDropped func(string)) {
	if in.TokenEstimate == nil {
		return
	}
	if *in.TokenEstimate < 0 {
		markDropped("candidate.token_estimate")
		return
	}
	value := *in.TokenEstimate
	out.TokenEstimate = &value
}

func sanitizeDirective(in *evidenceoutbox.DirectiveSnapshot, markDropped func(string)) *evidenceoutbox.DirectiveSnapshot {
	if in == nil {
		return nil
	}
	clean := &evidenceoutbox.DirectiveSnapshot{DirectiveVersionID: cloneUUID(in.DirectiveVersionID)}
	if in.ContentHash != "" {
		if digestPattern.MatchString(in.ContentHash) {
			clean.ContentHash = strings.ToLower(in.ContentHash)
		} else {
			markDropped("directive.content_hash")
		}
	}
	if clean.DirectiveVersionID == nil && clean.ContentHash == "" {
		return nil
	}
	return clean
}

func safeScore(in *float64, field string, markDropped func(string)) *float64 {
	if in == nil {
		return nil
	}
	if math.IsNaN(*in) || math.IsInf(*in, 0) || math.Abs(*in) > 1_000_000 {
		markDropped(field)
		return nil
	}
	v := *in
	return &v
}

func cloneUUID(in *uuid.UUID) *uuid.UUID {
	if in == nil || *in == uuid.Nil {
		return nil
	}
	v := *in
	return &v
}

func validW3C(value string, length int) bool {
	if len(value) != length || value == strings.Repeat("0", length) {
		return false
	}
	for _, c := range value {
		switch {
		case c >= '0' && c <= '9':
		case c >= 'a' && c <= 'f':
		case c >= 'A' && c <= 'F':
		default:
			return false
		}
	}
	return true
}

func oneOf(value string, allowed ...string) bool {
	for _, candidate := range allowed {
		if value == candidate {
			return true
		}
	}
	return false
}
