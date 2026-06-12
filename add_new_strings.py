#!/usr/bin/env python3
"""
add_new_strings.py — Adds new context blocks to all .ts files.

Run once after adding new C++ source files that haven't been processed
by lupdate yet. Inserts context blocks with unfinished translations,
or English copies for English variants.

Usage:
    python halkyi8n/add_new_strings.py
"""

import sys
import io
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ENGLISH_LANGS = {"en_AU", "en_CA", "en_GB", "en_NZ"}

# All new strings: {ContextClass: [source_string, ...]}
NEW_STRINGS = {
    "HalkyNavBar": [
        "Expand navigation",
        "Collapse navigation",
        "Home",
        "Library",
        "Modpacks",
        "Mods",
        "Resource Packs",
        "Shaders",
        "Add Instance",
        "Accounts",
        "Folders",
        "Settings",
        "Help",
    ],
    "NewsPanel": [
        "News",
        "More...",
        "No news available",
        "Loading news...",
    ],
    "HomePage": [
        "Welcome back, %1!",
        "Playing as %1",
        "Welcome to Halky Launcher!",
        "No account selected",
        "Recently Played",
        "View All",
        "Last played: %1",
        "Never played",
        "Play",
        "+ Add Instance",
        "No instances yet. Use the + button in the sidebar or click 'Add Instance' to get started.",
    ],
    "BrowsePage": [
        "Browse Modpacks",
        "Browse Mods",
        "Browse Resource Packs",
        "Browse Shader Packs",
        "Search and install ready-made modpacks from Modrinth, CurseForge, FTB, ATLauncher and more.",
        "Search and install mods from Modrinth and CurseForge for a selected instance.",
        "Search and install resource packs from Modrinth and CurseForge for a selected instance.",
        "Search and install shader packs from Modrinth and CurseForge for a selected instance.",
        "Browse Modpacks...",
        "Browse Mods...",
        "Browse Resource Packs...",
        "Browse Shader Packs...",
        "For instance:",
        "Search...",
        "No instances available",
        "Tip: Clicking 'Browse Modpacks...' will open the full modpack browser where you can install any pack from Modrinth, CurseForge, FTB and more.",
        "Tip: Select an instance first, then click Browse to open the resource browser for that instance.",
    ],
    "OnboardingOverlay": [
        "Skip",
        "Next",
        "Done",
        "%1 / %2",
        "Navigation Sidebar",
        "Use the sidebar on the left to switch between your Library, browse Modpacks, Mods, Resource Packs and Shaders. Click the ☰ button at the top to expand labels.",
        "Add Instance",
        "Click the + button in the sidebar or use the '+ Add Instance' button in the Library to create a new Minecraft instance.",
        "Your Library",
        "The Library shows all your Minecraft instances. Double-click one to launch it, or select it for more options.",
        "News",
        "The News panel on the right shows the latest Halky Launcher updates and announcements.",
    ],
    "MainWindow": [
        "Library",
        "Edit",
        "Delete",
        "More",
        "Play",
    ],
    "WizardSidebar": [
        "Quick Setup",
    ],
    "AppearanceWidget": [
        "None",
    ],
    "SetupWizard": [
        "Next >",
        "< Back",
        "Finish",
        "Refresh",
        "%1 Quick Setup",
    ],
    "LanguageWizardPage": [
        "Language",
        "Select the language to use in %1",
    ],
    "JavaWizardPage": [
        "Java",
        "Choose Java memory allocation and whether %1 should manage Java automatically.",
    ],
    "AutoJavaWizardPage": [
        "Automatic Java",
        "Automatically download the correct Java version for each Minecraft version.",
        "A new feature was added that can automatically download and switch to the correct Java version for each instance. Would you like to enable it?",
        "Enable automatic Java download",
        "Recommended — %1 will download and manage Java automatically.",
        "Keep manual Java settings",
        "You will manage Java installation and selection yourself.",
    ],
    "PasteWizardPage": [
        "Paste Service",
        "The default log upload service has changed.",
        "The default paste service has changed to mclo.gs. Choose what to do with your existing paste settings.",
        "Use new default service (mclo.gs)",
        "Recommended — switch to the new, faster mclo.gs service.",
        "Keep previous settings",
        "Your existing custom paste service URL will be preserved.",
    ],
    "ThemeWizardPage": [
        "Appearance",
        "Choose a theme and icon set that suits you.",
    ],
    "LoginWizardPage": [
        "Account",
        "Add Account",
        "Sign in to play Minecraft. You can add more accounts later in Settings.",
        "Please enter your desired username to add your offline account.",
        "Please enter authentication server URL, your username and password.",
        "  Microsoft account  (Minecraft: Java Edition)",
        "  Ely.by account",
        "  Offline account  (no authentication)",
        "  Custom auth server",
    ],
    "FlameAPIKeyWizardPage": [
        "CurseForge API",
        "CurseForge API Key",
        "Enable full CurseForge modpack downloads.",
        "Warning: Using the official CurseForge app's API key may violate CurseForge's terms of service.",
        "Fetching the key allows %1 to download all mods in a modpack automatically, without requiring manual downloads. This can also be done later in Settings.",
        "Fetch Official Launcher's Key",
    ],
}


