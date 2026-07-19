{{/*
Governor chart helpers — wrap library namespaced to this chart.
*/}}
{{- define "tkeir-governor.name" -}}
{{- include "tkeir-lib.name" . -}}
{{- end -}}

{{- define "tkeir-governor.fullname" -}}
{{- include "tkeir-lib.fullname" . -}}
{{- end -}}

{{- define "tkeir-governor.labels" -}}
{{- include "tkeir-lib.labels" . -}}
{{- end -}}

{{- define "tkeir-governor.selectorLabels" -}}
{{- include "tkeir-lib.selectorLabels" . -}}
{{- end -}}

{{- define "tkeir-governor.serviceAccountName" -}}
{{- if .Values.serviceAccount.create -}}
{{- default (include "tkeir-governor.fullname" .) .Values.serviceAccount.name -}}
{{- else -}}
{{- default "default" .Values.serviceAccount.name -}}
{{- end -}}
{{- end -}}
