{{/*
Expand the name of the chart.
*/}}
{{- define "lke-vlan-controller-python.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "lke-vlan-controller-python.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Create chart label value (chart name + version).
*/}}
{{- define "lke-vlan-controller-python.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels applied to every resource.
*/}}
{{- define "lke-vlan-controller-python.labels" -}}
helm.sh/chart: {{ include "lke-vlan-controller-python.chart" . }}
{{ include "lke-vlan-controller-python.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- with .Values.commonLabels }}
{{ toYaml . }}
{{- end }}
{{- end }}

{{/*
Selector labels — used for matchLabels in Deployment pod selectors.
*/}}
{{- define "lke-vlan-controller-python.selectorLabels" -}}
app.kubernetes.io/name: {{ include "lke-vlan-controller-python.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
ServiceAccount name.
*/}}
{{- define "lke-vlan-controller-python.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "lke-vlan-controller-python.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}

{{/*
Name of the Secret that holds the Linode API token.
Returns existingSecret when provided, otherwise the chart-managed Secret name.
*/}}
{{- define "lke-vlan-controller-python.secretName" -}}
{{- if .Values.existingSecret }}
{{- .Values.existingSecret }}
{{- else }}
{{- include "lke-vlan-controller-python.fullname" . }}
{{- end }}
{{- end }}

{{/*
Render node selector env string as key=value,key2=value2
*/}}
{{- define "lke-vlan-controller-python.nodeSelectorEnv" -}}
{{- $pairs := list -}}
{{- range $k, $v := .Values.controller.nodeSelector -}}
{{- $pairs = append $pairs (printf "%s=%s" $k $v) -}}
{{- end -}}
{{- join "," $pairs -}}
{{- end }}
