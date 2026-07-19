{{- define "tkeir-indexer.fullname" -}}
{{- include "tkeir-lib.fullname" . -}}
{{- end -}}
{{- define "tkeir-indexer.labels" -}}
{{- include "tkeir-lib.labels" . -}}
{{- end -}}
{{- define "tkeir-indexer.serviceAccountName" -}}
{{- if .Values.serviceAccount.create -}}
{{- default (include "tkeir-indexer.fullname" .) .Values.serviceAccount.name -}}
{{- else -}}
{{- default "default" .Values.serviceAccount.name -}}
{{- end -}}
{{- end -}}
