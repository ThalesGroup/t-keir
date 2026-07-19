{{- define "tkeir-audit.name" -}}
{{- include "tkeir-lib.name" . -}}
{{- end -}}

{{- define "tkeir-audit.fullname" -}}
{{- include "tkeir-lib.fullname" . -}}
{{- end -}}

{{- define "tkeir-audit.labels" -}}
{{- include "tkeir-lib.labels" . -}}
{{- end -}}

{{- define "tkeir-audit.selectorLabels" -}}
{{- include "tkeir-lib.selectorLabels" . -}}
{{- end -}}

{{- define "tkeir-audit.serviceAccountName" -}}
{{- if .Values.serviceAccount.create -}}
{{- default (include "tkeir-audit.fullname" .) .Values.serviceAccount.name -}}
{{- else -}}
{{- default "default" .Values.serviceAccount.name -}}
{{- end -}}
{{- end -}}

{{- define "tkeir-audit.hotStoreUrl" -}}
{{- if .Values.hotStoreUrl -}}
{{- .Values.hotStoreUrl -}}
{{- else if .Values.postgres.enabled -}}
postgres://{{ .Values.postgres.username }}:{{ .Values.postgres.password }}@{{ include "tkeir-audit.fullname" . }}-postgres:5432/{{ .Values.postgres.database }}
{{- else -}}
sqlite:////var/tkeir/audit/hot/audit.db
{{- end -}}
{{- end -}}
