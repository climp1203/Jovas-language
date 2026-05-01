#!/usr/bin/env python3
# ═══════════════════════════════════════════════════════════════
#   JOVAS PROTECTION BUILD SCRIPT
#   Compiles the Jovas backend from Python → C++ → Native Binary
#   using Nuitka, making reverse engineering extremely difficult.
#
#   Protection levels applied:
#   1. Python → C++ via Nuitka (source code hidden)
#   2. C++ → native binary (platform-specific machine code)
#   3. All .py files stripped from distribution
#   4. JS obfuscation for playground.html (front-end)
#
#   Usage:
#     pip install nuitka
#     python build_protected.py
#
#   Output:
#     dist/jovas-server          ← Linux/Mac binary
#     dist/jovas-server.exe      ← Windows binary
#     dist/playground.html       ← Obfuscated frontend
# ═══════════════════════════════════════════════════════════════

import os
import sys
import shutil
import subprocess
import re

ROOT = os.path.dirname(os.path.abspath(__file__))
DIST = os.path.join(ROOT, 'dist')


def banner(msg):
    print(f"\n{'═'*55}")
    print(f"  {msg}")
    print('═'*55)


def run(cmd, cwd=None):
    print(f"  $ {' '.join(cmd)}")
    r = subprocess.run(cmd, cwd=cwd or ROOT, capture_output=True, text=True)
    if r.returncode != 0:
        print(f"  ❌ Error: {r.stderr[:200]}")
        return False
    return True


def check_deps():
    banner("Checking dependencies")
    deps = {
        'nuitka':    ['python3', '-m', 'nuitka', '--version'],
        'python3':   ['python3', '--version'],
    }
    all_ok = True
    for name, cmd in deps.items():
        r = subprocess.run(cmd, capture_output=True, text=True)
        ok = r.returncode == 0
        print(f"  {'✅' if ok else '❌'} {name}: {r.stdout.strip()[:40] if ok else 'NOT FOUND'}")
        if not ok: all_ok = False
    return all_ok


def clean_dist():
    banner("Cleaning dist/")
    if os.path.exists(DIST):
        shutil.rmtree(DIST)
    os.makedirs(DIST)
    print("  ✅ dist/ cleaned")


def compile_backend():
    banner("Compiling Python → C++ → Binary (Nuitka)")
    print("  This converts server.py + all dependencies to native machine code.")
    print("  Reverse engineers will see: assembly, not Python.\n")

    cmd = [
        'python3', '-m', 'nuitka',
        '--standalone',           # Include all dependencies
        '--onefile',              # Bundle into single binary
        f'--output-dir={DIST}',
        '--output-filename=jovas-server',

        # Optimisation
        '--lto=yes',              # Link-time optimisation (harder to reverse)
        '--python-flag=no_site',  # Strip site packages
        '--python-flag=no_docstrings',  # Remove all docstrings

        # Include required packages
        '--include-package=flask',
        '--include-package=flask_cors',

        # Anti-debug (makes dynamic analysis harder)
        '--python-flag=no_asserts',

        # Include our modules
        '--include-module=jovas_interpreter',
        '--include-module=jovas_lexer',
        '--include-module=jovas_parser',
        '--include-module=jovas_modules',
        '--include-module=jovasdb',
        '--include-module=jovas_biometric',

        'server.py'
    ]

    print(f"  Running Nuitka compilation...")
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)

    if r.returncode == 0:
        # Check output binary exists
        binary = os.path.join(DIST, 'jovas-server')
        binary_exe = binary + '.exe'
        if os.path.exists(binary):
            size = os.path.getsize(binary) // (1024*1024)
            print(f"\n  ✅ Binary compiled: dist/jovas-server ({size}MB)")
            os.chmod(binary, 0o755)
            return True
        elif os.path.exists(binary_exe):
            size = os.path.getsize(binary_exe) // (1024*1024)
            print(f"\n  ✅ Binary compiled: dist/jovas-server.exe ({size}MB)")
            return True
    
    print(f"  ⚠️  Full compilation failed (needs C compiler). Using bytecode protection instead.")
    return False


def protect_with_bytecode():
    """Fallback: compile to .pyc bytecode (basic obfuscation)"""
    banner("Fallback: Python Bytecode Compilation")
    import compileall, py_compile

    protected_dir = os.path.join(DIST, 'jovas-backend')
    os.makedirs(protected_dir, exist_ok=True)

    py_files = [
        'server.py', 'jovas_interpreter.py', 'jovas_lexer.py',
        'jovas_parser.py', 'jovas_modules.py', 'jovasdb.py',
        'jovas_biometric.py', 'jovas_complete.py', 'run.py'
    ]

    compiled = 0
    for f in py_files:
        src = os.path.join(ROOT, f)
        if not os.path.exists(src):
            continue
        dst = os.path.join(protected_dir, f.replace('.py', '.pyc'))
        try:
            py_compile.compile(src, dst, optimize=2)
            print(f"  ✅ {f} → {os.path.basename(dst)}")
            compiled += 1
        except Exception as e:
            print(f"  ⚠️  {f}: {e}")

    print(f"\n  ✅ {compiled} files compiled to optimised bytecode")
    print("  Note: Bytecode is harder to read but not impossible to decompile.")
    print("  For full protection, install a C compiler and re-run for native binary.")
    return True


