"""Default noise filters, risk rules, and settings."""

from __future__ import annotations

# Dot-paths to strip before diffing. Supports glob on leaf keys via fnmatch.
NOISE_PATHS: set[str] = {
    "metadata.creationTimestamp",
    "metadata.resourceVersion",
    "metadata.uid",
    "metadata.generation",
    "metadata.managedFields",
    "metadata.annotations.meta\\.helm\\.sh/*",
    "metadata.annotations.kubectl\\.kubernetes\\.io/last-applied-configuration",
    "metadata.labels.helm\\.sh/chart",
    "status",
}

# Known immutable fields per Kind (lowercase kind → list of dot-paths)
IMMUTABLE_FIELDS: dict[str, list[str]] = {
    "deployment": ["spec.selector"],
    "daemonset": ["spec.selector"],
    "service": ["spec.clusterIP"],
    "persistentvolumeclaim": ["spec.storageClassName", "spec.accessModes", "spec.volumeName"],
    "job": ["spec.selector", "spec.template"],
    "statefulset": [
        "spec.selector", "spec.serviceName", "spec.podManagementPolicy",
        "spec.volumeClaimTemplates",
    ],
}

# Lists that should be sorted by a known key before comparison
UNORDERED_LIST_SORT_KEYS: dict[str, str] = {
    "spec.template.spec.containers.*.env": "name",
    "spec.template.spec.containers.*.ports": "containerPort",
    "spec.template.spec.containers.*.volumeMounts": "mountPath",
    "spec.template.spec.volumes": "name",
    "spec.template.spec.initContainers.*.env": "name",
    "spec.template.spec.initContainers.*.ports": "containerPort",
    "spec.ports": "port",
}

# Default subprocess timeout in seconds
DEFAULT_TIMEOUT = 60
