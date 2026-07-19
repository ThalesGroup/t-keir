{{- define "tkeir-inference.fullname" -}}
{{- include "tkeir-lib.fullname" . -}}
{{- end -}}
{{- define "tkeir-inference.labels" -}}
{{- include "tkeir-lib.labels" . -}}
{{- end -}}
{{- define "tkeir-inference.selectorLabels" -}}
{{- include "tkeir-lib.selectorLabels" . -}}
{{- end -}}
{{/*
Emit env map for consumers (documented; umbrella wires into api/indexer).
*/}}
{{- define "tkeir-inference.providerEnv" -}}
PROVIDER: {{ .Values.provider | default "ollama" | quote }}
EMBEDDING_MODEL: {{ .Values.embeddingModel | quote }}
LLM_MODEL: {{ .Values.llmModel | quote }}
{{- if eq .Values.mode "ollama" }}
OLLAMA_BASE_URL: {{ printf "http://%s:%v" (include "tkeir-inference.fullname" .) .Values.ollama.service.port | quote }}
{{- else if and (eq .Values.mode "external") .Values.external.openaiBaseUrl }}
OPENAI_BASE_URL: {{ .Values.external.openaiBaseUrl | quote }}
{{- else if eq .Values.mode "vllm" }}
PROVIDER: "openai"
OPENAI_BASE_URL: {{ printf "http://%s:8000/v1" (include "tkeir-inference.fullname" .) | quote }}
{{- end }}
{{- end -}}
