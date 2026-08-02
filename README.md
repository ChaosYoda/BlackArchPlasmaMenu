# BlackArchPlasmaMenuTool

Generates **BlackArch** categories in your application launcher, one per BlackArch
group (Exploitation, Wireless, Recon, Cracker, ...) listing the tools from that
group that are **actually installed** on your machine.

Group membership and installed state both come from `pacman`, so the menu never
shows a tool you do not have. Install more with `sudo pacman -S blackarch-<group>`
and re-run the generator to pick them up.

```
Application launcher
├── BlackArch Automation
├── BlackArch Bluetooth
├── BlackArch Cracker
│   ├── asleap
│   ├── auto-eap
│   └── ...
├── BlackArch DoS
│   ├── hwk
│   ├── slowloris
│   └── ...
└── ...
```

## Usage (KDE Plasma)

```sh
./BlackArchPlasmaMenuTool.py               # install for the current user
./BlackArchPlasmaMenuTool.py --dry-run -v  # show what would be written, change nothing
./BlackArchPlasmaMenuTool.py --system      # install for all users (needs root)
./BlackArchPlasmaMenuTool.py --fix-dirty   # reinstall, clearing a stuck menu state
./BlackArchPlasmaMenuTool.py --nested      # one BlackArch menu with the groups inside
./BlackArchPlasmaMenuTool.py --uninstall   # remove everything it generated
```

Requires Python 3.9+ and `pacman`. No third-party modules.

The umbrella `blackarch` group is skipped on purpose — it contains every tool in
the repo and would duplicate the whole tree into a single unusable submenu.

## Note for Plasma

Plasma's **Kickoff** ("Application Launcher") and the **Cinnamon** menu applet only
draw *top-level* categories. Anything nested below one is flattened away, so a
single `BlackArch` parent menu shows up as one undivided category of 100+ tools
with no groups in sight.

The groups are therefore installed at the top level by default, named
`BlackArch <Group>`, which every launcher can render. `--nested` puts them back
under one `BlackArch` parent — tidier, and fine if you use a cascading launcher
(right click the start button → *Show Alternatives* → *Application Menu*) or
`kmenuedit`, but the groups will not appear in Kickoff or Cinnamon.

## When the menu will not appear

A correctly generated menu can still be hidden by something downstream of it, and
that state survives reinstalling — regenerating cannot clear it. `--fix-dirty`
undoes all of it:

* **Menu-editor overrides.** `plasma-applications.menu` merges
  `~/.config/menus/applications-kmenuedit.menu` *last*, so it beats every fragment
  this script writes. Saving in kmenuedit while the menus are missing (mid-uninstall,
  say) records them as `<Deleted/>` — and because `<Deleted/>` hides them from
  kmenuedit too, there is nothing left in the UI to undelete. Cinnamon's and GNOME's
  editors write an override copy of the whole menu file with the same effect.
* **Hidden entries.** Hiding a single app writes an `<Exclude>` plus a `.hidden`
  menu, or shadows the entry with a user-level `.desktop` carrying `Hidden=true`.
* **Malformed fragments.** A `.menu` file that is not well-formed XML is dropped
  whole by the menu builder, so one stale broken fragment can take working entries
  down with it. Broken `blackarch*.menu` files are renamed to `.disabled` rather
  than deleted.
* **Stale caches.** `~/.cache/ksycoca*` is cleared and rebuilt from scratch with
  `kbuildsycoca --noincremental`.

Every edited file is backed up alongside itself as `.bak`, and each repair is
printed. Under `sudo`, the repair and the cache rebuild are applied to the desktop
user's home rather than root's — running `kbuildsycoca` as root rebuilds root's
cache and leaves your launcher unchanged, which is a common reason `--system`
appears to do nothing.

## What gets written

For a user-level install:

| Path | Contents |
| --- | --- |
| `~/.local/share/applications/blackarch/` | one `.desktop` per installed tool |
| `~/.local/share/desktop-directories/blackarch*.directory` | menu titles and icons |
| `~/.config/menus/*-merged/blackarch.menu` | the XML that grafts the groups onto the menu |

`--uninstall` removes all of the above. Nothing outside these paths is touched,
and no system files are modified. No helper scripts or wrappers are generated.

`--fix-dirty` additionally edits `~/.config/menus/*.menu` and clears
`~/.cache/ksycoca*` — see [When the menu will not appear](#when-the-menu-will-not-appear).

## How tools are launched

Every entry's `Exec` is the **bare command with no arguments**, so a menu editor
shows the binary as the program and an empty argument list.

Three cases are handled:

* **Ships its own `.desktop` file** (Burp Suite, Tor Browser, SDR++, Kismon) —
  the upstream entry is mirrored, keeping its real name, icon and arguments, and
  GUI apps correctly launch without a terminal. Invalid upstream icon names such
  as `Icon=loic.png` are corrected on the way through.
* **Ships binaries in `/usr/bin`** — one entry per package pointing at its main
  command. Packages such as `rfidiot` install 35 executables; listing them all
  would bury the menu, so `pick_binary()` chooses the one that best matches the
  package name. `COMMAND_OVERRIDES` in `blackarch_menu.py` handles the handful it
  gets wrong (`hwk` → `hawk`, `radare2-cutter` → `cutter`, ...).
* **Ships data only** (Windows executables under `/usr/share/windows/`, wordlists,
  firmware) — these have no command of their own, so the entry opens the package
  directory with `xdg-open` and those groups are not silently empty.

Packages with no launchable command and no topical group — mirrorlists, DKMS
drivers, kernel modules — are skipped and reported at the end of the run.

Because the command runs bare, a CLI tool that only prints a usage screen will
exit immediately and its terminal window will close with it. Run those from a
terminal you opened yourself. Many of these tools also need root; the menu does
not assume that.

## Previewing the menu

`--dry-run` prints the tree that would be generated and writes nothing. Add `-v`
to expand every group down to its individual tools. The counts are only there to
show what was detected — they do not appear in the real menu.

```
$ ./BlackArchPlasmaMenuTool.py --dry-run
Menu structure will look as follows:

*Application launcher*
├── BlackArch Automation (4 tools)
├── BlackArch Bluetooth (2 tools)
├── BlackArch Cracker (16 tools)
├── BlackArch DoS (4 tools)
...
└── BlackArch Wireless (91 tools)

23 submenus, 106 tools (191 entries; tools in several groups appear in each).
```

## Layout

* `blackarch_menu.py` — all the logic: pacman queries, command resolution, file
  generation. Desktop-environment agnostic.
* `BlackArchPlasmaMenuTool.py` — Plasma front-end (merge dirs + `kbuildsycoca`).
* `blackarchgroups.txt` — reference copy of `pacman -Sg | grep blackarch`. Not read
  by the generator; groups are discovered live.
