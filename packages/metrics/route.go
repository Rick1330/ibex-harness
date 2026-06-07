package metrics

import "net/http"

func routeTemplate(r *http.Request) string {
	if r.Pattern != "" {
		return r.Pattern
	}
	return "/unknown"
}
