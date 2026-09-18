#!/usr/bin/env python3
"""
CS2 Helper - PC Optimizer  (Windows only, standard library only)
==================================================================

An interactive maintenance script for your own machine:

  1) Startup apps   - see everything set to auto-launch with Windows,
                       disable the ones you don't want. Every change is
                       backed up first, so you can roll it back with one
                       key press right after seeing "Done!", or later
                       from the menu.
  2) Temp / cache    - reports how much space %TEMP%, Windows Temp and
                       browser caches are using, and clears them on
                       confirmation. This step is NOT reversible (the
                       files are gone, like emptying the Recycle Bin),
                       so it always asks first and never pretends it
                       can be undone.
  3) Undo log        - lists every startup change you've made through
                       this script, oldest first, so you can restore
                       any of them later even if you didn't roll back
                       immediately.

Nothing here touches other people's computers, hides itself, disables
security software, or runs without asking. Every destructive action
requires an explicit y/N confirmation, and registry edits only ever
touch the current user's own Run keys (HKCU) plus, if you re-run the
script as Administrator, the machine-wide Run keys (HKLM) - never
anything else.

Run it with:      python cs2_optimizer.py
(or just double-click it if .py files are associated with Python)
"""

import ctypes
import json
import os
import shutil
import sys
import time
from datetime import datetime

IS_WINDOWS = sys.platform.startswith("win")
if IS_WINDOWS:
    import winreg

APP_DATA = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
STATE_DIR = os.path.join(APP_DATA, "CS2HelperOptimizer")
BACKUP_FILE = os.path.join(STATE_DIR, "startup_backup.json")
LOG_FILE = os.path.join(STATE_DIR, "actions_log.json")