def xml_escape(s: str) -> str:
    return (
        s.replace("&", "&amp;")
         .replace("<", "&lt;")
         .replace(">", "&gt;")
         .replace('"', "&quot;")
         .replace("'", "&apos;")
    )


def build_context_block(context_name: str, strings: list[str], is_english: bool) -> str:
    messages = []
    for src in strings:
        escaped = xml_escape(src)
        if is_english:
            translation = f"        <translation>{escaped}</translation>"
        else:
            translation = '        <translation type="unfinished"></translation>'
        messages.append(
            f"    <message>\n"
            f"        <source>{escaped}</source>\n"
            f"{translation}\n"
            f"    </message>"
        )
    return f"<context>\n    <name>{context_name}</name>\n" + "\n".join(messages) + "\n</context>"


def context_exists(content: str, context_name: str) -> bool:
    return f"<name>{context_name}</name>" in content


def insert_contexts(ts_path: Path, is_english: bool) -> int:
    content = ts_path.read_text(encoding="utf-8", errors="replace")
    added = 0
    new_blocks = []

    for ctx_name, strings in NEW_STRINGS.items():
        if context_exists(content, ctx_name):
            continue  # already exists, skip
        block = build_context_block(ctx_name, strings, is_english)
        new_blocks.append(block)
        added += 1

    if not new_blocks:
        return 0

    # Insert before closing </TS> tag
    insert_point = content.rfind("</TS>")
    if insert_point == -1:
        print(f"  ⚠️  No </TS> found in {ts_path.name}, skipping")
        return 0

    insertion = "\n" + "\n\n".join(new_blocks) + "\n"
    new_content = content[:insert_point] + insertion + content[insert_point:]
    ts_path.write_text(new_content, encoding="utf-8")
    return added


def main():
    ts_dir = Path(__file__).parent
    ts_files = sorted(ts_dir.glob("*.ts"))

    if not ts_files:
        print("No .ts files found.")
        return

    total_files = 0
    total_contexts = 0

    for ts_path in ts_files:
        lang = ts_path.stem
        if lang == ".template":
            continue

        is_english = lang in ENGLISH_LANGS
        added = insert_contexts(ts_path, is_english)

        if added > 0:
            label = "(English copy)" if is_english else "(unfinished)"
            print(f"  ✅  [{lang:18}] +{added} context(s) {label}")
            total_files += 1
            total_contexts += added
        # else: silently skip already-done files

    print(f"\nDone: updated {total_files} files, added {total_contexts} context blocks total.")
    print("\nRun translate_ts.py for each new string to fill in non-English translations.")


if __name__ == "__main__":
    main()