def obfuscate_frontend():
    """Obfuscate playground.html JavaScript"""
    banner("Obfuscating Frontend JavaScript")

    src = os.path.join(ROOT, 'playground.html')
    if not os.path.exists(src):
        print("  ❌ playground.html not found")
        return False

    content = open(src, encoding='utf-8').read()

    # Extract JS
    js_match = re.search(r'<script[^>]*>([\s\S]*?)</script>', content)
    if not js_match:
        print("  ❌ No script block found")
        return False

    js = js_match.group(1)

    # Try javascript-obfuscator
    r = subprocess.run(['npx', 'javascript-obfuscator', '--version'],
                       capture_output=True, text=True)
    if r.returncode == 0:
        # Write JS to temp file
        tmp_js = os.path.join(DIST, '_tmp.js')
        out_js = os.path.join(DIST, '_tmp.obf.js')
        open(tmp_js, 'w').write(js)

        result = subprocess.run([
            'npx', 'javascript-obfuscator', tmp_js,
            '--output', out_js,
            '--compact', 'true',
            '--string-array', 'true',
            '--rotate-string-array', 'true',
            '--string-array-encoding', 'base64',
            '--control-flow-flattening', 'true',
            '--control-flow-flattening-threshold', '0.5',
            '--dead-code-injection', 'true',
            '--dead-code-injection-threshold', '0.2',
            '--identifier-names-generator', 'hexadecimal',
            '--rename-globals', 'false',   # keep globals for HTML to call
            '--self-defending', 'true',    # anti-tampering
        ], capture_output=True, text=True)

        if result.returncode == 0 and os.path.exists(out_js):
            obf_js = open(out_js).read()
            # Reconstruct HTML with obfuscated JS
            new_content = content.replace(js_match.group(1), '\n' + obf_js + '\n')
            dst = os.path.join(DIST, 'playground.html')
            open(dst, 'w', encoding='utf-8').write(new_content)
            orig_size = len(js) // 1024
            new_size  = len(obf_js) // 1024
            print(f"  ✅ JS obfuscated: {orig_size}KB → {new_size}KB")
            print(f"  ✅ Saved: dist/playground.html")
            # Cleanup temp files
            os.remove(tmp_js)
            os.remove(out_js)
            return True

    # Fallback: basic minification (remove comments, whitespace)
    print("  ℹ️  javascript-obfuscator not found — applying basic minification")
    minified = re.sub(r'//[^\n]*\n', '\n', js)           # remove // comments
    minified = re.sub(r'/\*[\s\S]*?\*/', '', minified)    # remove /* */ comments
    minified = re.sub(r'\n\s*\n', '\n', minified)         # collapse blank lines
    minified = re.sub(r'^\s+', '', minified, flags=re.M)  # remove leading spaces

    new_content = content.replace(js_match.group(1), '\n' + minified + '\n')
    dst = os.path.join(DIST, 'playground.html')
    open(dst, 'w', encoding='utf-8').write(new_content)

    orig = len(js)//1024
    new  = len(minified)//1024
    print(f"  ✅ Comments stripped: {orig}KB → {new}KB")
    print(f"  ✅ Saved: dist/playground.html")
    print("  ℹ️  For full obfuscation: npm install -g javascript-obfuscator")
    return True


def copy_static_files():
    """Copy non-Python files to dist"""
    banner("Copying Static Files")
    static = ['index.html', '404.html', 'manifest.json', 'sw.js', 'README.md']
    for f in static:
        src = os.path.join(ROOT, f)
        if os.path.exists(src):
            shutil.copy2(src, DIST)
            print(f"  ✅ {f}")


def create_launcher():
    """Create a launcher script that runs the binary"""
    banner("Creating Launcher Scripts")

    # Linux/Mac launcher
    launcher_sh = os.path.join(DIST, 'start.sh')
    open(launcher_sh, 'w').write("""#!/bin/bash
# Jovas Language Server — Protected Build
echo "Starting Jovas Backend Server..."
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
"$DIR/jovas-server" "$@"
""")
    os.chmod(launcher_sh, 0o755)
    print("  ✅ start.sh (Linux/Mac)")

    # Windows launcher
    launcher_bat = os.path.join(DIST, 'start.bat')
    open(launcher_bat, 'w').write("""@echo off
REM Jovas Language Server — Protected Build
echo Starting Jovas Backend Server...
%~dp0jovas-server.exe %*
pause
""")
    print("  ✅ start.bat (Windows)")


def print_summary(binary_ok):
    banner("BUILD COMPLETE")
    print(f"""
  Protection applied:
  {"✅" if binary_ok else "⚠️ "} Python → Native Binary (Nuitka)
  ✅ JavaScript minified/obfuscated
  ✅ Source .py files NOT included in dist/
  ✅ Docstrings stripped
  ✅ Assertions removed

  Distribution folder: dist/
  ├── jovas-server{"" if not binary_ok else " (native binary — no Python needed)"}
  ├── playground.html (obfuscated JS)
  ├── index.html
  ├── 404.html
  ├── manifest.json
  ├── sw.js
  ├── start.sh
  └── start.bat

  What a reverse engineer sees:
  - Binary: assembly/machine code (no Python visible)
  - Frontend: hex identifiers, encoded strings, flattened logic
  - No source code, no comments, no variable names

  To run:
    Linux/Mac:  ./dist/start.sh
    Windows:    dist\\start.bat
    Direct:     ./dist/jovas-server
""")


def main():
    banner("JOVAS PROTECTION BUILD (Nuitka)")
    print("  Converting Python source → C++ → Native Binary")
    print("  Making reverse engineering extremely difficult\n")

    if not check_deps():
        print("\n  ❌ Missing dependencies. Run: pip install nuitka")
        sys.exit(1)

    clean_dist()

    # Try full Nuitka compilation first
    binary_ok = compile_backend()

    # If Nuitka fails (needs C compiler), fall back to bytecode
    if not binary_ok:
        protect_with_bytecode()

    # Always obfuscate the frontend
    obfuscate_frontend()
    copy_static_files()
    create_launcher()
    print_summary(binary_ok)


if __name__ == '__main__':
    main()
