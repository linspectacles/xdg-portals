#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# LinSpectacles - Linux Inspection Suite
# Copyright (C) 2026 brunonlinespace
# GPL-3.0-or-later

APPLET_ID = "linspectacles-xdg-portals"
APPLET_NAME = "XDG Portals"
APPLET_VERSION = "0.0.3"
APPLET_AUTHOR = "brunonlinespace"
APPLET_EDITOR = "brunonlinespace"
APPLET_PUBLISHER = "brunonlinespace"
APPLET_ORGANIZATION_ID = "linspectacles"
APPLET_ORGANIZATION_URL = "https://github.com/linspectacles/"
APPLET_REPOSITORY = "https://github.com/linspectacles/xdg-portals"
APPLET_LAYER = "Desktop Environment"

import configparser
import os
import shutil
import subprocess
from pathlib import Path

from PyQt6.QtCore import QSettings, Qt, QUrl
from PyQt6.QtGui import QBrush, QColor, QFont, QKeySequence, QPixmap, QShortcut, QTextCharFormat, QTextCursor
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ._support import (
    BaseInspectorTab,
    ColumnVisibilityController,
    apply_metadata_font,
    export_records_dialog,
    metadata_font_qss,
)


VIEWS = ("Overview", "Backends", "Interfaces", "Configuration", "Runtime")

VIEW_COLUMNS = {
    "Overview": [
        ("item", "Item", 210, "left"),
        ("value", "Value", 310, "left"),
        ("source", "Source", 240, "left"),
    ],
    "Backends": [
        ("backend", "Backend", 150, "left"),
        ("dbus_name", "D-Bus Name", 280, "left"),
        ("interfaces_display", "Interfaces", 260, "left"),
        ("use_in", "UseIn", 150, "left"),
        ("source", "Source", 300, "left"),
    ],
    "Interfaces": [
        ("interface", "Interface", 310, "left"),
        ("backend", "Backend", 150, "left"),
        ("selected", "Selected", 95, "left"),
        ("dbus_name", "D-Bus Name", 280, "left"),
        ("source", "Source", 300, "left"),
    ],
    "Configuration": [
        ("config_file", "Config File", 230, "left"),
        ("scope", "Scope", 130, "left"),
        ("desktop", "Desktop", 120, "left"),
        ("default_backends", "Default Backends", 190, "left"),
        ("overrides_display", "Overrides", 180, "left"),
        ("effective_state", "Effective / Shadowed", 150, "left"),
    ],
    "Runtime": [
        ("bus_name", "Bus Name", 310, "left"),
        ("role", "Role", 100, "left"),
        ("owner", "Owner / Unique Name", 170, "left"),
        ("pid", "PID", 85, "right"),
        ("component", "Backend / Frontend", 190, "left"),
        ("state", "State", 100, "left"),
    ],
}


def _split_semicolon(value):
    return [item.strip() for item in str(value or "").split(";") if item.strip()]


def _split_colon(value):
    return [item.strip() for item in str(value or "").split(":") if item.strip()]


def _absolute_path(value, default):
    raw = str(value or "").strip()
    if raw and os.path.isabs(os.path.expanduser(raw)):
        return os.path.expanduser(raw)
    return os.path.expanduser(default)


def _absolute_path_list(value, default):
    raw = str(value or "").strip()
    parts = _split_colon(raw) if raw else _split_colon(default)
    result = []
    for part in parts:
        expanded = os.path.expanduser(part)
        if os.path.isabs(expanded) and expanded not in result:
            result.append(expanded)
    if not result and raw:
        for part in _split_colon(default):
            expanded = os.path.expanduser(part)
            if os.path.isabs(expanded) and expanded not in result:
                result.append(expanded)
    return result


def _desktop_values():
    raw = os.environ.get("XDG_CURRENT_DESKTOP", "")
    return [item for item in _split_colon(raw)]


