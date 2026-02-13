"""Rich terminal colored output."""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from helm_preview.analysis.ownership import OwnershipInfo
from helm_preview.analysis.risk import RiskAnnotation, RiskLevel
from helm_preview.diff.engine import ChangeRecord, FieldChange

# Style mappings
RISK_STYLES = {
    RiskLevel.SAFE: ("SAFE", "green"),
    RiskLevel.WARNING: ("WARNING", "yellow"),
    RiskLevel.DANGER: ("DANGER", "red bold"),
}

OWNER_STYLES = {
    "helm": ("helm", "blue"),
    "argocd": ("argocd", "magenta"),
    "flux": ("flux", "cyan"),
    "unknown": ("unknown", "dim"),
}

STATUS_STYLES = {
    "added": ("ADDED", "green bold"),
    "removed": ("REMOVED", "red bold"),
    "changed": ("CHANGED", "yellow bold"),
}


def render_terminal(
    results: list[tuple[ChangeRecord, list[RiskAnnotation], OwnershipInfo | None]],
    context_lines: int = 3,
    show_all: bool = False,
    no_color: bool = False,
    risk_only: bool = False,
    crd_report: "CrdReport | None" = None,
) -> None:
    """Print colored diff to terminal."""
    console = Console(no_color=no_color)

    if risk_only:
        results = [
            (cr, ra, oi) for cr, ra, oi in results
            if any(a.level in (RiskLevel.WARNING, RiskLevel.DANGER) for a in ra)
        ]

    if not results and not crd_report:
        console.print("[dim]No changes detected.[/dim]")
        return

    for change, risk_annotations, ownership in results:
        _render_resource(console, change, risk_annotations, ownership)

    # Render CRD analysis section if present
    if crd_report:
        _render_crd_section(console, crd_report)

    _render_summary(console, results, crd_report=crd_report)


def _render_resource(
    console: Console,
    change: ChangeRecord,
    risk_annotations: list[RiskAnnotation],
    ownership: OwnershipInfo | None,
) -> None:
    """Render a single resource change."""
    # Build title line
    status_label, status_style = STATUS_STYLES[change.status]
    title = Text()
    title.append(f"[{status_label}] ", style=status_style)
    title.append(f"{change.kind}/{change.name}", style="bold")
    title.append(f"  ({change.namespace})", style="dim")

    # Badges
    badges = Text()
    if ownership:
        owner_label, owner_style = OWNER_STYLES.get(
            ownership.manager, ("unknown", "dim")
        )
        badges.append(f" [{owner_label}]", style=owner_style)

    # Risk badges
    max_risk = _max_risk(risk_annotations)
    if max_risk:
        risk_label, risk_style = RISK_STYLES[max_risk]
        badges.append(f" [{risk_label}]", style=risk_style)

    title.append(badges)

    if change.status in ("added", "removed"):
        console.print(Panel(title, border_style=status_style.split()[0]))
    else:
        # Show field changes
        content = Text()
        for fc in change.changes:
            _render_field_change(content, fc, risk_annotations)

        panel = Panel(
            content,
            title=title,
            title_align="left",
            border_style="yellow",
        )
        console.print(panel)

    # Show risk details
    for annotation in risk_annotations:
        risk_label, risk_style = RISK_STYLES[annotation.level]
        console.print(
            f"  [{risk_style}]{risk_label}[/{risk_style}]: {annotation.message}"
        )

    console.print()


def _render_field_change(
    content: Text,
    fc: FieldChange,
    risk_annotations: list[RiskAnnotation],
) -> None:
    """Render a single field change."""
    # Check if this field has risk annotations
    field_risks = [a for a in risk_annotations if a.path == fc.path]
    risk_marker = ""
    if field_risks:
        max_level = max(a.level.value for a in field_risks)
        if max_level == RiskLevel.DANGER.value:
            risk_marker = " !!"
        elif max_level == RiskLevel.WARNING.value:
            risk_marker = " !"

    if fc.change_type == "value_changed":
        content.append(f"  ~ {fc.path}{risk_marker}\n", style="yellow")
        content.append(f"    - {_format_value(fc.old_value)}\n", style="red")
        content.append(f"    + {_format_value(fc.new_value)}\n", style="green")
    elif fc.change_type == "type_changed":
        content.append(f"  ~ {fc.path} (type changed){risk_marker}\n", style="yellow")
        content.append(f"    - {_format_value(fc.old_value)} ({type(fc.old_value).__name__})\n", style="red")
        content.append(f"    + {_format_value(fc.new_value)} ({type(fc.new_value).__name__})\n", style="green")
    elif fc.change_type == "item_added":
        content.append(f"  + {fc.path}{risk_marker}\n", style="green")
        content.append(f"    {_format_value(fc.new_value)}\n", style="green")
    elif fc.change_type == "item_removed":
        content.append(f"  - {fc.path}{risk_marker}\n", style="red")
        content.append(f"    {_format_value(fc.old_value)}\n", style="red")


def _format_value(value: object) -> str:
    """Format a value for display, truncating long strings."""
    s = repr(value)
    if len(s) > 120:
        s = s[:117] + "..."
    return s


