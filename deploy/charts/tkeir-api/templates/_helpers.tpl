{{/*
API chart helpers — wrap library namespaced to this chart.
*/}}
{{- define "tkeir-api.name" -}}
{{- include "tkeir-lib.name" . -}}
{{- end -}}

{{- define "tkeir-api.fullname" -}}
{{- include "tkeir-lib.fullname" . -}}
{{- end -}}

{{- define "tkeir-api.labels" -}}
{{- include "tkeir-lib.labels" . -}}
{{- end -}}

{{- define "tkeir-api.selectorLabels" -}}
{{- include "tkeir-lib.selectorLabels" . -}}
{{- end -}}

{{- define "tkeir-api.serviceAccountName" -}}
{{- if .Values.serviceAccount.create -}}
{{- default (include "tkeir-api.fullname" .) .Values.serviceAccount.name -}}
{{- else -}}
{{- default "default" .Values.serviceAccount.name -}}
{{- end -}}
{{- end -}}