def _pkg_config_portal_path(variable):
    """Read build metadata only; never invoke or activate the portal service."""
    tool = shutil.which("pkg-config")
    if not tool:
        return ""
    try:
        result = subprocess.run(
            [tool, f"--variable={variable}", "xdg-desktop-portal"],
            capture_output=True, text=True, errors="replace", timeout=3, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    value = result.stdout.strip() if result.returncode == 0 else ""
    return os.path.normpath(value) if os.path.isabs(value) else ""


def _portal_build_roots():
    """Exact when explicitly supplied/available in installed build metadata.

    Conventional roots are only assumptions, never claimed to be verified.
    Overrides affect inspection only; they do not change portal behaviour.
    """
    roots = {}
    for kind, fallback in (("sysconfdir", "/etc"), ("datadir", "/usr/share")):
        env_key = f"LINSPECTACLES_XDG_PORTAL_{kind.upper()}"
        specified = str(os.environ.get(env_key, "")).strip()
        if specified and os.path.isabs(specified):
            roots[kind] = (os.path.normpath(specified), "Inspector override", True)
            continue
        discovered = _pkg_config_portal_path(kind)
        if discovered:
            roots[kind] = (discovered, "Installed pkg-config metadata", True)
            continue
        roots[kind] = (fallback, "Conventional path (not build-verified)", False)
    return roots


def _xdg_data_dirs():
    home = _absolute_path(os.environ.get("XDG_DATA_HOME"), "~/.local/share")
    dirs = _absolute_path_list(
        os.environ.get("XDG_DATA_DIRS"), "/usr/local/share:/usr/share"
    )
    # The upstream frontend's build datadir may be outside XDG_DATA_DIRS.
    built_root, _source, _verified = _portal_build_roots()["datadir"]
    result = [home]
    for path in dirs + [built_root]:
        if path not in result:
            result.append(path)
    return result


def _config_locations():
    config_home = _absolute_path(os.environ.get("XDG_CONFIG_HOME"), "~/.config")
    config_dirs = _absolute_path_list(os.environ.get("XDG_CONFIG_DIRS"), "/etc/xdg")
    data_home = _absolute_path(os.environ.get("XDG_DATA_HOME"), "~/.local/share")
    data_dirs = _absolute_path_list(
        os.environ.get("XDG_DATA_DIRS"), "/usr/local/share:/usr/share"
    )
    roots = _portal_build_roots()
    sysconfdir, sys_source, sys_verified = roots["sysconfdir"]
    datadir, data_source, data_verified = roots["datadir"]

    locations = [(config_home, "Config Home", True)]
    locations.extend((item, "Config Dirs", True) for item in config_dirs)
    locations.append((sysconfdir, "System Config", sys_verified))
    locations.append((data_home, "Data Home", True))
    locations.extend((item, "Data Dirs", True) for item in data_dirs)
    locations.append((datadir, "System Data", data_verified))

    deduped = []
    seen = set()
    for root, scope, verified in locations:
        key = os.path.normpath(root)
        if key in seen:
            continue
        seen.add(key)
        deduped.append((key, scope, verified))
    return deduped


def _scan_directory(directory, *, suffix=None):
    """Preserve directory access errors rather than silently treating them as empty."""
    try:
        with os.scandir(directory) as listing:
            entries = list(listing)
    except FileNotFoundError:
        return [], "missing", ""
    except PermissionError as exc:
        return [], "restricted", str(exc)
    except OSError as exc:
        return [], "error", str(exc)
    results = []
    for entry in entries:
        if suffix is not None and not entry.name.endswith(suffix):
            continue
        try:
            if entry.is_file(follow_symlinks=True):
                results.append(entry.name)
        except PermissionError as exc:
            return results, "restricted", f"{entry.path}: {exc}"
        except OSError as exc:
            return results, "error", f"{entry.path}: {exc}"
    return sorted(results, key=str.casefold), "observed", ""


def _read_ini(path):
    parser = configparser.ConfigParser(interpolation=None, strict=False)
    parser.optionxform = str
    try:
        with open(path, "r", encoding="utf-8-sig", errors="replace") as handle:
            parser.read_file(handle)
        return "observed", parser, ""
    except PermissionError as exc:
        return "restricted", None, str(exc)
    except OSError as exc:
        return "error", None, str(exc)
    except configparser.Error as exc:
        return "error", None, str(exc)


def _backend_source_issue(directory, state, error, rank):
    return {
        "_view": "Backends", "backend": "Source unavailable",
        "backend_id": "", "dbus_name": "Not determined", "interfaces": [],
        "interfaces_raw": "", "interfaces_display": "Not determined",
        "use_in": "Not determined", "source": str(directory),
        "descriptor_state": state, "descriptor_error": error,
        "data_root": str(directory), "source_rank": rank,
        "_source_issue": True,
    }


def _collect_backends():
    records = []
    seen_paths = set()
    backend_rank = 0
    for data_root in _xdg_data_dirs():
        portal_dir = Path(data_root) / "xdg-desktop-portal" / "portals"
        names, scan_state, scan_error = _scan_directory(portal_dir, suffix=".portal")
        if scan_state not in {"observed", "missing"}:
            backend_rank += 1
            records.append(_backend_source_issue(portal_dir, scan_state, scan_error, backend_rank))
        for filename in names:
            path = portal_dir / filename
            resolved = str(path)
            if resolved in seen_paths:
                continue
            seen_paths.add(resolved)
            backend_rank += 1
            state, parser, error = _read_ini(path)
            backend_id = path.stem
            dbus_name = ""
            interfaces_raw = ""
            use_in = ""
            if parser is not None and parser.has_section("portal"):
                section = parser["portal"]
                dbus_name = section.get("DBusName", "").strip()
                interfaces_raw = section.get("Interfaces", "").strip()
                use_in = section.get("UseIn", "").strip()
            elif state == "observed":
                state, error = "error", "The descriptor has no [portal] section."
            interfaces = _split_semicolon(interfaces_raw)
            records.append({
                "_view": "Backends", "backend": backend_id,
                "backend_id": backend_id, "dbus_name": dbus_name or "Not reported",
                "interfaces": interfaces, "interfaces_raw": interfaces_raw,
                "interfaces_display": (
                    "; ".join(interfaces) if interfaces else
                    ("Not determined" if state != "observed" else "None reported")
                ),
                "use_in": use_in or ("Not determined" if state != "observed" else "None reported"),
                "source": str(path),
                "descriptor_state": state, "descriptor_error": error,
                "data_root": str(data_root), "source_rank": backend_rank,
            })
    return records


def _config_source_issue(directory, scope, state, error, position, verified):
    return {
        "_view": "Configuration", "config_file": "Source unavailable",
        "scope": scope, "desktop": "Not determined",
        "default_backends": "Not determined", "default_backends_raw": "",
        "overrides": {}, "overrides_display": "Not determined",
        "effective_state": "", "source": str(directory),
        "lookup_position": position, "parse_state": state, "parse_error": error,
        "root_verified": verified, "_source_issue": True,
    }


def _collect_configuration():
    # One desktop-specific file per XDG_CURRENT_DESKTOP token, then fallback.
    desktops = _desktop_values()
    names = list(dict.fromkeys([f"{desktop.lower()}-portals.conf" for desktop in desktops]
                               + ["portals.conf"]))
    records = []
    candidate_position = 0
    assumed_positions = []
    for root, scope, verified in _config_locations():
        if not verified:
            assumed_positions.append(candidate_position + 1)
        portal_dir = Path(root) / "xdg-desktop-portal"
        found_names, state, error = _scan_directory(portal_dir)
        if state not in {"observed", "missing"}:
            records.append(_config_source_issue(
                portal_dir, scope, state, error, candidate_position + 1, verified
            ))
        found = set(found_names)
        for filename in names:
            candidate_position += 1
            if filename not in found:
                continue
            path = portal_dir / filename
            state, parser, error = _read_ini(path)
            preferred = {}
            if parser is not None and parser.has_section("preferred"):
                for key, value in parser.items("preferred"):
                    preferred[str(key).strip()] = str(value).strip()
            default = preferred.get("default", "")
            overrides = {key: value for key, value in preferred.items() if key != "default"}
            desktop = "All / fallback" if filename == "portals.conf" else filename[:-len("-portals.conf")]
            records.append({
                "_view": "Configuration", "config_file": filename,
                "scope": scope, "desktop": desktop,
                "default_backends": (
                    default or ("Not determined" if state != "observed" else "None reported")
                ),
                "default_backends_raw": default, "overrides": overrides,
                "overrides_display": (
                    f"{len(overrides)} interface override(s)" if overrides else
                    ("Not determined" if state != "observed" else "None reported")
                ),
                "effective_state": "", "source": str(path),
                "lookup_position": candidate_position, "parse_state": state,
                "parse_error": error, "root_verified": verified,
            })

    # First candidate is potentially effective. An inaccessible earlier root
    # makes the lower-precedence result uncertain, not simply 'Effective'.
    records.sort(key=lambda item: item["lookup_position"])
    winner_seen = False
    blocked_above = False
    for record in records:
        if winner_seen:
            record["effective_state"] = "Shadowed"
            continue
        if record.get("_source_issue"):
            record["effective_state"] = "Unverified"
            blocked_above = True
            continue
        # A conventional build root is not proof of the frontend's compiled
        # search path. Never certify lower-priority effective selection when
        # an earlier assumed build root could be different on this host.
        uncertain_root = any(position <= record["lookup_position"]
                             for position in assumed_positions)
        record["effective_state"] = (
            "Potentially effective" if blocked_above or uncertain_root else "Effective"
        )
        winner_seen = True
    return records


def _active_backend_map(backends):
    result = {}
    for record in sorted(backends, key=lambda item: item.get("source_rank", 0)):
        backend_id = record.get("backend_id", "")
        if backend_id and backend_id not in result:
            result[backend_id] = record
    return result


def _selected_backend_for_interface(interface, effective_config, active_backends,
                                    *, backend_inventory_complete=True):
    """Return (selected ID, provenance note, selection-is-determined).

    A parse/access failure must never be silently converted to 'No'.
    """
    if not effective_config:
        return None, "No effective portals.conf was established.", False
    if effective_config.get("parse_state") != "observed":
        return None, (
            f"Configuration is {effective_config.get('parse_state')}: "
            f"{effective_config.get('parse_error') or 'preferences unavailable'}."
        ), False
    if effective_config.get("effective_state") != "Effective":
        return None, "Higher-precedence configuration could not be ruled out.", False

    overrides = effective_config.get("overrides", {})
    preference = overrides.get(interface)
    source = f"interface override in {effective_config.get('source', '')}"
    if preference is None:
        preference = effective_config.get("default_backends_raw", "")
        source = f"default preference in {effective_config.get('source', '')}"

    candidates = _split_semicolon(preference)
    if not candidates:
        return None, f"No applicable backend preference is reported by {source}.", True

    implementing = {
        backend_id: record for backend_id, record in active_backends.items()
        if interface in record.get("interfaces", [])
    }
    # Even with a readable configuration, an incomplete descriptor inventory
    # may hide an earlier preferred backend or change '*' ordering.
    for candidate in candidates:
        if candidate == "none":
            return None, f"Selection disabled by 'none' from {source}.", True
        if not backend_inventory_complete:
            return None, f"Backend descriptor inventory is incomplete; cannot resolve {source}.", False
        if candidate == "*":
            if implementing:
                selected = sorted(implementing, key=str.lower)[0]
                return selected, f"Selected lexicographically by '*' from {source}.", True
            continue
        if candidate in implementing:
            return candidate, (
                "First preferred observed backend declaring this interface "
                f"({source})."
            ), True
    return None, f"No preferred backend declaring this interface was found ({source}).", True


def _collect_interfaces(backends, configs):
    effective_config = next(
        (item for item in configs if item.get("effective_state") in
         {"Effective", "Potentially effective"}), None
    )
    active_backends = _active_backend_map(backends)
    backend_inventory_complete = all(
        record.get("descriptor_state") == "observed" and not record.get("_source_issue")
        for record in backends
    )
    # The compiled datadir may contain a descriptor outside the paths we can
    # prove are searched. Do not assert an exhaustive backend choice if unknown.
    backend_inventory_complete &= _portal_build_roots()["datadir"][2]
    records = []
    for backend in backends:
        if backend.get("_source_issue"):
            continue
        for interface in backend.get("interfaces", []):
            selected_backend, note, determined = _selected_backend_for_interface(
                interface, effective_config, active_backends,
                backend_inventory_complete=backend_inventory_complete,
            )
            if not determined:
                selected = "Not determined"
            elif (selected_backend == backend.get("backend_id") and
                  active_backends.get(selected_backend, {}).get("source") == backend.get("source")):
                selected = "Yes"
            else:
                selected = "No"
            records.append({
                "_view": "Interfaces", "interface": interface,
                "backend": backend.get("backend_id", ""), "selected": selected,
                "dbus_name": backend.get("dbus_name", ""),
                "source": backend.get("source", ""),
                "selection_note": note,
                "effective_config": effective_config.get("source", "") if effective_config else "",
            })
    records.sort(key=lambda item: (item.get("interface", "").lower(), item.get("backend", "").lower()))
    return records


def _frontend_installation():
    """Filesystem evidence only; no bus query or activation is performed."""
    issues = []
    for data_root in _xdg_data_dirs():
        service_dir = Path(data_root) / "dbus-1" / "services"
        found, state, error = _scan_directory(service_dir)
        if state not in {"observed", "missing"}:
            issues.append(f"{service_dir}: {state}: {error}")
        if "org.freedesktop.portal.Desktop.service" in found:
            path = str(service_dir / "org.freedesktop.portal.Desktop.service")
            return "D-Bus activation descriptor found", path
    executable = shutil.which("xdg-desktop-portal")
    if executable:
        return "Executable found on PATH", executable
    if issues:
        return "Not determined (some locations inaccessible)", "; ".join(issues)
    return "Not confirmed in searched paths", "XDG data directories / PATH (filesystem only)"


def _run_command(args, timeout=5):
    try:
        completed = subprocess.run(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            errors="replace",
            timeout=timeout,
            check=False,
            env=os.environ.copy(),
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return False, "", str(exc)
    if completed.returncode != 0:
        return False, completed.stdout or "", (completed.stderr or "").strip()
    return True, completed.stdout or "", (completed.stderr or "").strip()


def _runtime_from_busctl(backends):
    busctl = shutil.which("busctl")
    if not busctl:
        return None, "busctl is unavailable."
    ok, output, error = _run_command(
        [busctl, "--user", "--no-pager", "--no-legend", "--acquired", "--full", "list"]
    )
    if not ok:
        return None, error or "Could not query the user D-Bus."

    descriptor_names = {
        item.get("dbus_name"): item.get("backend_id")
        for item in backends
        if item.get("dbus_name") and item.get("dbus_name") != "Not reported"
    }
    rows = []
    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(None, 7)
        if not parts:
            continue
        name = parts[0]
        is_frontend = name == "org.freedesktop.portal.Desktop"
        is_backend = name in descriptor_names or name.startswith("org.freedesktop.impl.portal.")
        if not (is_frontend or is_backend):
            continue
        pid = parts[1] if len(parts) > 1 else ""
        owner = parts[4] if len(parts) > 4 else ""
        component = "xdg-desktop-portal" if is_frontend else descriptor_names.get(name, "Unmatched backend service")
        rows.append({
            "_view": "Runtime",
            "bus_name": name,
            "role": "Frontend" if is_frontend else "Backend",
            "owner": owner if owner and owner != "-" else "Not reported",
            "pid": int(pid) if pid.isdigit() else 0,
            "component": component,
            "state": "Running",
            "runtime_source": "session bus acquired names via busctl --user --acquired list",
        })
    rows.sort(key=lambda item: (item.get("role", ""), item.get("bus_name", "").lower()))
    return rows, ""


def _parse_dbus_send_strings(output):
    values = []
    for line in output.splitlines():
        line = line.strip()
        if line.startswith("string \"") and line.endswith("\""):
            values.append(line[8:-1])
    return values


def _dbus_send_call(method, args=None):
    dbus_send = shutil.which("dbus-send")
    if not dbus_send:
        return False, "", "dbus-send is unavailable."
    command = [
        dbus_send,
        "--session",
        "--print-reply",
        "--reply-timeout=4000",
        "--dest=org.freedesktop.DBus",
        "/org/freedesktop/DBus",
        f"org.freedesktop.DBus.{method}",
    ]
    command.extend(args or [])
    return _run_command(command)


def _dbus_owner(name):
    ok, output, _error = _dbus_send_call("GetNameOwner", [f"string:{name}"])
    if not ok:
        return ""
    values = _parse_dbus_send_strings(output)
    return values[0] if values else ""


def _dbus_pid(owner):
    if not owner:
        return 0
    ok, output, _error = _dbus_send_call("GetConnectionUnixProcessID", [f"string:{owner}"])
    if not ok:
        return 0
    for line in output.splitlines():
        line = line.strip()
        if line.startswith("uint32 "):
            raw = line.split(None, 1)[1]
            return int(raw) if raw.isdigit() else 0
    return 0


def _runtime_from_dbus_send(backends):
    ok, output, error = _dbus_send_call("ListNames")
    if not ok:
        return None, error or "Could not query the user D-Bus."
    names = set(_parse_dbus_send_strings(output))
    descriptor_names = {
        item.get("dbus_name"): item.get("backend_id")
        for item in backends
        if item.get("dbus_name") and item.get("dbus_name") != "Not reported"
    }
    candidates = [
        name for name in names
        if name == "org.freedesktop.portal.Desktop"
        or name in descriptor_names
        or name.startswith("org.freedesktop.impl.portal.")
    ]
    rows = []
    for name in sorted(candidates, key=str.lower):
        is_frontend = name == "org.freedesktop.portal.Desktop"
        owner = _dbus_owner(name)
        rows.append({
            "_view": "Runtime",
            "bus_name": name,
            "role": "Frontend" if is_frontend else "Backend",
            "owner": owner or "Not reported",
            "pid": _dbus_pid(owner),
            "component": "xdg-desktop-portal" if is_frontend else descriptor_names.get(name, "Unmatched backend service"),
            "state": "Running",
            "runtime_source": "session bus acquired names via org.freedesktop.DBus.ListNames",
        })
    return rows, ""


def _collect_runtime(backends):
    rows, error = _runtime_from_busctl(backends)
    if rows is not None:
        return "observed", rows, ""
    fallback_rows, fallback_error = _runtime_from_dbus_send(backends)
    if fallback_rows is not None:
        return "observed", fallback_rows, ""
    combined = "; ".join(item for item in (error, fallback_error) if item)
    return "unavailable", [], combined or "No supported session-bus query tool is available."


class XDGPortalsOptionsDialog(QDialog):
    """Kernel Modules-authoritative Options treatment, adapted only for XDG Portals content."""

    def __init__(self, owner):
        super().__init__(owner)
        self.owner = owner
        self.setWindowTitle("Options — XDG Portals")
        self.resize(980, 720)

        root = QVBoxLayout(self)
        tabs = QTabWidget()
        root.addWidget(tabs, 1)

        appearance_page = QWidget()
        appearance_layout = QVBoxLayout(appearance_page)
        appearance_layout.setContentsMargins(12, 12, 12, 12)
        appearance_layout.setSpacing(10)

        appearance_heading = QLabel("Metadata display")
        heading_font = appearance_heading.font()
        heading_font.setBold(True)
        appearance_heading.setFont(heading_font)
        appearance_layout.addWidget(appearance_heading)

        appearance_note = QLabel(
            "Choose how the inventory and Metadata Details panes are arranged. "
            "This XDG Portals setting is remembered."
        )
        appearance_note.setWordWrap(True)
        appearance_layout.addWidget(appearance_note)

        layout_row = QHBoxLayout()
        layout_row.addWidget(QLabel("Record details layout:"))
        self.layout_combo = QComboBox()
        self.layout_combo.addItems(["Horizontal", "Vertical"])
        self.layout_combo.setCurrentText(
            "Vertical" if owner.details_orientation == "vertical" else "Horizontal"
        )
        self.layout_combo.currentTextChanged.connect(self._layout_changed)
        layout_row.addWidget(self.layout_combo)
        layout_row.addStretch(1)
        appearance_layout.addLayout(layout_row)

        self.show_metadata_panel = QCheckBox("Show Metadata Details panel (F3)")
        self.show_metadata_panel.setChecked(owner.metadata_panel_visible)
        self.show_metadata_panel.toggled.connect(self._metadata_panel_changed)
        appearance_layout.addWidget(self.show_metadata_panel)

        shortcut_note = QLabel(
            "F3 hides/restores Metadata Details. Shift+F5 refreshes the current inventory. "
            "Ctrl+L toggles Horizontal/Vertical layout. Ctrl+/ opens Options."
        )
        shortcut_note.setWordWrap(True)
        appearance_layout.addWidget(shortcut_note)

        appearance_layout.addStretch(1)
        tabs.addTab(appearance_page, "Appearance")

        sources_page = QWidget()
        sources_layout = QVBoxLayout(sources_page)
        sources_layout.setContentsMargins(12, 12, 12, 12)
        sources_layout.setSpacing(10)

        sources_heading = QLabel("Data Sources")
        sources_heading_font = sources_heading.font()
        sources_heading_font.setBold(True)
        sources_heading_font.setPointSize(max(sources_heading_font.pointSize(), 11))
        sources_heading.setFont(sources_heading_font)
        sources_layout.addWidget(sources_heading)

        sources_note = QLabel(
            "Linux interfaces and XDG Desktop Portal configuration used by this read-only inspector."
        )
        sources_note.setWordWrap(True)
        sources_layout.addWidget(sources_note)

        sources_text = QTextEdit()
        sources_text.setReadOnly(True)
        sources_text.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        chosen_font = getattr(owner, "_metadata_font", None)
        if chosen_font is not None:
            sources_text.setFont(chosen_font)
            sources_text.document().setDefaultFont(chosen_font)
            sources_text.setCurrentFont(chosen_font)
            font_rule = metadata_font_qss(chosen_font)
        else:
            font_rule = ""
        sources_text.setStyleSheet(
            "QTextEdit { "
            + font_rule
            + " background-color: #151719; color: #dcdcdc; "
              "border: 1px solid #333333; }"
        )

        source_key_format = QTextCharFormat()
        source_key_format.setForeground(QColor("#9cdcfe"))
        source_key_format.setFontWeight(600)
        source_value_format = QTextCharFormat()
        source_value_format.setForeground(QColor("#dcdcdc"))

        cursor = sources_text.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        for line in owner.sources_text().splitlines():
            if line and not line[:1].isspace():
                cursor.insertText(line + "\n", source_key_format)
            else:
                cursor.insertText(line + "\n", source_value_format)
        sources_text.setTextCursor(cursor)
        sources_text.moveCursor(QTextCursor.MoveOperation.Start)
        sources_layout.addWidget(sources_text, 1)
        tabs.addTab(sources_page, "Sources")

        export_page = QWidget()
        export_layout = QVBoxLayout(export_page)
        export_layout.setContentsMargins(12, 12, 12, 12)
        export_layout.setSpacing(10)

        export_heading = QLabel("Export details")
        export_heading_font = export_heading.font()
        export_heading_font.setBold(True)
        export_heading.setFont(export_heading_font)
        export_layout.addWidget(export_heading)

        export_note = QLabel(
            f"Select the {owner.current_view} details to include in the export."
        )
        export_note.setWordWrap(True)
        export_layout.addWidget(export_note)

        self.export_checks = []
        for column_id, label, width, alignment in owner.columns:
            checkbox = QCheckBox(label)
            checkbox.setChecked(True)
            export_layout.addWidget(checkbox)
            self.export_checks.append((checkbox, (column_id, label, width, alignment)))

        self.export_metadata = QCheckBox("Metadata Details")
        self.export_metadata.setChecked(False)
        export_layout.addWidget(self.export_metadata)

        export_layout.addStretch(1)
        export_row = QHBoxLayout()
        export_row.addStretch(1)
        export_button = QPushButton("Export...")
        export_button.clicked.connect(self._export_selected)
        export_row.addWidget(export_button)
        export_layout.addLayout(export_row)
        tabs.addTab(export_page, "Export")

        about_page = QWidget()
        about_layout = QVBoxLayout(about_page)
        about_layout.setContentsMargins(24, 20, 24, 18)
        about_layout.setSpacing(8)

        icon_label = QLabel()
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_label.setFixedSize(112, 112)
        icon_path = Path(__file__).resolve().parent / "icon.png"
        if icon_path.is_file():
            pixmap = QPixmap(str(icon_path))
            if not pixmap.isNull():
                icon_label.setPixmap(
                    pixmap.scaled(
                        112,
                        112,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                )
        about_layout.addWidget(icon_label, alignment=Qt.AlignmentFlag.AlignHCenter)

        name = QLabel("<h2 style='margin:0'>XDG Portals</h2>")
        name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        about_layout.addWidget(name)

        version = QLabel(f"Version {APPLET_VERSION}")
        version.setAlignment(Qt.AlignmentFlag.AlignCenter)
        about_layout.addWidget(version)

        slogan = QLabel("<b>Expose. Explore. Explain.</b>")
        slogan.setAlignment(Qt.AlignmentFlag.AlignCenter)
        about_layout.addWidget(slogan)

        description = QLabel(
            "A read-only LinSpectacles applet for inspecting XDG Desktop Portal backends, "
            "declared interfaces, backend-selection configuration and already-running portal services."
        )
        description.setWordWrap(True)
        description.setAlignment(Qt.AlignmentFlag.AlignCenter)
        about_layout.addWidget(description)

        details = QLabel(
            "<b>Build:</b> Standalone LinSpectacles applet<br>"
            "<b>Organisation ID:</b> "
            "<a href='https://github.com/linspectacles/'>linspectacles</a><br>"
            f"<b>Applet ID:</b> {APPLET_ID}"
        )
        details.setWordWrap(True)
        details.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextBrowserInteraction
            | Qt.TextInteractionFlag.TextSelectableByMouse
        )
        details.setOpenExternalLinks(True)
        details.setAlignment(Qt.AlignmentFlag.AlignCenter)
        about_layout.addWidget(details)

        copyright_label = QLabel(
            "Copyright © 2026 "
            "<a href='https://github.com/brunonlinespace'>brunonlinespace</a>"
        )
        copyright_label.setOpenExternalLinks(True)
        copyright_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        about_layout.addWidget(copyright_label)

        license_label = QLabel("Licensed under GNU GPLv3 or later.")
        license_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        about_layout.addWidget(license_label)

        readme_url = QUrl.fromLocalFile(
            str(Path(__file__).resolve().parent.parent / "README.md")
        ).toString()
        license_url = QUrl.fromLocalFile(
            str(Path(__file__).resolve().parent.parent / "LICENSE")
        ).toString()
        links = QLabel(
            f"<a href='{readme_url}'>README</a> "
            "&nbsp;·&nbsp; "
            f"<a href='{license_url}'>License</a> "
            "&nbsp;·&nbsp; "
            "<a href='https://github.com/linspectacles/xdg-portals'>Repository</a>"
        )
        links.setOpenExternalLinks(True)
        links.setAlignment(Qt.AlignmentFlag.AlignCenter)
        about_layout.addWidget(links)
        about_layout.addStretch(1)
        tabs.addTab(about_page, "About")

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _layout_changed(self, text):
        self.owner.set_details_orientation(str(text).strip().lower(), persist=True)

    def _metadata_panel_changed(self, visible):
        self.owner.set_metadata_panel_visible(bool(visible), persist=True)

    def _export_selected(self):
        selected = [column for checkbox, column in self.export_checks if checkbox.isChecked()]
        if self.export_metadata.isChecked():
            selected.append(("metadata_details", "Metadata Details", 520, "left"))
        if not selected:
            QMessageBox.information(self, "Export", "Select at least one detail to export.")
            return

        records = []
        include_metadata = self.export_metadata.isChecked()
        for record in self.owner.get_export_records():
            exported = dict(record)
            if include_metadata:
                exported["metadata_details"] = self.owner.metadata_details_for_export(record)
            records.append(exported)

        if not records:
            QMessageBox.information(self, "Export", "There is no collected data to export yet.")
            return

        path = export_records_dialog(
            self,
            f"{APPLET_NAME} — {self.owner.current_view}",
            records,
            columns=selected,
        )
        if path is not None:
            self.owner.set_status(f"Exported data to {path}")


class XDGPortalsTab(BaseInspectorTab):
    NUMERIC_COLUMNS = {"pid", "lookup_position", "source_rank"}

    def __init__(self, parent=None):
        super().__init__("Total Overview Items", VIEW_COLUMNS["Overview"], list(VIEWS), parent)
        self.export_title = APPLET_NAME
        self.current_view = "Overview"
        self.backends = []
        self.configs = []
        self.interfaces = []
        self.runtime_records = []
        self.runtime_loaded = False
        self.runtime_state = "not_loaded"
        self.runtime_error = ""
        self.view_records = []
        self._hidden_by_view = self._load_hidden_columns_by_view()
        self._selector_by_view = {}

        self.category_label.setText("View:")
        try:
            self.category_dropdown.currentTextChanged.disconnect()
        except TypeError:
            pass
        self.category_dropdown.clear()
        self.category_dropdown.addItems(VIEWS)
        self.category_dropdown.setMinimumWidth(170)
        self.category_dropdown.currentTextChanged.connect(self._view_changed)

        # Keep the Kernel Modules top-level action row authoritative:
        # total at left; View immediately before Refresh List and Options at right.
        filter_layout = self.layout().itemAt(1).layout()
        filter_layout.removeWidget(self.category_label)
        filter_layout.removeWidget(self.category_dropdown)
        refresh_index = self.dash_layout.indexOf(self.refresh_btn)
        self.dash_layout.insertWidget(refresh_index, self.category_label)
        self.dash_layout.insertWidget(refresh_index + 1, self.category_dropdown)

        status_index = filter_layout.indexOf(self.filter_status_lbl)
        self.selector_label = QLabel("")
        self.selector_label.setStyleSheet("font-weight: 600;")
        self.selector_dropdown = QComboBox()
        self.selector_dropdown.setMinimumWidth(190)
        self.selector_dropdown.currentTextChanged.connect(self.filter_modules)
        filter_layout.insertWidget(status_index, self.selector_label)
        filter_layout.insertWidget(status_index + 1, self.selector_dropdown)

        self.details_orientation = "horizontal"
        self._load_details_orientation()

        self.metadata_panel_visible = True
        self._load_metadata_panel_visibility()

        self.export_btn.setText("Options...")
        try:
            self.export_btn.clicked.disconnect()
        except TypeError:
            pass
        self.export_btn.clicked.connect(self.show_options)
        self.export_btn.setEnabled(True)

        self.column_visibility.set_changed_callback(self._columns_changed)

        self._shortcuts = []
        self._install_shortcuts()

        self._configure_view("Overview")
        self.load_modules()

    @staticmethod
    def _column_settings():
        return QSettings("brunonlinespace", "XDG Portals")

    def _load_hidden_columns_by_view(self):
        settings = self._column_settings()
        hidden_by_view = {}
        self._local_columns_persisted = set()
        for view in VIEWS:
            key = f"hidden_columns/{view}"
            known = {column[0] for column in VIEW_COLUMNS[view]}
            if settings.contains(key):
                self._local_columns_persisted.add(view)
            value = settings.value(key, [])
            if isinstance(value, str):
                value = [value] if value else []
            if not isinstance(value, (list, tuple)):
                value = []
            hidden_by_view[view] = [str(item) for item in value if str(item) in known]
        return hidden_by_view

    def apply_host_settings(self, settings=None, column_visibility_callback=None):
        settings = settings or {}
        self._metadata_font = apply_metadata_font(
            self.info_text, settings.get("metadata_font", "")
        )
        self._update_info_style()
        # Host's legacy list has no view ID; migrate it *once*, for Overview
        # only. Applet-owned QSettings remains authoritative for all five views.
        host_hidden = settings.get("hidden_columns", [])
        if ("Overview" not in self._local_columns_persisted and
                self.current_view == "Overview" and isinstance(host_hidden, (list, tuple))):
            known = {column[0] for column in VIEW_COLUMNS["Overview"]}
            if all(str(key) in known for key in host_hidden):
                self._hidden_by_view["Overview"] = list(host_hidden)
                if host_hidden:
                    self._columns_changed(host_hidden)
        if callable(column_visibility_callback):
            def changed(hidden):
                self._columns_changed(hidden)
                column_visibility_callback(hidden)
            self.column_visibility.set_changed_callback(changed)
        else:
            self.column_visibility.set_changed_callback(self._columns_changed)
        self.column_visibility.apply_hidden(self._hidden_by_view[self.current_view])

    def _columns_changed(self, hidden):
        known = {column[0] for column in VIEW_COLUMNS[self.current_view]}
        values = [str(item) for item in (hidden or []) if str(item) in known]
        self._hidden_by_view[self.current_view] = values
        self._local_columns_persisted.add(self.current_view)
        settings = self._column_settings()
        settings.setValue(f"hidden_columns/{self.current_view}", values)
        settings.sync()

    def _set_columns(self, columns):
        self.columns = list(columns)
        self.table.setColumnCount(len(self.columns))
        self.table.setHorizontalHeaderLabels([column[1] for column in self.columns])
        for index, (_column_id, _label, width, _alignment) in enumerate(self.columns):
            self.table.setColumnHidden(index, False)
            self.table.setColumnWidth(index, width)
        self.column_visibility.columns = list(self.columns)
        self.column_visibility.apply_hidden(self._hidden_by_view.get(self.current_view, []))

    def _view_changed(self, view):
        if view not in VIEWS:
            return
        # Retain view-specific selector even when a different view is opened.
        if self.current_view in VIEWS:
            self._selector_by_view[self.current_view] = self.selector_dropdown.currentText()
        self.current_view = view
        self._configure_view(view, switched=True)
        if view == "Runtime":
            self._refresh_runtime()
        else:
            self._refresh_current_view()

    def _configure_view(self, view, *, switched=False):
        previous = self.selector_dropdown.currentText()
        preserve = self._selector_by_view.get(view, "") if switched else previous
        self.current_view = view
        self._set_columns(VIEW_COLUMNS[view])
        self.selector_dropdown.blockSignals(True)
        try:
            self.selector_dropdown.clear()
            if view == "Overview":
                self.selector_label.hide()
                self.selector_dropdown.hide()
            elif view == "Backends":
                self.selector_label.setText("Desktop:")
                self.selector_label.show()
                self.selector_dropdown.show()
                # Config selection is for the complete XDG_CURRENT_DESKTOP list,
                # not independent values of deprecated descriptor UseIn.
                desktop = ":".join(_desktop_values())
                self.selector_dropdown.addItems(["All"] + ([f"Current ({desktop})"] if desktop else []))
            elif view == "Interfaces":
                self.selector_label.setText("Backend:")
                self.selector_label.show()
                self.selector_dropdown.show()
                backend_ids = sorted({
                    item.get("backend_id", "") for item in self.backends
                    if item.get("backend_id")
                }, key=str.lower)
                self.selector_dropdown.addItems(["All Backends"] + backend_ids)
            elif view == "Configuration":
                self.selector_label.setText("Scope:")
                self.selector_label.show()
                self.selector_dropdown.show()
                scopes = list(dict.fromkeys(item.get("scope", "") for item in self.configs if item.get("scope")))
                self.selector_dropdown.addItems(["All Scopes"] + scopes)
            elif view == "Runtime":
                self.selector_label.setText("Role:")
                self.selector_label.show()
                self.selector_dropdown.show()
                self.selector_dropdown.addItems(["All Roles", "Frontend", "Backend"])
            if preserve and self.selector_dropdown.findText(preserve) >= 0:
                self.selector_dropdown.setCurrentText(preserve)
            self._selector_by_view[view] = self.selector_dropdown.currentText()
        finally:
            self.selector_dropdown.blockSignals(False)

    def _build_overview(self):
        effective = next((item for item in self.configs if item.get("effective_state") in
                          {"Effective", "Potentially effective"}), None)
        desktops_raw = os.environ.get("XDG_CURRENT_DESKTOP", "") or "Not reported"
        session_type = os.environ.get("XDG_SESSION_TYPE", "") or "Not reported"
        frontend_evidence, frontend_source = _frontend_installation()
        running_frontend = "Not checked — open Runtime view"
        runtime_value = "Not loaded — open Runtime view"
        runtime_source = "Session bus (not queried yet)"
        if self.runtime_loaded:
            runtime_value = str(len(self.runtime_records))
            running_frontend = "Running" if any(
                item.get("bus_name") == "org.freedesktop.portal.Desktop"
                for item in self.runtime_records
            ) else "Not observed"
            runtime_source = "Cached Runtime view result"
        elif self.runtime_state == "unavailable":
            runtime_value = "Unavailable"
            running_frontend = "Unavailable"
            runtime_source = self.runtime_error or "Session bus query unavailable"

        distinct_interfaces = {
            interface for backend in self.backends
            for interface in backend.get("interfaces", [])
        }
        valid_backends = [x for x in self.backends if not x.get("_source_issue")]
        issues = [x for x in self.backends if x.get("_source_issue") or
                  x.get("descriptor_state") != "observed"]
        issues += [x for x in self.configs if x.get("_source_issue") or
                   x.get("parse_state") != "observed"]
        roots = _portal_build_roots()
        unverified = [kind for kind, (_path, _source, verified) in roots.items() if not verified]
        coverage = (
            "Build roots assumed: " + ", ".join(unverified) if unverified else
            "Build roots verified through local metadata/overrides"
        )
        count_label = str(len(valid_backends))
        if any(item.get("_source_issue") or item.get("descriptor_state") != "observed"
               for item in self.backends):
            count_label += " (incomplete scan)"
        interface_label = str(len(distinct_interfaces))
        if any(item.get("_source_issue") or item.get("descriptor_state") != "observed"
               for item in self.backends):
            interface_label += " (incomplete scan)"
        if effective and effective.get("parse_state") != "observed":
            default_value = "Not determined (configuration unreadable/invalid)"
        else:
            default_value = effective.get("default_backends") if effective else "Not determined"
        if effective and effective.get("effective_state") != "Effective":
            default_value = f"Possibly {default_value} (lookup incomplete)"
        config_value = effective.get("source") if effective else (
            "Not determined (source restricted)" if any(x.get("_source_issue") for x in self.configs)
            else "Not found in searched paths"
        )
        if effective and effective.get("effective_state") != "Effective":
            config_value = f"Possibly {config_value} (lookup incomplete)"
        rows = [
            ("Current Desktop", desktops_raw, "XDG_CURRENT_DESKTOP"),
            ("Session Type", session_type, "XDG_SESSION_TYPE"),
            ("Portal Frontend Installation", frontend_evidence, frontend_source),
            ("Portal Frontend Runtime", running_frontend, runtime_source),
            ("Installed Backend Descriptors", count_label, "XDG data directories"),
            ("Declared Backend Interfaces", interface_label, ".portal descriptors"),
            ("Effective Configuration", config_value, "portals.conf lookup order"),
            ("Effective Default Backends", default_value, "[preferred] default"),
            ("Running Portal Services", runtime_value, runtime_source),
            ("Inspection Coverage", f"{len(issues)} unreadable/error source(s); {coverage}",
             "Filesystem inventory and installed build metadata"),
        ]
        return [
            {"_view": "Overview", "item": item, "value": value, "source": source}
            for item, value, source in rows
        ]

    def _records_for_view(self):
        if self.current_view == "Overview":
            return self._build_overview()
        if self.current_view == "Backends":
            return list(self.backends)
        if self.current_view == "Interfaces":
            return list(self.interfaces)
        if self.current_view == "Configuration":
            return list(self.configs)
        if self.current_view == "Runtime":
            return list(self.runtime_records)
        return []

    def _refresh_current_view(self):
        self._configure_view(self.current_view)
        self.view_records = self._records_for_view()
        self.modules_data = self.view_records
        self._update_stats_label()
        self.filter_modules()

    def _update_stats_label(self):
        labels = {
            "Overview": "Total Overview Items",
            "Backends": "Total Backends",
            "Interfaces": "Total Interfaces",
            "Configuration": "Total Configuration Files",
            "Runtime": "Total Running Portal Services",
        }
        self.total_label_text = labels[self.current_view]
        # Source-access diagnostic rows are visible but are not discovered files.
        count = sum(not item.get("_source_issue") for item in self.view_records)
        unavailable = sum(item.get("_source_issue", False) for item in self.view_records)
        extra = f" (+{unavailable} unavailable source(s))" if unavailable else ""
        self.stats_label.setText(f"{self.total_label_text}: {count}{extra}")

    def load_modules(self):
        if self.current_view == "Runtime":
            self._refresh_runtime()
            return
        self.set_status("Refreshing XDG Desktop Portal inventory...")
        try:
            self.backends = _collect_backends()
            self.configs = _collect_configuration()
            self.interfaces = _collect_interfaces(self.backends, self.configs)
            self._refresh_current_view()
            descriptors = sum(not x.get("_source_issue") for x in self.backends)
            configs = sum(not x.get("_source_issue") for x in self.configs)
            issues = sum(x.get("_source_issue", False) or x.get("descriptor_state") != "observed"
                         for x in self.backends)
            issues += sum(x.get("_source_issue", False) or x.get("parse_state") != "observed"
                          for x in self.configs)
            self.set_status(
                f"Refresh complete: {descriptors} backend descriptor(s), "
                f"{len(self.interfaces)} declared interface record(s), "
                f"{configs} configuration file(s). "
                + (f"WARNING: {issues} unavailable/invalid source(s); inventory may be incomplete."
                   if issues else "")
            )
        except Exception as exc:
            self.set_status(f"Error refreshing XDG Portals inventory: {exc}")

    def _refresh_runtime(self):
        self.set_status("Inspecting already-running portal services without activating absent services...")
        state, rows, error = _collect_runtime(self.backends)
        self.runtime_state = state
        self.runtime_error = error
        self.runtime_records = rows
        self.runtime_loaded = state == "observed"
        self._refresh_current_view()
        if state == "observed":
            if rows:
                self.set_status(f"Runtime inspection complete: {len(rows)} already-running portal service(s) observed.")
            else:
                self.set_status("Runtime inspection complete: no running portal frontend/backend services were observed.")
        else:
            self.set_status(f"Runtime inspection unavailable: {error}")

    def _matches_selector(self, record):
        selected = self.selector_dropdown.currentText()
        if self.current_view == "Backends":
            if not selected or selected == "All":
                return True
            # The active desktop's *configuration* chooses backends. UseIn is
            # deprecated and cannot be used as a current desktop filter.
            if any(item.get("selected") == "Not determined" for item in self.interfaces):
                return True  # Incomplete evidence: never hide a possible match.
            return any(
                item.get("source") == record.get("source") and item.get("selected") == "Yes"
                for item in self.interfaces
            )
        if self.current_view == "Interfaces":
            return not selected or selected == "All Backends" or record.get("backend") == selected
        if self.current_view == "Configuration":
            return not selected or selected == "All Scopes" or record.get("scope") == selected
        if self.current_view == "Runtime":
            return not selected or selected == "All Roles" or record.get("role") == selected
        return True

    def filter_modules(self, *_):
        query = self.search_entry.text().strip().lower()
        matches = []
        for record in self.view_records:
            if not self._matches_selector(record):
                continue
            if query and not any(query in str(value).lower() for value in record.values()):
                continue
            matches.append(record)

        blocked = self.table.blockSignals(True)
        try:
            self.clear_info()
            self.table.clearSelection()
            self.table.setCurrentCell(-1, -1)
            self.table.setSortingEnabled(False)
            self.table.setRowCount(len(matches))
            from PyQt6.QtWidgets import QTableWidgetItem
            for row, record in enumerate(matches):
                for column_index, (column_id, _label, _width, alignment) in enumerate(self.columns):
                    value = record.get(column_id, "")
                    if column_id == "pid" and isinstance(value, int):
                        display = str(value) if value > 0 else "Not reported"
                    else:
                        display = str(value)
                    item = QTableWidgetItem(display)
                    if column_index == 0:
                        item.setData(Qt.ItemDataRole.UserRole, record)
                    if alignment == "right":
                        item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                    else:
                        item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                    self.style_table_item(item, column_id, record)
                    self.table.setItem(row, column_index, item)
            if matches:
                self.table.setCurrentCell(0, 0)
                self.table.selectRow(0)
        finally:
            self.table.blockSignals(blocked)

        if matches:
            self.on_module_select()
        else:
            self.clear_info()

        selector_active = self.selector_label.isVisible() and self.selector_dropdown.currentIndex() > 0
        if query or selector_active:
            uncertain = (
                self.current_view == "Backends" and selector_active and
                any(item.get("selected") == "Not determined" for item in self.interfaces)
            )
            qualifier = " — backend selection undetermined" if uncertain else ""
            self.filter_status_lbl.setText(
                f"(Showing {len(matches)} of {len(self.view_records)} items{qualifier})"
            )
        else:
            self.filter_status_lbl.clear()

    def sort_by(self, column_id):
        reverse = self._sort_reverse.get(column_id, False)
        if column_id == "pid":
            key_func = lambda item: int(item.get(column_id, 0) or 0)
        else:
            key_func = lambda item: str(item.get(column_id, "")).lower()
        try:
            self.view_records.sort(key=key_func, reverse=reverse)
        except Exception:
            self.view_records.sort(key=lambda item: str(item.get(column_id, "")).lower(), reverse=reverse)
        self._sort_reverse[column_id] = not reverse
        self.modules_data = self.view_records
        self.filter_modules()

    def get_export_records(self):
        return list(self.view_records)

    def style_table_item(self, item, column_id, record):
        if column_id == "selected":
            value = record.get("selected")
            if value == "Yes":
                item.setForeground(QBrush(QColor("#4ec9b0")))
            elif value == "Not determined":
                item.setForeground(QBrush(QColor("#dcdcaa")))
        elif column_id == "effective_state":
            if record.get("effective_state") == "Effective":
                item.setForeground(QBrush(QColor("#4ec9b0")))
            elif record.get("effective_state") in {"Unverified", "Potentially effective"}:
                item.setForeground(QBrush(QColor("#dcdcaa")))
            else:
                item.setForeground(QBrush(QColor("#9a9a9a")))

    def on_module_select(self):
        record = self.current_record()
        if not record:
            return
        self._render_record_details(record)
        label = self._record_label(record)
        self.set_status(f"Inspecting {self.current_view.lower()} record [{label}].")

    def _record_label(self, record):
        for key in ("backend", "interface", "config_file", "bus_name", "item"):
            if record.get(key):
                return str(record.get(key))
        return "record"

    def _render_record_details(self, record):
        self.clear_info()
        view = record.get("_view", self.current_view)
        if view == "Overview":
            self.append_info("--- Overview ---\n")
            self.append_key_value("Item", record.get("item", ""))
            self.append_key_value("Value", record.get("value", ""))
            self.append_key_value("Source", record.get("source", ""))
            if record.get("item") in {"Portal Frontend Runtime", "Running Portal Services"} and not self.runtime_loaded:
                self.append_info("\nRuntime note: session-bus state is intentionally not queried until the Runtime view is opened.\n")
            return

        if view == "Backends":
            self.append_info("--- Backend Descriptor ---\n")
            self.append_key_value("Backend ID", record.get("backend_id", ""))
            self.append_key_value("Descriptor Path", record.get("source", ""))
            self.append_key_value("D-Bus Name", record.get("dbus_name", ""))
            self.append_key_value("Interfaces", record.get("interfaces_raw") or (
                "Not determined" if record.get("descriptor_state") != "observed" else "None reported"
            ))
            self.append_key_value("UseIn", record.get("use_in", "None reported"))
            self.append_key_value("Descriptor Read State", record.get("descriptor_state", ""))
            if record.get("descriptor_error"):
                self.append_key_value("Descriptor Error", record.get("descriptor_error"))
            self.append_info("\n--- Selection Context ---\n")
            self.append_info("UseIn note: UseIn is legacy/deprecated context. Current backend selection is driven by portals.conf.\n")
            if record.get("_source_issue"):
                self.append_info("Source could not be inventoried; this is NOT proof that the directory contains no backends.\n")
            selected_interfaces = [
                item.get("interface")
                for item in self.interfaces
                if item.get("backend") == record.get("backend_id")
                and item.get("source") == record.get("source")
                and item.get("selected") == "Yes"
            ]
            self.append_key_value("Selected Interfaces", "; ".join(selected_interfaces) if selected_interfaces else "None observed / not determined")
            if self.runtime_loaded:
                running = any(item.get("bus_name") == record.get("dbus_name") for item in self.runtime_records)
                self.append_key_value("Running Bus State", "Running" if running else "Not observed")
            else:
                self.append_key_value("Running Bus State", "Not checked — open Runtime view")
            return

        if view == "Interfaces":
            self.append_info("--- Declared Backend Interface ---\n")
            self.append_key_value("Interface", record.get("interface", ""))
            self.append_key_value("Backend", record.get("backend", ""))
            self.append_key_value("D-Bus Name", record.get("dbus_name", ""))
            self.append_key_value("Descriptor Path", record.get("source", ""))
            self.append_info("\n--- Selection ---\n")
            self.append_key_value("Selected", record.get("selected", ""))
            self.append_key_value("Effective Configuration", record.get("effective_config") or "Not found")
            self.append_key_value("Selection Note", record.get("selection_note", ""))
            self.append_info("Selection note: Selected means selected by the effective local portal configuration. It does not prove that a portal request will succeed.\n")
            return

        if view == "Configuration":
            self.append_info("--- Portal Configuration ---\n")
            self.append_key_value("Path", record.get("source", ""))
            self.append_key_value("Config File", record.get("config_file", ""))
            self.append_key_value("Scope", record.get("scope", ""))
            self.append_key_value("Desktop Applicability", record.get("desktop", ""))
            self.append_key_value("Lookup Position", record.get("lookup_position", ""))
            self.append_key_value("State", record.get("effective_state", ""))
            self.append_key_value("Parse State", record.get("parse_state", ""))
            if record.get("parse_error"):
                self.append_key_value("Parse Error", record.get("parse_error"))
            self.append_info("\n--- [preferred] ---\n")
            self.append_key_value("default", record.get("default_backends_raw") or (
                "Not determined" if record.get("parse_state") != "observed" else "None reported"
            ))
            overrides = record.get("overrides", {})
            if overrides:
                for interface, backends in overrides.items():
                    self.append_key_value(interface, backends)
            else:
                self.append_info(
                    "Interface overrides could not be inspected.\n" if record.get("parse_state") != "observed"
                    else "No interface-specific overrides reported.\n"
                )
            self.append_key_value("Build Root Basis", "Installed metadata / inspector override or XDG location" if record.get("root_verified", True) else "Conventional assumption (not build-verified)")
            self.append_info("\nLookup note: configuration follows XDG Desktop Portal precedence; inaccessible higher-priority locations can make the winner undetermined.\n")
            return

        if view == "Runtime":
            self.append_info("--- Running Portal Service ---\n")
            self.append_key_value("Bus Name", record.get("bus_name", ""))
            self.append_key_value("Role", record.get("role", ""))
            self.append_key_value("Owner / Unique Name", record.get("owner", ""))
            pid = record.get("pid", 0)
            self.append_key_value("PID", pid if pid else "Not reported")
            self.append_key_value("Backend / Frontend", record.get("component", ""))
            self.append_key_value("State", record.get("state", ""))
            self.append_key_value("Runtime Source", record.get("runtime_source", ""))
            self.append_info("\nRuntime note: only already-acquired session-bus names are listed. XDG Portals does not activate an absent portal service merely to inspect it.\n")

    def metadata_details_for_export(self, record):
        original_info = self.info_text
        temp = QTextEdit()
        self.info_text = temp
        try:
            self._render_record_details(record)
            return temp.toPlainText()
        finally:
            self.info_text = original_info

    @staticmethod
    def sources_text():
        return (
            "XDG Portals is read-only. It inventories portal installation and configuration without calling portal request methods.\n\n"
            "Desktop and session identity\n"
            "  XDG_CURRENT_DESKTOP\n"
            "  XDG_SESSION_TYPE\n"
            "  XDG_CONFIG_HOME / XDG_CONFIG_DIRS\n"
            "  XDG_DATA_HOME / XDG_DATA_DIRS\n\n"
            "Installed backend descriptors\n"
            "  XDG data directories under xdg-desktop-portal/portals/*.portal\n"
            "  Preserved descriptor fields: DBusName, Interfaces, UseIn\n"
            "  Legacy UseIn is never used for desktop-based selected-backend filtering.\n\n"
            "Backend-selection configuration\n"
            "  xdg-desktop-portal/{DESKTOP-}portals.conf in documented lookup precedence\n"
            "  [preferred] default=... and interface-specific org.freedesktop.impl.portal.* overrides\n"
            "  Build-time sysconfdir/datadir are checked through installed pkg-config data, when available.\n"
            "  Otherwise conventional roots are explicitly labelled unverified in Overview.\n"
            "  If search roots cannot be verified, backend selection is reported as Not determined.\n"
            "  Inspector-only path overrides: LINSPECTACLES_XDG_PORTAL_SYSCONFDIR and LINSPECTACLES_XDG_PORTAL_DATADIR.\n"
            "  Higher-priority unreadable roots mean selection cannot be determined.\n\n"
            "Already-running runtime state\n"
            "  Session D-Bus acquired-name inventory only, queried explicitly by opening Runtime\n"
            "  busctl --user --acquired list when available; org.freedesktop.DBus.ListNames fallback\n"
            "  No absent service is activated for inspection\n"
            "  Frontend installation is checked separately using existing D-Bus activation descriptors/PATH, without bus calls.\n\n"
            "Frontend / backend model\n"
            "  org.freedesktop.portal.Desktop is the application-facing portal frontend.\n"
            "  Desktop-specific backends implement org.freedesktop.impl.portal.* interfaces and are selected by portals.conf.\n"
            "  UseIn in .portal descriptors is deprecated legacy context; current selection is configuration-driven.\n\n"
            "Boundary\n"
            "  XDG Portals does not generically introspect D-Bus object members; generic bus/object/interface inspection belongs to D-Bus Inspector.\n"
            "  A declared interface or selected backend is not claimed to be functionally successful merely because it is installed or configured.\n\n"
            "Technical reference\n"
            "  https://flatpak.github.io/xdg-desktop-portal/docs/\n"
            "  https://flatpak.github.io/xdg-desktop-portal/docs/writing-a-new-backend.html\n"
            "  https://flatpak.github.io/xdg-desktop-portal/docs/configuration-file.html\n"
            "  https://flatpak.github.io/xdg-desktop-portal/docs/portals.conf.html"
        )

    def show_options(self):
        dialog = XDGPortalsOptionsDialog(self)
        dialog.exec()

    def _add_shortcut(self, sequence, callback):
        shortcut = QShortcut(QKeySequence(sequence), self)
        shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        shortcut.activated.connect(callback)
        self._shortcuts.append(shortcut)
        return shortcut

    def _install_shortcuts(self):
        self._add_shortcut("F3", self.toggle_metadata_panel)
        self._add_shortcut("Ctrl+L", self.toggle_details_orientation)
        self._add_shortcut("Ctrl+/", self.show_options)
        self._add_shortcut("Shift+F5", self.load_modules)

    def toggle_details_orientation(self):
        target = "vertical" if self.details_orientation == "horizontal" else "horizontal"
        self.set_details_orientation(target, persist=True)

    def _load_metadata_panel_visibility(self):
        settings = QSettings("brunonlinespace", "XDG Portals")
        value = settings.value("metadata_panel_visible", True)
        if isinstance(value, str):
            visible = value.strip().lower() not in {"0", "false", "no", "off"}
        else:
            visible = bool(value)
        self.set_metadata_panel_visible(visible, persist=False)

    def set_metadata_panel_visible(self, visible, *, persist=True):
        self.metadata_panel_visible = bool(visible)
        details_panel = self.splitter.widget(1)
        if details_panel is not None:
            details_panel.setVisible(self.metadata_panel_visible)
        if self.metadata_panel_visible:
            self.set_details_orientation(self.details_orientation, persist=False)
        if persist:
            settings = QSettings("brunonlinespace", "XDG Portals")
            settings.setValue("metadata_panel_visible", self.metadata_panel_visible)
            settings.sync()

    def toggle_metadata_panel(self):
        self.set_metadata_panel_visible(not self.metadata_panel_visible, persist=True)

    def _load_details_orientation(self):
        settings = QSettings("brunonlinespace", "XDG Portals")
        orientation = str(settings.value("details_orientation", "horizontal") or "horizontal").lower()
        if orientation not in {"horizontal", "vertical"}:
            orientation = "horizontal"
        self.set_details_orientation(orientation, persist=False)

    def set_details_orientation(self, orientation, *, persist=True):
        orientation = str(orientation or "horizontal").lower()
        if orientation not in {"horizontal", "vertical"}:
            orientation = "horizontal"
        self.details_orientation = orientation

        details_panel = self.splitter.widget(1)
        details_layout = details_panel.layout() if details_panel is not None else None
        if orientation == "vertical":
            self.splitter.setOrientation(Qt.Orientation.Vertical)
            if details_layout is not None:
                details_layout.setContentsMargins(0, 8, 0, 0)
            self.splitter.setSizes([430, 330])
        else:
            self.splitter.setOrientation(Qt.Orientation.Horizontal)
            if details_layout is not None:
                details_layout.setContentsMargins(8, 0, 0, 0)
            self.splitter.setSizes([480, 700])

        if persist:
            settings = QSettings("brunonlinespace", "XDG Portals")
            settings.setValue("details_orientation", orientation)
            settings.sync()


def create_applet(parent=None):
    return XDGPortalsTab(parent=parent)


def run_standalone():
    import sys
    from PyQt6.QtGui import QIcon
    from PyQt6.QtWidgets import QApplication, QMainWindow
    from ._support import STANDALONE_STYLESHEET

    app = QApplication(sys.argv)
    app.setApplicationName(APPLET_NAME)
    app.setOrganizationName(APPLET_AUTHOR)
    icon_path = Path(__file__).resolve().parent / "icon.png"
    if icon_path.is_file():
        app.setWindowIcon(QIcon(str(icon_path)))
    app.setStyleSheet(STANDALONE_STYLESHEET)
    window = QMainWindow()
    if icon_path.is_file():
        window.setWindowIcon(QIcon(str(icon_path)))
    window.setWindowTitle(f"{APPLET_NAME} {APPLET_VERSION} — LinSpectacles Applet")
    window.resize(1200, 780)
    window.setCentralWidget(create_applet())
    window.show()
    return app.exec()
