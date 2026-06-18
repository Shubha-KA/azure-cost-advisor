{{- define "finops.labels" -}}
app.kubernetes.io/part-of: azure-cost-advisor
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{- define "finops.selectorLabels" -}}
app.kubernetes.io/name: {{ .name }}
{{- end }}

{{- define "finops.secretProviderClassName" -}}
{{ printf "%s-keyvault" .name }}
{{- end }}

{{- define "finops.exportScript" -}}
set -eu
{{- range $envName, $objectName := .service.keyVaultObjects }}
export {{ $envName }}="$(cat {{ $.Values.global.keyVault.mountPath }}/{{ $objectName }})"
{{- end }}
exec {{ .service.command }}
{{- end }}
