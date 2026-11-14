# XDG Portals

**Expose. Explore. Explain.**

XDG Portals is a read-only inspector for the local XDG Desktop Portal frontend/backend architecture, installed backend descriptors, declared interfaces, backend-selection configuration, and already-running portal services without activation.

Current release: **0.0.3**

Repository: <https://github.com/linspectacles/xdg-portals>


<p align="center">
  <a href="https://github.com/brunonlinespace/brunonlinespace/blob/main/linspectacles/xdg-portals.png">
    <img
      src="https://raw.githubusercontent.com/brunonlinespace/brunonlinespace/main/linspectacles/xdg-portals.png"
      alt="XDG Portals screenshot"
      width="900"
    >
  </a>
</p>
## What XDG Portals is

XDG Portals answers a focused question: **which portal components are installed, what interfaces do their backends declare, how is backend selection configured, and which portal services are already running?**

It understands portal-specific frontend/backend/configuration semantics while leaving generic bus/object/interface inspection to D-Bus Inspector.

## Highlights

- Five views: **Overview**, **Backends**, **Interfaces**, **Configuration**, and **Runtime**.
- XDG desktop/session identity.
- Installed `.portal` backend descriptors preserving `DBusName`, `Interfaces`, and `UseIn`.
- `portals.conf` backend-selection precedence and interface-specific overrides.
- Verified build-time roots from installed `pkg-config` data where available.
- Conventional fallback roots explicitly marked unverified.
- Runtime view queried only when explicitly opened.
- Already-running session-bus names only; absent services are not activated.
- Search, sortable inventories, Metadata Details, export, and persistent presentation settings.

## Data sources and acquisition

### Desktop and session identity

- `XDG_CURRENT_DESKTOP`
- `XDG_SESSION_TYPE`
- `XDG_CONFIG_HOME` / `XDG_CONFIG_DIRS`
- `XDG_DATA_HOME` / `XDG_DATA_DIRS`

### Installed backend descriptors

- XDG data directories under `xdg-desktop-portal/portals/*.portal`.

### Backend-selection configuration

- `xdg-desktop-portal/{DESKTOP-}portals.conf`
- `[preferred] default=...`
- interface-specific `org.freedesktop.impl.portal.*` overrides.
- installed xdg-desktop-portal `pkg-config` build metadata when available.

Inspector-only path overrides:

- `LINSPECTACLES_XDG_PORTAL_SYSCONFDIR`
- `LINSPECTACLES_XDG_PORTAL_DATADIR`

### Runtime

- `busctl --user --acquired list` where available.
- `org.freedesktop.DBus.ListNames` fallback.

Runtime state is acquired only when opening Runtime. No absent service is activated.

## Interface

The five views separate overall installation/session context, backend descriptors, implementation interfaces, configuration precedence, and already-running runtime names.

Legacy `UseIn` remains descriptor evidence but is not treated as the current desktop-selection authority; backend selection is configuration-driven.

## Read-only and scope boundaries

XDG Portals does not call portal request methods, open portal dialogs, edit portal configuration, install/remove backends, activate missing services, or generically introspect D-Bus object members.

A declared interface or configured backend is **not** proof that a portal request will succeed.

**D-Bus Inspector** remains authoritative for generic D-Bus inspection.

## Useful keyboard shortcuts

| Command | Shortcut |
| --- | --- |
| Toggle Metadata Details | `F3` |
| Toggle Metadata Details layout | `Ctrl+L` |
| Refresh current inventory | `Shift+F5` |
| Options | `Ctrl+/` |

## Running from source

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install PyQt6
python3 -m linspectacles_xdg_portals.standalone
```

`busctl` and `pkg-config` are optional sources used only by the implemented acquisition paths.

No RPM installation instructions are included in this README.

## LinSpectacles Hub

This applet can run independently, but it can also be installed and used inside **[LinSpectacles Hub](https://github.com/linspectacles/linspectacles-hub)**.

LinSpectacles Hub is the optional workbench for the LinSpectacles applet family. It provides shared applet discovery, navigation and management while each inspector remains independently runnable.

To install a portable or user applet through the Hub, open **Configuration... → Applets** and add the applet ZIP. Once discovered, the applet can be enabled and opened from the Hub navigation.

System-installed applets are discovered by the Hub from its system applet store and remain managed by the system package manager.

## Source layout and LinSpectacles integration

```text
linspectacles_xdg_portals/
├── __init__.py
├── standalone.py
├── LICENSE
├── applet.json
├── README.md
└── xdg_portals/
    ├── __init__.py
    ├── applet.py
    ├── _support.py
    └── icon.png
```

## Configuration

XDG Portals persists implemented presentation settings. Its inspector-only path overrides do not alter xdg-desktop-portal's own configuration.

## Scope

XDG Portals owns **portal-specific installation, backend, interface-selection and already-running runtime evidence**. **D-Bus Inspector** owns generic D-Bus state, **Display Server Inspector** owns graphical-session/display-stack evidence, and **Desktop Integration** owns desktop-entry/MIME registration.

## License

GNU General Public License v3.0 or later. See [`LICENSE`](LICENSE).

## Links

- LinSpectacles organisation: <https://github.com/linspectacles/>
- LinSpectacles Hub: <https://github.com/linspectacles/linspectacles-hub>
- Repository: <https://github.com/linspectacles/xdg-portals>
- Issues: <https://github.com/linspectacles/xdg-portals/issues>

<p align="center">
  <a href="https://github.com/linspectacles/xdg-portals">
    <img
      src="xdg_portals/icon.png"
      alt="XDG Portals"
      width="256"
    >
  </a>
</p>
