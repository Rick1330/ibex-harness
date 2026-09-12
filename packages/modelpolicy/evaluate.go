package modelpolicy

import "sort"

// Decision is the result of evaluating org policies against a candidate model.
type Decision struct {
	Allowed bool
	Matched bool
	Policy  *Policy
}

// EvaluatePolicies applies priority-ASC first-match-wins rules.
// No matching row → Allowed=true, Matched=false (platform default).
func EvaluatePolicies(policies []Policy, model string) (Decision, error) {
	ordered := append([]Policy(nil), policies...)
	sort.SliceStable(ordered, func(i, j int) bool {
		if ordered[i].Priority != ordered[j].Priority {
			return ordered[i].Priority < ordered[j].Priority
		}
		return ordered[i].Pattern < ordered[j].Pattern
	})
	for i := range ordered {
		p := &ordered[i]
		ok, err := Match(p.Pattern, model)
		if err != nil {
			return Decision{}, err
		}
		if !ok {
			continue
		}
		cp := *p
		return Decision{Allowed: p.Allowed, Matched: true, Policy: &cp}, nil
	}
	return Decision{Allowed: true, Matched: false}, nil
}
