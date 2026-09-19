{{- define "ibex.name" -}}
ibex-harness
{{- end -}}

{{- define "ibex.labels" -}}
app.kubernetes.io/name: {{ include "ibex.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
ibex.io/milestone: "4.p.5"
{{- end -}}

{{- define "ibex.selector" -}}
app.kubernetes.io/name: {{ include "ibex.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/component: {{ .component }}
{{- end -}}
