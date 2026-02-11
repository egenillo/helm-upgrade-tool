# helm-preview

Semantic, noise-filtered, risk-aware diffs for Helm upgrades.

`helm-preview` compares your live Helm release against a proposed upgrade and produces a clear, actionable diff. It strips Kubernetes noise fields, detects risky changes, identifies resource ownership, and outputs results as a rich terminal display or structured JSON for CI/CD pipelines.

## Features

- **Noise filtering** - Automatically strips `resourceVersion`, `uid`, `creationTimestamp`, `managedFields`, Helm bookkeeping annotations, and other fields that change on every apply but carry no semantic meaning.
- **Semantic comparison** - Handles numeric strings vs integers (`"80"` vs `80`), boolean strings vs bools (`"true"` vs `true`), and normalizes unordered lists (env vars, ports, volumes) before diffing.
- **Risk analysis** - Flags dangerous changes with `[WARNING]` and `[DANGER]` badges: immutable field mutations, Service type escalation, PVC storage class changes, resource deletions, CRD schema changes, and RBAC rule modifications.
- **Ownership detection** - Identifies whether resources are managed by Helm, ArgoCD, or Flux via standard labels and annotations.
- **Server-side truth diff** - Optional `--server-side` mode sends rendered manifests through `kubectl apply --dry-run=server` to capture admission webhook mutations before diffing.
- **Structured JSON output** - Machine-readable output with summaries, risk annotations, and per-field changes for integration into CI/CD gates.

## Requirements

- Python 3.10+
- `helm` CLI available on PATH
- `kubectl` CLI available on PATH (only required for `--server-side` mode)
- An active kubeconfig context with access to the target cluster

## Installation

```bash
pip install -e .
```


## Usage

After installation, the `helm-preview` command is available directly:

```
helm-preview diff <RELEASE> <CHART> [flags]
```

Alternatively, you can run it as a Python module:

```
python -m helm_preview diff <RELEASE> <CHART> [flags]
```

### Quick start: end-to-end example

A demo chart is included in the `demo/` directory to try `helm-preview` against a real cluster.

**What's in the demo**

```
demo/
├── demo-app/              # Helm chart
│   ├── Chart.yaml
│   ├── values.yaml        # Default values (v1)
│   └── templates/
│       ├── deployment.yaml
│       ├── service.yaml
│       └── configmap.yaml
└── values-upgrade.yaml    # Upgrade values (v2)
```

**Changes between v1 and v2**

| What | Before | After | Risk |
|------|--------|-------|------|
| Replicas | 2 | 5 | - |
| Image tag | 1.24 | 1.25 | - |
| Service type | ClusterIP | **NodePort** | DANGER |
| CPU request | 100m | 200m | - |
| CPU limit | 250m | 500m | - |
| Memory limit | 256Mi | 512Mi | - |
| LOG_LEVEL | info | debug | - |
| FEATURE_FLAG | *(missing)* | true | - |
| ConfigMap text | v1 | v2 - upgraded! | - |

**Step 1** - Install the chart into your cluster:

```bash
helm install demo-release ./demo/demo-app -n default
```

**Step 2** - Preview the upgrade with `helm-preview`:

```bash
helm-preview diff demo-release ./demo/demo-app -n default -f ./demo/values-upgrade.yaml
```

Terminal output:

![helm-preview terminal output](images/showall.JPG)

**Step 3** - Try JSON output for CI/CD integration:

```bash
helm-preview diff demo-release ./demo/demo-app -n default -f ./demo/values-upgrade.yaml -o json
```

