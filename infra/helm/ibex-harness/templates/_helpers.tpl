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

{{/*
Extract @sha256:<64hex> from an image reference for IBEX_DEPLOY_IMAGE_DIGEST.
Returns empty string when the image is not digest-pinned.
*/}}
{{- define "ibex.imageDigest" -}}
{{- $img := . | toString -}}
{{- if contains "@sha256:" $img -}}
{{- $parts := splitList "@" $img -}}
{{- $digest := index $parts (sub (len $parts) 1) -}}
{{- if regexMatch "^sha256:[a-f0-9]{64}$" $digest -}}
{{- $digest -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{/* Omit replicas when HPA owns the count (avoids Helm reset on upgrade). */}}
{{- define "ibex.replicas" -}}
{{- if not .Values.hpa.enabled }}
replicas: {{ .Values.hpa.minReplicas }}
{{- end }}
{{- end -}}

{{/* rollingUpdate fields are only valid with RollingUpdate strategy. */}}
{{- define "ibex.strategy" -}}
strategy:
  type: {{ .Values.rollout.strategy }}
  {{- if eq .Values.rollout.strategy "RollingUpdate" }}
  rollingUpdate:
    maxUnavailable: {{ .Values.rollout.maxUnavailable }}
    maxSurge: {{ .Values.rollout.maxSurge }}
  {{- end }}
{{- end -}}
