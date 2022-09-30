#!/usr/bin/env bash

set -e

echo "ensure that clusters with cert issuers are well formed"
helm template . \
    --api-versions cert-manager.io/v1/Issuer \
    | kubeconform -schema-location 'https://raw.githubusercontent.com/yannh/kubernetes-json-schema/master/{{ .NormalizedKubernetesVersion }}-standalone{{ .StrictSuffix }}/{{ .ResourceKind }}{{ .KindSuffix }}.json' \
    -ignore-missing-schemas

echo "ensure that clusters without cert issuers are well formed"
helm template . --set caBundle=abc123 \
    | kubeconform -schema-location 'https://raw.githubusercontent.com/yannh/kubernetes-json-schema/master/{{ .NormalizedKubernetesVersion }}-standalone{{ .StrictSuffix }}/{{ .ResourceKind }}{{ .KindSuffix }}.json' \
    -ignore-missing-schemas
