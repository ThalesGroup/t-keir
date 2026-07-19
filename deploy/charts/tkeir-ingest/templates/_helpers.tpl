{{/*
Ingest chart helpers — wrap library namespaced to this chart.
*/}}
{{- define "tkeir-ingest.name" -}}
{{- include "tkeir-lib.name" . -}}
{{- end -}}

{{- define "tkeir-ingest.fullname" -}}
{{- include "tkeir-lib.fullname" . -}}
{{- end -}}

{{- define "tkeir-ingest.labels" -}}
{{- include "tkeir-lib.labels" . -}}
{{- end -}}

{{- define "tkeir-ingest.selectorLabels" -}}
{{- include "tkeir-lib.selectorLabels" . -}}
{{- end -}}

{{- define "tkeir-ingest.serviceAccountName" -}}
{{- if .Values.serviceAccount.create -}}
{{- default (include "tkeir-ingest.fullname" .) .Values.serviceAccount.name -}}
{{- else -}}
{{- default "default" .Values.serviceAccount.name -}}
{{- end -}}
{{- end -}}
