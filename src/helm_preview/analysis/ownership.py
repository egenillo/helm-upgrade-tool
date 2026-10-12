"""Ownership detection (Helm, ArgoCD, Flux)."""

from __future__ import annotations

from dataclasses import dataclass

from helm_preview.parser.manifest import Resource


@dataclass
class OwnershipInfo:
    manager: str  # "helm", "argocd", "flux", "unknown"
    release: str | None = None
    app: str | None = None


def detect_ownership(resource: Resource) -> OwnershipInfo:
    """Check annotations/labels to determine resource ownership.

    GitOps controllers are checked before Helm: ArgoCD and Flux both render
    Helm charts, so their resources usually also carry
    app.kubernetes.io/managed-by=Helm.

    Checks:
    - argocd.argoproj.io/tracking-id (annotation) / argocd.argoproj.io/instance (label)
    - *.toolkit.fluxcd.io/* and fluxcd.io/* labels/annotations
    - app.kubernetes.io/managed-by / meta.helm.sh/release-name
    """
    metadata = resource.body.get("metadata") or {}
    labels = metadata.get("labels") or {}
    annotations = metadata.get("annotations") or {}

    # ArgoCD detection (tracking-id format: "<app>:<group>/<kind>:<ns>/<name>")
    argocd_app = labels.get("argocd.argoproj.io/instance")
    tracking_id = annotations.get("argocd.argoproj.io/tracking-id")
    if not argocd_app and isinstance(tracking_id, str):
        argocd_app = tracking_id.split(":", 1)[0]
    if argocd_app:
        return OwnershipInfo(
            manager="argocd",
            app=str(argocd_app),
        )

    # Flux detection
    flux_keys = [k for k in (*annotations, *labels) if "fluxcd.io" in k]
    if flux_keys:
        return OwnershipInfo(manager="flux")

    # Helm detection
    managed_by = str(labels.get("app.kubernetes.io/managed-by") or "")
    helm_release = annotations.get("meta.helm.sh/release-name")
    if managed_by.lower() == "helm" or helm_release:
        return OwnershipInfo(
            manager="helm",
            release=helm_release or labels.get("app.kubernetes.io/instance"),
        )

    return OwnershipInfo(manager="unknown")
