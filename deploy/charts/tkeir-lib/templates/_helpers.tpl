{{/*
Expand the name of the chart.
*/}}
{{- define "tkeir-lib.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "tkeir-lib.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- $name := default .Chart.Name .Values.nameOverride -}}
{{- if contains $name .Release.Name -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{/*
Common labels
*/}}
{{- define "tkeir-lib.labels" -}}
helm.sh/chart: {{ include "tkeir-lib.chart" . }}
{{ include "tkeir-lib.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/part-of: tkeir
{{- end -}}

{{- define "tkeir-lib.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "tkeir-lib.selectorLabels" -}}
app.kubernetes.io/name: {{ include "tkeir-lib.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{/*
Restricted Pod Security defaults (PSS restricted-compatible).
*/}}
{{- define "tkeir-lib.securityContext" -}}
runAsNonRoot: true
runAsUser: {{ .Values.securityContext.runAsUser | default 10001 }}
runAsGroup: {{ .Values.securityContext.runAsGroup | default 10001 }}
fsGroup: {{ .Values.securityContext.fsGroup | default 10001 }}
seccompProfile:
  type: RuntimeDefault
{{- end -}}

{{- define "tkeir-lib.containerSecurityContext" -}}
allowPrivilegeEscalation: false
readOnlyRootFilesystem: {{ .Values.securityContext.readOnlyRootFilesystem | default true }}
capabilities:
  drop:
    - ALL
{{- end -}}

{{/*
HTTP probes — path defaults to /health.
*/}}
{{- define "tkeir-lib.livenessProbe" -}}
httpGet:
  path: {{ .path | default "/health" }}
  port: {{ .port }}
initialDelaySeconds: {{ .initialDelaySeconds | default 30 }}
periodSeconds: {{ .periodSeconds | default 20 }}
timeoutSeconds: {{ .timeoutSeconds | default 5 }}
failureThreshold: {{ .failureThreshold | default 6 }}
{{- end -}}

{{- define "tkeir-lib.readinessProbe" -}}
httpGet:
  path: {{ .path | default "/ready" }}
  port: {{ .port }}
initialDelaySeconds: {{ .initialDelaySeconds | default 20 }}
periodSeconds: {{ .periodSeconds | default 10 }}
timeoutSeconds: {{ .timeoutSeconds | default 5 }}
failureThreshold: {{ .failureThreshold | default 6 }}
{{- end -}}
