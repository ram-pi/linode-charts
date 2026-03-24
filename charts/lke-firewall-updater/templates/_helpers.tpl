{{/*
Expand the name of the chart.
*/}}
{{- define "lke-firewall-updater.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "lke-firewall-updater.fullname" -}}
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
{{- define "lke-firewall-updater.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels applied to every resource.
*/}}
{{- define "lke-firewall-updater.labels" -}}
helm.sh/chart: {{ include "lke-firewall-updater.chart" . }}
{{ include "lke-firewall-updater.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- with .Values.commonLabels }}
{{ toYaml . }}
{{- end }}
{{- end }}

{{/*
Selector labels — used for matchLabels in DaemonSet/CronJob pod selectors.
*/}}
{{- define "lke-firewall-updater.selectorLabels" -}}
app.kubernetes.io/name: {{ include "lke-firewall-updater.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
ServiceAccount name.
*/}}
{{- define "lke-firewall-updater.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "lke-firewall-updater.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}

{{/*
Firewall IDs as a space-separated string of integers.
Helm stores JSON numbers as float64, so large integers like 4015277 are serialised
as "4.015277e+06" by default. Converting each value with `int` before joining
ensures they are emitted as plain integers (e.g. "4015277 67890").
*/}}
{{- define "lke-firewall-updater.firewallIds" -}}
{{- $ids := list -}}
{{- range .Values.firewall.ids -}}
{{- $ids = append $ids (toString (int .)) -}}
{{- end -}}
{{- join " " $ids -}}
{{- end }}

{{/*
Name of the Secret that holds the Linode API token.
Returns existingSecret when provided, otherwise the chart-managed Secret name.
*/}}
{{- define "lke-firewall-updater.secretName" -}}
{{- if .Values.existingSecret }}
{{- .Values.existingSecret }}
{{- else }}
{{- include "lke-firewall-updater.fullname" . }}
{{- end }}
{{- end }}
