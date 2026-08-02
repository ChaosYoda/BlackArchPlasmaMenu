#!/usr/bin/env python3
"""Generate a BlackArch menu for KDE Plasma.

Builds a "BlackArch" entry in the application launcher with one submenu per
BlackArch group (Exploitation, Wireless, Recon, ...), each listing the tools from
that group that are actually installed on this system. Group membership and
installed state both come from pacman, so the menu only ever shows tools you have.

Installing asks which launcher is on the panel, because only the cascading
Application Menu draws submenus; Application Launcher needs the groups flat.

Usage:
    ./BlackArchPlasmaMenuTool.py                 # print this usage
    ./BlackArchPlasmaMenuTool.py --install       # install for the current user
    ./BlackArchPlasmaMenuTool.py --install -v --dry-run   # show what would change
    ./BlackArchPlasmaMenuTool.py --system        # install for all users (needs root)
    ./BlackArchPlasmaMenuTool.py --fix-dirty     # clear a stuck menu state, no reinstall
    ./BlackArchPlasmaMenuTool.py --uninstall     # remove everything it generated

Install more tools with `sudo pacman -S blackarch-<group>`, then re-run this
script to pick them up.
"""

from __future__ import annotations

import argparse
import sys

from blackarch_menu import (
    Generator,
    Layout,
    PacmanError,
    Repair,
    Session,
    collect_tools,
    refresh_caches,
    require_writable,
    summarise,
    uninstall_all,
)

# Plasma sets XDG_MENU_PREFIX=plasma-, so <DefaultMergeDirs/> in
# plasma-applications.menu resolves to plasma-applications-merged. The unprefixed
# directory is written too because some Plasma builds and other Qt launchers read
# the generic applications.menu instead.
MERGE_DIRS = ["applications-merged", "plasma-applications-merged"]

# plasma-applications.menu's root <Menu> is named "Applications"; a merged
# fragment has to use the same root name to be grafted onto it.
ROOT_MENU_NAME = "Applications"

MENU_CACHE_COMMANDS = [["kbuildsycoca6"], ["kbuildsycoca5"]]

# kbuildsycoca only re-reads what it thinks changed; after clearing a dirty state
# the cache has to be rebuilt from scratch or the stale menu simply comes back.
FULL_REBUILD_FLAG = "--noincremental"

# Which shape the menu takes is not ours to guess: it depends on the launcher the
# user has on their panel, and picking wrong is silently wrong -- nested groups do
# not render in Kickoff, and flat ones needlessly clutter a launcher that could
# have nested them.
LAUNCHER_PROMPT = """\
Which launcher is on your panel? (right click the start button -> Show Alternatives)

  1) Application Launcher -- the Plasma default. Draws top-level categories only,
     so the groups have to be installed flat, as "BlackArch Wireless" and so on.
  2) Application Menu -- the cascading one. Draws submenus, so the groups can sit
     inside a single "BlackArch" menu.

Choice [1]: """


def ask_nested() -> bool:
    """Ask which launcher is in use. True when it can render submenus."""
    if not sys.stdin.isatty():
        return False  # unattended: flat is the shape every launcher draws
    while True:
        choice = input(LAUNCHER_PROMPT).strip() or "1"
        if choice in ("1", "2"):
            return choice == "2"
        print("Enter 1 or 2.\n")


def refresh_commands(layout: Layout, full: bool) -> list[list[str]]:
    commands = [
        [*command, FULL_REBUILD_FLAG] if full else list(command)
        for command in MENU_CACHE_COMMANDS
    ]
    # update-desktop-database exits 1 when given no directory (it defaults to the
    # system ones, which are not ours to write), and /usr/share/applications is
    # maintained by a pacman hook anyway -- so only a user install needs it.
    if not layout.system_wide:
        commands.append(["update-desktop-database", str(layout.applications.parent)])
    return commands


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate KDE Plasma menu entries for installed BlackArch tools.",
    )
    parser.add_argument(
        "--install",
        action="store_true",
        help="write the menu for the tools installed right now",
    )
    parser.add_argument(
        "--system",
        action="store_true",
        help="install for all users under /usr/share (requires root)",
    )
    parser.add_argument(
        "--uninstall",
        action="store_true",
        help="remove every file a previous run generated",
    )
    parser.add_argument(
        "--fix-dirty",
        action="store_true",
        help="Fix dirty menu state where the new menu might not show correctly",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="report what would change without touching the filesystem",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="expand the tree to every tool, and list each file written or removed",
    )
    args = parser.parse_args()

    installing = args.install or args.system
    if not (installing or args.uninstall or args.fix_dirty):
        # Nothing was asked for. Writing a menu is not what a bare run should do.
        parser.print_help()
        return 0

    session = Session.detect()
    layout = (
        Layout.system(MERGE_DIRS) if args.system else Layout.user(MERGE_DIRS, session)
    )

    if args.uninstall:
        # An install may be user-level or system-wide and nothing on disk records
        # which, so sweep both rather than reporting "removed 0" while a full
        # install sits in /usr/share.
        removed, needs_root = uninstall_all(
            [Layout.user(MERGE_DIRS, session), Layout.system(MERGE_DIRS)],
            dry_run=args.dry_run,
        )
        verb = "Would remove" if args.dry_run else "Removed"
        print(f"{verb} {len(removed)} path(s).")
        if args.verbose:
            for path in removed:
                print(f"  {path}")
        if needs_root:
            print(
                f"\n{len(needs_root)} system-wide path(s) still installed under "
                "/usr/share and /etc/xdg. Re-run with sudo to remove them."
            )
            if args.verbose:
                for path in needs_root:
                    print(f"  {path}")
    elif installing:
        if not args.dry_run:
            require_writable(layout)
        generator = Generator(layout, dry_run=args.dry_run, verbose=args.verbose)
        try:
            tools, skipped = collect_tools()
        except PacmanError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1

        if not tools:
            print(
                "No BlackArch tools found. Install some with "
                "`sudo pacman -S blackarch-<group>` and re-run."
            )
            return 1

        nested = ask_nested()
        generator.generate(tools, root_menu_name=ROOT_MENU_NAME, nested=nested)
        summarise(tools, skipped, show_tools=args.verbose, nested=nested)
        verb = "Dry run:" if args.dry_run else "Wrote"
        suffix = " would be written" if args.dry_run else ""
        print(f"\n{verb} {len(generator.written)} file(s){suffix}.")

    if args.fix_dirty:
        # Clear anything downstream that could hide the menu we just wrote.
        actions = Repair(layout, session=session, dry_run=args.dry_run).run()
        verb = "Would fix" if args.dry_run else "Fixed"
        print(f"\n{verb} {len(actions)} dirty menu state(s).")
        for action in actions:
            print(f"  {action}")

    refresh_caches(
        refresh_commands(layout, args.fix_dirty), dry_run=args.dry_run, session=session
    )
    if not args.dry_run and installing:
        print("Menu rebuilt. If it has not appeared, log out and back in.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
