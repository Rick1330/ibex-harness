package modelpolicy

// Decision is the result of evaluating org policies against a candidate model.
type Decision struct {
	Allowed bool
	Matched bool
	Policy  *Policy
}

// EvaluatePolicies applies first-match-wins on policies already ordered by
// priority ASC, model_pattern ASC (store ORDER BY). No matching row → deny
// (4.P.1 deny-by-default; breaking vs ADR-0075 allow-on-miss).
func EvaluatePolicies(policies []Policy, model string) (Decision, error) {
	for i := range policies {
		p := &policies[i]
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
	return Decision{Allowed: false, Matched: false}, nil
}