```json
{
  "summary": {
    "added": 0,
    "removed": 0,
    "changed": 3,
    "unchanged": 0
  },
  "risk_summary": {
    "safe": 2,
    "warning": 0,
    "danger": 1
  },
  "changes": [
    {
      "resource": "v1/ConfigMap/default/demo-release-config",
      "kind": "ConfigMap",
      "name": "demo-release-config",
      "namespace": "default",
      "status": "changed",
      "risk": [],
      "ownership": {
        "manager": "helm",
        "release": null,
        "app": null
      },
      "fields": [
        {
          "path": "data.welcome.txt",
          "old": "Hello from demo-app v1",
          "new": "Hello from demo-app v2 - upgraded!",
          "type": "value_changed"
        }
      ]
    },
    {
      "resource": "v1/Service/default/demo-release",
      "kind": "Service",
      "name": "demo-release",
      "namespace": "default",
      "status": "changed",
      "risk": [
        {
          "level": "danger",
          "rule": "service_type_change",
          "message": "Service type changed from ClusterIP to NodePort",
          "path": "spec.type"
        }
      ],
      "ownership": {
        "manager": "helm",
        "release": null,
        "app": null
      },
      "fields": [
        {
          "path": "spec.type",
          "old": "ClusterIP",
          "new": "NodePort",
          "type": "value_changed"
        }
      ]
    },
    {
      "resource": "apps/v1/Deployment/default/demo-release",
      "kind": "Deployment",
      "name": "demo-release",
      "namespace": "default",
      "status": "changed",
      "risk": [],
      "ownership": {
        "manager": "helm",
        "release": null,
        "app": null
      },
      "fields": [
        {
          "path": "spec.replicas",
          "old": 2,
          "new": 5,
          "type": "value_changed"
        },
        {
          "path": "spec.template.spec.containers[0].env[1].name",
          "old": "LOG_LEVEL",
          "new": "FEATURE_FLAG",
          "type": "value_changed"
        },
        {
          "path": "spec.template.spec.containers[0].env[1].value",
          "old": "info",
          "new": "true",
          "type": "value_changed"
        },
        {
          "path": "spec.template.spec.containers[0].image",
          "old": "nginx:1.24",
          "new": "nginx:1.25",
          "type": "value_changed"
        },
        {
          "path": "spec.template.spec.containers[0].resources.limits.cpu",
          "old": "250m",
          "new": "500m",
          "type": "value_changed"
        },
        {
          "path": "spec.template.spec.containers[0].resources.limits.memory",
          "old": "256Mi",
          "new": "512Mi",
          "type": "value_changed"
        },
        {
          "path": "spec.template.spec.containers[0].resources.requests.cpu",
          "old": "100m",
          "new": "200m",
          "type": "value_changed"
        },
        {
          "path": "spec.template.spec.containers[0].env[2]",
          "old": null,
          "new": {
            "name": "LOG_LEVEL",
            "value": "debug"
          },
          "type": "item_added"
        }
      ]
    }
  ]
}
```

**Step 4** - Other useful modes:

```bash
# Only show risky changes (the Service type change)
helm-preview diff demo-release ./demo/demo-app -n default -f ./demo/values-upgrade.yaml --risk-only

# Raw diff without noise filtering
helm-preview diff demo-release ./demo/demo-app -n default -f ./demo/values-upgrade.yaml --show-all

# Using python -m instead of the entry point
python -m helm_preview diff demo-release ./demo/demo-app -n default -f ./demo/values-upgrade.yaml
```


The <CHART> argument points to the entire chart directory, not just values. The underlying command is:

  helm upgrade <release> <chart> --dry-run                                                                                                                                                                                                   
  Helm renders all templates in the chart against the provided values, so any change is captured:                                                                                                                                            
  - Modified templates (e.g. adding a new container, changing a label)
  - New template files (e.g. adding ingress.yaml results in an ADDED resource)
  - Deleted template files (results in a REMOVED resource)
  - Changes to Chart.yaml (appVersion, dependencies)
  - Changes to helpers (_helpers.tpl)
  - Changes to default values.yaml inside the chart


### When the upgrade include several changes in files of the helm chart

  The demo uses -f values-upgrade.yaml because that's the most common upgrade scenario where only the values file changed, demo-app folder is used to deploy the first version but is also used to compare as the new version.
   
  If you have a new helm chart for the upgrade where not only the values file changed then you can run:

  ```bash
  helm-preview diff demo-release ./demo/demo-app-v2 -n default
  ```

  where demo-app-v2 is the new version of the chart — no -f flag needed. You can also combine both: a modified chart and a values override file together.

### Positional arguments

| Argument  | Description                                    |
|-----------|------------------------------------------------|
| `RELEASE` | Helm release name                              |
| `CHART`   | Chart reference (local path, repo/chart, OCI URL) |

### Flags

