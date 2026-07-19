{{- define "tkeir-hmi.name" -}}
{{- include "tkeir-lib.name" . -}}
{{- end -}}
{{- define "tkeir-hmi.fullname" -}}
{{- include "tkeir-lib.fullname" . -}}
{{- end -}}
{{- define "tkeir-hmi.labels" -}}
{{- include "tkeir-lib.labels" . -}}
{{- end -}}
{{- define "tkeir-hmi.selectorLabels" -}}
{{- include "tkeir-lib.selectorLabels" . -}}
{{- end -}}
{{- define "tkeir-hmi.serviceAccountName" -}}
{{- if .Values.serviceAccount.create -}}
{{- default (include "tkeir-hmi.fullname" .) .Values.serviceAccount.name -}}
{{- else -}}
{{- default "default" .Values.serviceAccount.name -}}
{{- end -}}
{{- end -}}
