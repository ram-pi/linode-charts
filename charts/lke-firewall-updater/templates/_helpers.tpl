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
Selector labels — used for matchLabels in Deployment pod selectors.
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
── Backward-compatibility resolvers ──────────────────────────────────────────
These helpers coalesce v0.2.x providers.linode.* keys with the deprecated
v0.1.x top-level keys so that existing --set linodeToken=X / firewall.ids=[N]
invocations continue to work without modification.
*/}}

{{/*
Resolved Linode API token: new path takes precedence over legacy linodeToken.
coalesce skips nil but NOT empty strings, so use explicit conditionals to
avoid passing "" as the secret data value.
*/}}
{{- define "lke-firewall-updater.resolvedLinodeToken" -}}
{{- if .Values.providers.linode.token -}}
{{- .Values.providers.linode.token -}}
{{- else if .Values.linodeToken -}}
{{- .Values.linodeToken -}}
{{- end -}}
{{- end }}

{{/*
Resolved Linode existing secret: new path takes precedence over legacy existingSecret.
coalesce skips nil but NOT empty strings, so use explicit conditionals to
avoid returning "" which would be treated as a valid (but empty) secret name.
*/}}
{{- define "lke-firewall-updater.resolvedLinodeExistingSecret" -}}
{{- if .Values.providers.linode.existingSecret -}}
{{- .Values.providers.linode.existingSecret -}}
{{- else if .Values.existingSecret -}}
{{- .Values.existingSecret -}}
{{- end -}}
{{- end }}

{{/*
Resolved Linode secret key.
*/}}
{{- define "lke-firewall-updater.resolvedLinodeSecretKey" -}}
{{- coalesce .Values.providers.linode.secretKey .Values.secretKey | default "token" }}
{{- end }}

{{/*
Resolved Linode firewall IDs as a space-separated string of integers.
Helm stores JSON numbers as float64, so large integers like 4015277 are
serialised as "4.015277e+06" by default. Converting each value with `int`
before joining ensures they are emitted as plain integers (e.g. "4015277 67890").
*/}}
{{- define "lke-firewall-updater.resolvedFirewallIds" -}}
{{- $rawIds := coalesce .Values.providers.linode.firewall.ids .Values.firewall.ids }}
{{- $ids := list -}}
{{- range $rawIds -}}
{{- $ids = append $ids (toString (int .)) -}}
{{- end -}}
{{- join " " $ids -}}
{{- end }}

{{/*
Resolved Linode firewall rule name.
*/}}
{{- define "lke-firewall-updater.resolvedRuleName" -}}
{{- coalesce .Values.providers.linode.firewall.ruleName .Values.firewall.ruleName | default "lke-nodes" }}
{{- end }}

{{/*
Resolved Linode firewall protocol.
*/}}
{{- define "lke-firewall-updater.resolvedProtocol" -}}
{{- coalesce .Values.providers.linode.firewall.protocol .Values.firewall.protocol | default "TCP" }}
{{- end }}

{{/*
Resolved Linode firewall ports.
*/}}
{{- define "lke-firewall-updater.resolvedPorts" -}}
{{- coalesce .Values.providers.linode.firewall.ports .Values.firewall.ports | default "1-65535" }}
{{- end }}

{{/*
Resolved Linode firewall action.
*/}}
{{- define "lke-firewall-updater.resolvedAction" -}}
{{- coalesce .Values.providers.linode.firewall.action .Values.firewall.action | default "ACCEPT" }}
{{- end }}

{{/*
── Provider secret name helpers ──────────────────────────────────────────────
Each returns the name of the Secret that holds credentials for that provider:
either an existing user-supplied Secret or the chart-managed one.
*/}}

{{- define "lke-firewall-updater.linodeSecretName" -}}
{{- $existing := include "lke-firewall-updater.resolvedLinodeExistingSecret" . }}
{{- if and $existing (ne $existing "") }}
{{- $existing }}
{{- else }}
{{- printf "%s-linode" (include "lke-firewall-updater.fullname" .) }}
{{- end }}
{{- end }}

{{- define "lke-firewall-updater.awsSecretName" -}}
{{- if .Values.providers.aws.existingSecret }}
{{- .Values.providers.aws.existingSecret }}
{{- else }}
{{- printf "%s-aws" (include "lke-firewall-updater.fullname" .) }}
{{- end }}
{{- end }}

{{- define "lke-firewall-updater.gcpSecretName" -}}
{{- if .Values.providers.gcp.existingSecret }}
{{- .Values.providers.gcp.existingSecret }}
{{- else }}
{{- printf "%s-gcp" (include "lke-firewall-updater.fullname" .) }}
{{- end }}
{{- end }}

{{/*
Container startup args — installs only the runtime deps required for the
enabled providers, then executes the controller script.
Linode + AWS: stock Alpine + curl + jq + aws-cli (all available in apk).
GCP: user must override controller.image to google/cloud-sdk:alpine since
     gcloud is not available via apk. aws-cli is still added if AWS is also enabled.
*/}}
{{- define "lke-firewall-updater.containerArgs" -}}
{{- $deps := list "curl" "jq" -}}
{{- if .Values.providers.aws.enabled -}}
{{- $deps = append $deps "aws-cli" -}}
{{- end -}}
{{- printf "apk add --no-cache %s >/dev/null 2>&1 && /scripts/controller.sh" (join " " $deps) -}}
{{- end }}