| Flag | Short | Description |
|------|-------|-------------|
| `--namespace` | `-n` | Kubernetes namespace (default: `default`) |
| `--values` | `-f` | Values file(s), can be repeated |
| `--set` | | Set individual values (`key=val`), can be repeated |
| `--version` | | Chart version to upgrade to |
| `--server-side` | | Enable truth-diff mode (server-side dry-run) |
| `--show-all` | | Disable noise filtering, show raw diff |
| `--output` | `-o` | Output format: `terminal` (default) or `json` |
| `--context` | | Lines of context around changes (default: `3`) |
| `--ignore-path` | | Additional dot-paths to ignore, can be repeated |
| `--kubeconfig` | | Path to kubeconfig file |
| `--kube-context` | | Kubernetes context to use |
| `--no-color` | | Disable colored output |
| `--risk-only` | | Only show changes with WARNING or DANGER risk level |

### Examples

Preview a basic upgrade:

```bash
helm-preview diff my-app ./charts/my-app -n production
```

Preview with custom values:

```bash
helm-preview diff my-app bitnami/nginx -n staging \
  -f values-staging.yaml \
  --set image.tag=2.0.0
```

JSON output for CI/CD:

```bash
helm-preview diff my-app oci://registry.example.com/charts/my-app \
  -n production \
  -o json \
  --version 3.2.1
```

Server-side truth diff (captures webhook mutations):

```bash
helm-preview diff my-app ./chart -n production --server-side
```

Show only risky changes:

```bash
helm-preview diff my-app ./chart -n production --risk-only
```

Ignore custom annotation noise:

```bash
helm-preview diff my-app ./chart -n production \
  --ignore-path 'metadata.annotations.example\.com/*'
```

## How it works

```
1. FETCH LIVE        helm get manifest <release> -n <ns>
       |
2. RENDER UPGRADE    helm upgrade <release> <chart> --dry-run -n <ns> [flags]
       |
3. (OPTIONAL)        kubectl apply --dry-run=server  (--server-side mode)
       |
4. PARSE             Split multi-doc YAML, key each resource by
                     apiVersion/kind/namespace/name
       |
5. PAIR              Match old <-> new resources by key
                     Classify as ADDED, REMOVED, CHANGED, or UNCHANGED
       |
6. NORMALIZE         Strip noise fields, sort dict keys,
                     sort unordered lists (env, ports, volumes)
       |
7. DIFF              Structural diff via DeepDiff, semantic equality checks
       |
8. ANALYZE           Run risk rules, detect ownership
       |
9. OUTPUT            Rich terminal display or structured JSON
```

## Noise filtering

The following fields are stripped by default before comparison:

- `metadata.creationTimestamp`
- `metadata.resourceVersion`
- `metadata.uid`
- `metadata.generation`
- `metadata.managedFields`
- `metadata.annotations.meta.helm.sh/*`
- `metadata.annotations.kubectl.kubernetes.io/last-applied-configuration`
- `metadata.labels.helm.sh/chart`
- `status`

Use `--show-all` to disable filtering, or `--ignore-path` to add custom paths to ignore.

## Risk rules

| Rule | Trigger | Level |
|------|---------|-------|
| `immutable_field` | Changes to Deployment `spec.selector.matchLabels`, Service `spec.clusterIP`, PVC `spec.storageClassName`, Job `spec.selector`, StatefulSet `spec.volumeClaimTemplates` | DANGER |
| `service_type_change` | Service type changed from ClusterIP to NodePort/LoadBalancer | DANGER |
| `service_type_change` | Any other Service type change | WARNING |
| `pvc_storage_class_change` | PVC `storageClassName` changed | DANGER |
| `pvc_storage_change` | PVC storage request size changed | WARNING |
| `resource_deleted` | Any resource removed from the release | WARNING |
| `crd_spec_change` | CRD scope, versions, validation, or names changed | DANGER |
| `rbac_change` | ClusterRole or Role rules modified | WARNING |

## JSON output schema

```json
{
  "summary": {
    "added": 2,
    "removed": 1,
    "changed": 5,
    "unchanged": 12
  },
  "risk_summary": {
    "safe": 4,
    "warning": 2,
    "danger": 1
  },
  "changes": [
    {
      "resource": "apps/v1/Deployment/default/my-app",
      "kind": "Deployment",
      "name": "my-app",
      "namespace": "default",
      "status": "changed",
      "risk": [
        {
          "level": "warning",
          "rule": "immutable_field",
          "message": "...",
          "path": "spec.selector.matchLabels"
        }
      ],
      "ownership": {
        "manager": "helm",
        "release": "my-app",
        "app": null
      },
      "fields": [
        {
          "path": "spec.replicas",
          "old": 3,
          "new": 5,
          "type": "value_changed"
        }
      ]
    }
  ]
}
```