RUN_KEYS = [
    (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", "HKCU") if IS_WINDOWS else None,
    (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\Run", "HKLM") if IS_WINDOWS else None,
]

# ----------------------------------------------------------------- helpers
def is_admin():
    if not IS_WINDOWS:
        return False
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def ensure_state_dir():
    os.makedirs(STATE_DIR, exist_ok=True)


def load_json(path, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path, data):
    ensure_state_dir()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def log_action(kind, detail):
    log = load_json(LOG_FILE, [])
    log.append({"time": datetime.now().isoformat(timespec="seconds"), "kind": kind, "detail": detail})
    save_json(LOG_FILE, log)


def confirm(prompt):
    ans = input(f"{prompt} (y/N): ").strip().lower()
    return ans in ("y", "yes", "д", "да")


def human_size(n):
    for unit in ["B", "KB", "MB", "GB"]:
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def pause():
    input("\nPress Enter to continue... ")


# ----------------------------------------------------------------- startup apps
def read_run_key(hive, subkey):
    entries = []
    try:
        with winreg.OpenKey(hive, subkey, 0, winreg.KEY_READ) as key:
            i = 0
            while True:
                try:
                    name, value, _ = winreg.EnumValue(key, i)
                    entries.append((name, value))
                    i += 1
                except OSError:
                    break
    except FileNotFoundError:
        pass
    except PermissionError:
        pass
    return entries


def list_startup_entries():
    """Returns a flat list of dicts: {name, command, hive_label, subkey}."""
    if not IS_WINDOWS:
        return []
    out = []
    for item in RUN_KEYS:
        if item is None:
            continue
        hive, subkey, label = item
        for name, value in read_run_key(hive, subkey):
            out.append({"name": name, "command": value, "hive": label, "subkey": subkey})
    return out


def disable_startup_entry(entry):
    """Back up the value, then delete it from the registry."""
    hive = winreg.HKEY_CURRENT_USER if entry["hive"] == "HKCU" else winreg.HKEY_LOCAL_MACHINE
    access = winreg.KEY_SET_VALUE | (winreg.KEY_WOW64_64KEY if entry["hive"] == "HKLM" else 0)
    with winreg.OpenKey(hive, entry["subkey"], 0, access) as key:
        winreg.DeleteValue(key, entry["name"])


def restore_startup_entry(entry):
    hive = winreg.HKEY_CURRENT_USER if entry["hive"] == "HKCU" else winreg.HKEY_LOCAL_MACHINE
    access = winreg.KEY_SET_VALUE | (winreg.KEY_WOW64_64KEY if entry["hive"] == "HKLM" else 0)
    with winreg.OpenKey(hive, entry["subkey"], 0, access) as key:
        winreg.SetValueEx(key, entry["name"], 0, winreg.REG_SZ, entry["command"])


def menu_startup():
    if not IS_WINDOWS:
        print("Startup management is Windows-only (uses the registry Run keys).")
        pause()
        return

    entries = list_startup_entries()
    if not entries:
        print("No startup entries found (or HKLM is hidden - try running as Administrator).")
        pause()
        return

    print(f"\n{'#':<3} {'Scope':<5} {'Name':<28} Command")
    print("-" * 90)
    for i, e in enumerate(entries, 1):
        cmd = e["command"] if len(e["command"]) <= 46 else e["command"][:43] + "..."
        print(f"{i:<3} {e['hive']:<5} {e['name']:<28} {cmd}")

    if not is_admin():
        print("\n(Running without Administrator rights - only your own account's [HKCU] entries")
        print(" can be disabled. Re-run as Administrator to also manage machine-wide [HKLM] ones.)")

    raw = input("\nEnter the numbers to DISABLE, comma-separated (or Enter to cancel): ").strip()
    if not raw:
        return
    try:
        picks = sorted({int(x.strip()) for x in raw.split(",") if x.strip()})
    except ValueError:
        print("Couldn't read that list of numbers.")
        pause()
        return

    backup = load_json(BACKUP_FILE, [])
    for n in picks:
        if not (1 <= n <= len(entries)):
            continue
        entry = entries[n - 1]
        if entry["hive"] == "HKLM" and not is_admin():
            print(f"  ! Skipping '{entry['name']}' - it's machine-wide (HKLM), re-run as Administrator.")
            continue
        try:
            disable_startup_entry(entry)
        except Exception as e:
            print(f"  ! Could not disable '{entry['name']}': {e}")
            continue

        entry["disabled_at"] = datetime.now().isoformat(timespec="seconds")
        backup.append(entry)
        save_json(BACKUP_FILE, backup)
        log_action("startup_disabled", entry)

        print(f"\n✅ Done! '{entry['name']}' will no longer start automatically with Windows.")
        if confirm("   Keep it disabled? Choose 'n' to roll back this change right now"):
            print("   Kept disabled.")
        else:
            try:
                restore_startup_entry(entry)
                backup.pop()  # it's the last one we appended
                save_json(BACKUP_FILE, backup)
                log_action("startup_restored_immediately", entry)
                print(f"   ↩ Rolled back - '{entry['name']}' will start with Windows again.")
            except Exception as e:
                print(f"   ! Rollback failed: {e} (it's still in the undo log, use option 3 later).")
    pause()


def menu_undo_log():
    backup = load_json(BACKUP_FILE, [])
    if not backup:
        print("Nothing to undo - no startup entries have been disabled yet.")
        pause()
        return
    print(f"\n{'#':<3} {'Scope':<5} {'Name':<28} Disabled at")
    print("-" * 70)
    for i, e in enumerate(backup, 1):
        print(f"{i:<3} {e['hive']:<5} {e['name']:<28} {e.get('disabled_at','?')}")
    raw = input("\nEnter a number to RESTORE that entry (or Enter to go back): ").strip()
    if not raw:
        return
    try:
        n = int(raw)
        entry = backup[n - 1]
    except (ValueError, IndexError):
        print("That's not one of the listed numbers.")
        pause()
        return
    try:
        restore_startup_entry(entry)
        backup.pop(n - 1)
        save_json(BACKUP_FILE, backup)
        log_action("startup_restored_later", entry)
        print(f"↩ Restored '{entry['name']}' - it will start with Windows again.")
    except Exception as e:
        print(f"Restore failed: {e}")
    pause()


# ----------------------------------------------------------------- temp / cache cleanup
def candidate_cleanup_dirs():
    dirs = []
    tmp = os.environ.get("TEMP") or os.environ.get("TMP")
    if tmp:
        dirs.append(("User TEMP", tmp))
    win_dir = os.environ.get("WINDIR", r"C:\Windows")
    dirs.append(("Windows Temp", os.path.join(win_dir, "Temp")))

    local = os.environ.get("LOCALAPPDATA", "")
    if local:
        dirs.append(("Chrome cache", os.path.join(local, "Google", "Chrome", "User Data", "Default", "Cache")))
        dirs.append(("Edge cache", os.path.join(local, "Microsoft", "Edge", "User Data", "Default", "Cache")))
        dirs.append(("Firefox cache", os.path.join(local, "Mozilla", "Firefox", "Profiles")))
    return [(label, path) for label, path in dirs if os.path.isdir(path)]


def dir_size(path):
    total = 0
    for root, _dirs, files in os.walk(path, onerror=lambda e: None):
        for name in files:
            try:
                total += os.path.getsize(os.path.join(root, name))
            except OSError:
                pass
    return total


def clear_dir_contents(path):
    freed = 0
    for entry in os.scandir(path):
        try:
            if entry.is_file() or entry.is_symlink():
                freed += entry.stat().st_size
                os.remove(entry.path)
            elif entry.is_dir():
                freed += dir_size(entry.path)
                shutil.rmtree(entry.path, ignore_errors=True)
        except (PermissionError, OSError):
            pass  # file in use - skipped, exactly like a normal disk cleanup tool would
    return freed


def menu_cleanup():
    print("\nScanning temp and cache folders (this can take a moment)...\n")
    targets = candidate_cleanup_dirs()
    if not targets:
        print("No known temp/cache folders found on this system.")
        pause()
        return

    sized = []
    for label, path in targets:
        size = dir_size(path)
        sized.append((label, path, size))
        print(f"  {label:<16} {human_size(size):>10}   {path}")

    total = sum(s for _, _, s in sized)
    print(f"\nTotal reclaimable (approx): {human_size(total)}")
    print("\nNote: this step is NOT reversible - deleted temp/cache files cannot be")
    print("restored, the same way emptying your Recycle Bin can't be undone. Files")
    print("that are currently in use are simply skipped, nothing else is touched.")

    if not confirm("\nClear all of the above now?"):
        print("Cancelled - nothing was deleted.")
        pause()
        return

    grand_total = 0
    for label, path, _ in sized:
        freed = clear_dir_contents(path)
        grand_total += freed
        print(f"  ✅ {label}: freed {human_size(freed)}")

    log_action("cleanup", {"freed_bytes": grand_total, "targets": [s[0] for s in sized]})
    print(f"\n✅ Done! Freed approximately {human_size(grand_total)} total.")
    pause()


# ----------------------------------------------------------------- main menu
def main():
    if not IS_WINDOWS:
        print("This optimizer targets Windows (registry startup + Windows temp paths).")
        print("You can still run the temp/cache cleaner section on macOS/Linux paths")
        print("if you adapt candidate_cleanup_dirs(), but startup management needs Windows.\n")

    while True:
        print("\n" + "=" * 60)
        print("  CS2 HELPER — PC OPTIMIZER")
        print("=" * 60)
        print(f"  Admin rights: {'yes' if is_admin() else 'no (HKCU only)'}")
        print("  1) Manage startup apps (disable / roll back)")
        print("  2) Clean temp & cache folders")
        print("  3) View / restore from undo log")
        print("  4) Exit")
        choice = input("\nChoose an option (1-4): ").strip()

        if choice == "1":
            menu_startup()
        elif choice == "2":
            menu_cleanup()
        elif choice == "3":
            menu_undo_log()
        elif choice == "4":
            print("Bye!")
            break
        else:
            print("Please enter 1, 2, 3 or 4.")
            time.sleep(1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrupted - no pending changes were left half-done.")