def _max_risk(annotations: list[RiskAnnotation]) -> RiskLevel | None:
    """Get the highest risk level from a list of annotations."""
    if not annotations:
        return None
    order = {RiskLevel.SAFE: 0, RiskLevel.WARNING: 1, RiskLevel.DANGER: 2}
    return max(annotations, key=lambda a: order[a.level]).level


def _render_crd_section(console: Console, crd_report: "CrdReport") -> None:
    """Render the CRD Analysis section."""
    from helm_preview.crd.report import CrdReport

    console.print()
    console.rule("[bold cyan]CRD Analysis[/bold cyan]")
    console.print()

    # CRD changes table
    if crd_report.crds:
        table = Table(title="CRD Changes", show_header=True)
        table.add_column("CRD Name", style="bold")
        table.add_column("Status")
        table.add_column("Risk")
        table.add_column("Details")

        for crd in crd_report.crds:
            status_label, status_style = STATUS_STYLES.get(
                crd.status, ("UNKNOWN", "dim")
            )
            risk_label, risk_style = RISK_STYLES.get(
                crd.max_risk, ("SAFE", "green")
            )
            details = f"{len(crd.changes)} change(s)" if crd.changes else ""
            table.add_row(
                crd.name,
                f"[{status_style}]{status_label}[/{status_style}]",
                f"[{risk_style}]{risk_label}[/{risk_style}]",
                details,
            )

        console.print(table)
        console.print()

    # New CRDs
    if crd_report.new_crds:
        console.print("[bold green]New CRDs:[/bold green]")
        for new_crd in crd_report.new_crds:
            versions_str = ", ".join(new_crd.versions)
            console.print(
                f"  + {new_crd.name} ({new_crd.kind}) "
                f"[dim]versions: {versions_str}[/dim]"
            )
        console.print()

    # Ownership conflicts
    conflicts = [c for c in crd_report.crds if c.ownership_conflict]
    if conflicts:
        console.print("[bold yellow]Ownership Conflicts:[/bold yellow]")
        for crd in conflicts:
            console.print(f"  [yellow]![/yellow] {crd.ownership_conflict}")
        console.print()

    # Stored-version warnings
    sv_warnings = [
        (c.name, w)
        for c in crd_report.crds
        for w in c.stored_version_warnings
    ]
    if sv_warnings:
        console.print("[bold yellow]Stored Version Warnings:[/bold yellow]")
        for name, warning in sv_warnings:
            console.print(f"  [yellow]![/yellow] {name}: {warning}")
        console.print()

    # Schema validation issues
    schema_errors = [
        (c.name, e)
        for c in crd_report.crds
        for e in c.schema_validation_errors
    ]
    if schema_errors:
        console.print("[bold red]Schema Validation Issues:[/bold red]")
        for name, error in schema_errors:
            console.print(f"  [red]!![/red] {name}: {error}")
        console.print()

    # Risk details for each CRD
    for crd in crd_report.crds:
        if crd.risk_annotations:
            for annotation in crd.risk_annotations:
                risk_label, risk_style = RISK_STYLES[annotation.level]
                console.print(
                    f"  [{risk_style}]{risk_label}[/{risk_style}] "
                    f"{crd.name}: {annotation.message}"
                )

    # General warnings
    for warning in crd_report.warnings:
        console.print(f"  [dim]Warning: {warning}[/dim]")

    # Policy decision
    if crd_report.policy_result:
        pr = crd_report.policy_result
        if pr.blocked:
            console.print(f"\n  [red bold]{pr.message}[/red bold]")
        else:
            console.print(f"\n  [dim]{pr.message}[/dim]")

    console.print()


def _render_summary(
    console: Console,
    results: list[tuple[ChangeRecord, list[RiskAnnotation], OwnershipInfo | None]],
    crd_report: "CrdReport | None" = None,
) -> None:
    """Render summary table at the bottom."""
    added = sum(1 for cr, _, _ in results if cr.status == "added")
    removed = sum(1 for cr, _, _ in results if cr.status == "removed")
    changed = sum(1 for cr, _, _ in results if cr.status == "changed")
    warnings = sum(
        sum(1 for a in ra if a.level == RiskLevel.WARNING) for _, ra, _ in results
    )
    dangers = sum(
        sum(1 for a in ra if a.level == RiskLevel.DANGER) for _, ra, _ in results
    )

    table = Table(title="Summary", show_header=False, box=None)
    table.add_row("[green]Added[/green]", str(added))
    table.add_row("[red]Removed[/red]", str(removed))
    table.add_row("[yellow]Changed[/yellow]", str(changed))
    if warnings:
        table.add_row("[yellow]Warnings[/yellow]", str(warnings))
    if dangers:
        table.add_row("[red bold]Dangers[/red bold]", str(dangers))

    if crd_report:
        crd_changed = sum(1 for c in crd_report.crds if c.status == "changed")
        crd_new = len(crd_report.new_crds)
        if crd_changed or crd_new:
            table.add_row("[cyan]CRDs Changed[/cyan]", str(crd_changed))
            if crd_new:
                table.add_row("[cyan]CRDs New[/cyan]", str(crd_new))

    console.print(table)
