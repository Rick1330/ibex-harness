package metrics

import "net/http"

// UnknownRoute is the fallback route label when pattern matching fails.
const UnknownRoute = "/unknown"

func routeTemplate(r *http.Request) string {
	if r.Pattern != "" {
		return r.Pattern
	}
	return UnknownRoute
}
