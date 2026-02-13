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
- **CRD analysis** - Optional `--check-crds` mode performs deep analysis of CustomResourceDefinition changes: graduated risk classification, stored-version safety checks, ownership conflict detection, live CR schema validation, and configurable policy enforcement (`--crd-policy ignore|warn|fail`).

## Requirements

- Python 3.10+
- `helm` CLI available on PATH
- `kubectl` CLI available on PATH (required for `--server-side` and `--check-crds` modes)
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
| `--check-crds` | | Enable CRD analysis (disabled by default) |
| `--crd-policy` | | CRD policy mode: `ignore`, `warn` (default), or `fail` |

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

Enable CRD analysis:

```bash
helm-preview diff my-app ./chart -n production --check-crds
```

Block the pipeline on dangerous CRD changes:

```bash
helm-preview diff my-app ./chart -n production --check-crds --crd-policy fail
```

## CRD analysis

When `--check-crds` is enabled, `helm-preview` performs a deep analysis of every `CustomResourceDefinition` included in the upgrade. This is disabled by default because it requires additional cluster access (`kubectl get crds`, `kubectl get <crs>`).

### How to use it

```bash
# Basic CRD analysis (warns about issues, never blocks)
helm-preview diff my-release ./chart -n production --check-crds

# JSON output with CRD analysis included
helm-preview diff my-release ./chart -n production --check-crds -o json

# Block the pipeline if any DANGER-level CRD change is detected
helm-preview diff my-release ./chart -n production --check-crds --crd-policy fail

# Suppress all CRD warnings
helm-preview diff my-release ./chart -n production --check-crds --crd-policy ignore
```

### What it checks

The CRD pipeline runs 10 analysis steps automatically:

1. **Extract proposed CRDs** from the rendered upgrade manifests and the chart's `crds/` directory.
2. **Discover installed CRDs** from the cluster via `kubectl get crds`. If the cluster is unreachable or permissions are insufficient, a warning is emitted and analysis continues against an empty set.
3. **Pair** installed vs proposed CRDs by `metadata.name`.
4. **Diff** each pair using the same noise-filtered, normalized engine as regular resources, with additional CRD-specific noise paths.
5. **Classify** every field change into a graduated risk level (see table below).
6. **Detect new CRDs** that exist in the proposed set but are not yet installed.
7. **Check ownership** — flags conflicts when a CRD is managed by a different Helm release, ArgoCD, or Flux.
8. **Validate live CRs** — fetches existing custom resource instances from the cluster and validates them against the proposed schema. Reports fields that would fail validation after the upgrade.
9. **Check stored-version safety** — reads `status.storedVersions` from the installed CRD and warns if a version being removed still has stored objects.
10. **Evaluate policy** — applies the `--crd-policy` mode to decide whether to block.

### CRD risk classification

Each field change in a CRD is classified into one of three risk levels:

| Path pattern | Change type | Risk | Reason |
|---|---|---|---|
| `metadata.annotations.*` / `metadata.labels.*` | any | SAFE | Cosmetic metadata |
| `spec.versions[N].additionalPrinterColumns` | any | SAFE | Display-only columns |
| `spec.versions[N]` | added | SAFE | New version, non-breaking |
| `spec.versions[N].schema.*.properties.*.properties.*` | added | SAFE | New optional property |
| `spec.versions[N].schema.*.properties.*.default` | value changed | WARNING | May change behavior of existing CRs |
| `spec.versions[N].schema.*.properties.*.pattern` | value changed | WARNING | Tighter validation |
| `spec.versions[N].schema.*.properties.*.minimum/maximum` | value changed | WARNING | Range change |
| `spec.versions[N].schema.*.properties.*.enum` | any | WARNING | Enum values changed |
| `spec.conversion.webhook.*` | any | WARNING | Webhook config changed |
| `spec.versions[N].schema.*.required` | item added | DANGER | New required field breaks existing CRs |
| `spec.versions[N].schema.*.properties.*` | removed | DANGER | Removed field |
| `spec.versions[N].schema.*.properties.*.type` | value changed | DANGER | Type change |
| `spec.versions[N]` | removed | DANGER | Removed version |
| `spec.scope` | value changed | DANGER | Namespaced ↔ Cluster |
| `spec.conversion.strategy` | value changed | DANGER | Conversion strategy change |
| Everything else | any | WARNING | Unknown CRD change |

### Policy modes

The `--crd-policy` flag controls what happens when CRD issues are found:

| Mode | Behavior |
|------|----------|
| `ignore` | All CRD issues are suppressed. The pipeline never blocks. |
| `warn` (default) | Issues are displayed in the output but the exit code is always `0`. |
| `fail` | If any CRD has a **DANGER**-level change, the command exits with code `1`. Useful as a CI/CD gate. |

### Terminal output

When `--check-crds` is active, a **CRD Analysis** section is rendered after the regular resource changes and before the summary. It includes:

- A table of CRD changes with name, status, and risk level
- New CRDs not yet installed in the cluster
- Ownership conflicts
- Stored-version warnings
- Schema validation issues (live CRs that would fail against the new schema)
- The policy decision

### JSON output

When using `-o json` with `--check-crds`, a `crd_analysis` top-level key is added:

```json
{
  "summary": { "..." : "..." },
  "risk_summary": { "..." : "..." },
  "changes": [ "..." ],
  "crd_analysis": {
    "crds": [
      {
        "name": "mycrs.example.com",
        "status": "changed",
        "max_risk": "danger",
        "risk_annotations": [
          {
            "level": "danger",
            "rule": "crd_version_removed",
            "message": "CRD version removed",
            "path": "spec.versions[0]"
          }
        ],
        "changes": [
          {
            "path": "spec.versions[0]",
            "old": { "name": "v1alpha1", "..." : "..." },
            "new": null,
            "type": "item_removed"
          }
        ],
        "stored_version_warnings": [
          "Stored version 'v1alpha1' is still in status.storedVersions but is being removed..."
        ],
        "schema_validation_errors": [
          "default/my-instance: At 'spec': missing required field 'mode'"
        ]
      }
    ],
    "new_crds": [
      {
        "name": "externalconfigs.dep.example.com",
        "group": "dep.example.com",
        "kind": "ExternalConfig",
        "versions": ["v1"]
      }
    ],
    "policy": {
      "mode": "warn",
      "blocked": false,
      "message": "CRD policy: warn - 1 CRD(s) with DANGER-level changes: mycrs.example.com"
    },
    "warnings": []
  }
}
```

### Required permissions

CRD analysis requires the following RBAC permissions in the target cluster:

- `get`, `list` on `customresourcedefinitions` (to discover installed CRDs)
- `get`, `list` on the specific CR types being validated (to fetch live instances for schema validation)

If permissions are missing, `helm-preview` emits a warning and continues with reduced analysis rather than failing.

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
