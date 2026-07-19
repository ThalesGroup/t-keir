{{- define "tkeir-vespa.name" -}}
{{- include "tkeir-lib.name" . -}}
{{- end -}}
{{- define "tkeir-vespa.fullname" -}}
{{- include "tkeir-lib.fullname" . -}}
{{- end -}}
{{- define "tkeir-vespa.labels" -}}
{{- include "tkeir-lib.labels" . -}}
{{- end -}}
{{- define "tkeir-vespa.selectorLabels" -}}
{{- include "tkeir-lib.selectorLabels" . -}}
{{- end -}}
{{- define "tkeir-vespa.serviceAccountName" -}}
{{- if .Values.serviceAccount.create -}}
{{- default (include "tkeir-vespa.fullname" .) .Values.serviceAccount.name -}}
{{- else -}}
{{- default "default" .Values.serviceAccount.name -}}
{{- end -}}
{{- end -}}
{{- define "tkeir-vespa.resources" -}}
{{- $profile := .Values.resourceProfile | default "laptop" -}}
{{- $res := index .Values.resources $profile | default .Values.resources.laptop -}}
{{- toYaml $res -}}
{{- end -}}
