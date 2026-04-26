#!/usr/bin/env python3
# ═══════════════════════════════════════════════════════════════
#   JOVAS BACKEND API SERVER
#   Flask + WebSocket server bridging the playground to the
#   Python interpreter, JovasDB, and all backend modules.
#
#   Endpoints:
#     POST /api/run          — execute Jovas code, return output
#     POST /api/db/query     — run a JovasDB SQL query
#     POST /api/ai/ask       — proxy to Claude API
#     GET  /api/health       — server health check
#     GET  /api/version      — Jovas version info
#     WS   /ws               — real-time code execution stream
#
#   Usage:
#     pip install flask flask-cors
#     python server.py
#     Server runs on http://localhost:5000
# ═══════════════════════════════════════════════════════════════

import sys
import os
import json
import time
import traceback
import io
import threading
from contextlib import redirect_stdout

from flask import Flask, request, jsonify, Response
from flask_cors import CORS

# ── Add parent dir to path so we can import Jovas modules ──────
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ── Lazy-import Jovas interpreter ──────────────────────────────
_interp_available = False
try:
    from jovas_interpreter import Interpreter
    from jovasdb import JovasDB
    _interp_available = True
except ImportError as e:
    print(f"[Warning] Could not import Jovas interpreter: {e}")
    print("[Warning] Running in JS-only mode (playground uses its own interpreter)")


# ══════════════════════════════════════════════════════════════
#  APP SETUP
# ══════════════════════════════════════════════════════════════
app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}})

# In-memory databases per session
_dbs = {}
_db_lock = threading.Lock()

JOVAS_VERSION = "1.0.0"
MAX_CODE_LENGTH = 50_000
EXECUTION_TIMEOUT = 10  # seconds


# ══════════════════════════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════════════════════════
def get_or_create_db(session_id: str) -> "JovasDB":
    with _db_lock:
        if session_id not in _dbs:
            _dbs[session_id] = JovasDB(f":memory:{session_id}")
        return _dbs[session_id]


def run_jovas_code(code: str, session_id: str = "default") -> dict:
    """Execute Jovas code using the Python interpreter. Returns structured output."""
    if not _interp_available:
        return {
            "success": False,
            "output": [],
            "error": "Python interpreter not available — playground uses JS interpreter",
            "exec_ms": 0
        }

    if len(code) > MAX_CODE_LENGTH:
        return {"success": False, "output": [], "error": "Code too large (max 50KB)", "exec_ms": 0}

    output_lines = []
    start = time.time()

    # Custom print that captures output
    def jovas_print(*args):
        line = " ".join(str(a) for a in args)
        output_lines.append({"type": "info", "text": line})

    try:
        interp = Interpreter()
        # Override print in interpreter scope
        interp.global_env.set("print", jovas_print)
        # Inject DB for this session
        if _interp_available and JovasDB:
            db = get_or_create_db(session_id)
            interp.global_env.set("__db__", db)

        # Run with timeout
        result = [None]
        error  = [None]

        def target():
            try:
                result[0] = interp.run(code)
            except Exception as e:
                error[0] = str(e)

        t = threading.Thread(target=target, daemon=True)
        t.start()
        t.join(timeout=EXECUTION_TIMEOUT)

        exec_ms = int((time.time() - start) * 1000)

        if t.is_alive():
            return {
                "success": False,
                "output": output_lines,
                "error": f"Execution timeout ({EXECUTION_TIMEOUT}s)",
                "exec_ms": exec_ms
            }

        if error[0]:
            output_lines.append({"type": "err", "text": f"[Error] {error[0]}"})
            return {"success": False, "output": output_lines, "error": error[0], "exec_ms": exec_ms}

        return {"success": True, "output": output_lines, "error": None, "exec_ms": exec_ms}

    except Exception as e:
        exec_ms = int((time.time() - start) * 1000)
        return {
            "success": False,
            "output": output_lines,
            "error": traceback.format_exc(),
            "exec_ms": exec_ms
        }


# ══════════════════════════════════════════════════════════════
#  API ROUTES
# ══════════════════════════════════════════════════════════════

@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({
        "status": "ok",
        "version": JOVAS_VERSION,
        "interpreter": _interp_available,
        "timestamp": int(time.time())
    })


@app.route("/api/version", methods=["GET"])
def version():
    return jsonify({
        "version": JOVAS_VERSION,
        "engine": "Python" if _interp_available else "JS (browser-side)",
        "modules": [
            "database", "security", "email", "ai", "http", "server",
            "realtime", "deploy", "biometric", "auth", "log", "math",
            "json", "crypto", "time", "env", "config", "file",
            "fmt", "lint", "debug", "network", "game", "story"
        ],
        "features": [
            "syntax_highlighting", "autocomplete", "real_ai",
            "jovasdb", "biometric", "share_url", "themes"
        ]
    })


@app.route("/api/run", methods=["POST"])
def run_code():
    """
    Execute Jovas code server-side.
    Body: { "code": "...", "session": "optional-session-id" }
    """
    try:
        body       = request.get_json(force=True) or {}
        code       = body.get("code", "").strip()
        session_id = body.get("session", "default")

        if not code:
            return jsonify({"success": False, "error": "No code provided", "output": []}), 400

        result = run_jovas_code(code, session_id)
        return jsonify(result)

    except Exception as e:
        return jsonify({"success": False, "error": str(e), "output": []}), 500


@app.route("/api/db/query", methods=["POST"])
def db_query():
    """
    Run a raw SQL-style query against JovasDB.
    Body: { "sql": "SELECT * FROM users", "session": "..." }
    """
    if not _interp_available:
        return jsonify({"success": False, "error": "JovasDB not available"}), 503

    try:
        body       = request.get_json(force=True) or {}
        sql        = body.get("sql", "").strip()
        session_id = body.get("session", "default")

        if not sql:
            return jsonify({"success": False, "error": "No SQL provided"}), 400

        db = get_or_create_db(session_id)
        result = db.query(sql)
        return jsonify({"success": True, "result": result})

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/db/tables", methods=["GET"])
def db_tables():
    """List all tables in the session database."""
    if not _interp_available:
        return jsonify({"success": False, "error": "JovasDB not available"}), 503

    session_id = request.args.get("session", "default")
    try:
        db = get_or_create_db(session_id)
        tables = db.list_tables() if hasattr(db, "list_tables") else []
        return jsonify({"success": True, "tables": tables})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/share", methods=["POST"])
def save_share():
    """
    Save shareable code snippet.
    Body: { "code": "...", "title": "optional" }
    Returns: { "id": "abc123", "url": "/share/abc123" }
    """
    import hashlib
    body  = request.get_json(force=True) or {}
    code  = body.get("code", "")
    title = body.get("title", "Untitled")

    if not code:
        return jsonify({"success": False, "error": "No code"}), 400

    # Simple hash-based ID (stateless — URL carries the code)
    share_id = hashlib.sha256(code.encode()).hexdigest()[:12]
    import base64
    encoded  = base64.b64encode(code.encode()).decode()

    return jsonify({
        "success":  True,
        "id":       share_id,
        "title":    title,
        "encoded":  encoded,
        "url":      f"/playground.html?code={encoded}"
    })


@app.route("/api/lint", methods=["POST"])
def lint_code():
    """
    Lint Jovas code — check syntax without executing.
    Body: { "code": "..." }
    """
    body = request.get_json(force=True) or {}
    code = body.get("code", "").strip()

    if not code:
        return jsonify({"success": True, "errors": [], "warnings": []}), 200

    errors   = []
    warnings = []

    # Basic static checks
    lines = code.split("\n")
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        # Check for common mistakes
        if stripped.startswith("def ") or stripped.startswith("function "):
            errors.append({"line": i, "msg": "Use 'fn' instead of 'def'/'function'", "type": "error"})
        if stripped.endswith(";"):
            warnings.append({"line": i, "msg": "Jovas doesn't need semicolons", "type": "warning"})
        if "==" in stripped and stripped.startswith("if ") and "===" in stripped:
            warnings.append({"line": i, "msg": "Use '==' not '==='; Jovas uses Python-style equality", "type": "warning"})
        if stripped.startswith("var "):
            errors.append({"line": i, "msg": "Use 'let' or 'const' instead of 'var'", "type": "error"})

    # Try to parse if interpreter available
    if _interp_available:
        try:
            from jovas_lexer import Lexer
            from jovas_parser import Parser
            lexer  = Lexer(code)
            tokens = lexer.tokenize()
            parser = Parser(tokens)
            parser.parse()
        except Exception as e:
            errors.append({"line": 0, "msg": f"Parse error: {str(e)}", "type": "error"})

    return jsonify({
        "success":  len(errors) == 0,
        "errors":   errors,
        "warnings": warnings,
        "lines":    len(lines)
    })


@app.route("/api/format", methods=["POST"])
def format_code():
    """
    Auto-format Jovas code.
    Body: { "code": "..." }
    """
    body = request.get_json(force=True) or {}
    code = body.get("code", "")

    if not code:
        return jsonify({"success": False, "error": "No code"}), 400

    formatted_lines = []
    for line in code.split("\n"):
        # Normalize indentation to 4 spaces
        stripped = line.lstrip()
        indent   = len(line) - len(stripped)
        # Round to nearest 4
        indent   = (indent // 4) * 4
        formatted_lines.append(" " * indent + stripped)

    return jsonify({
        "success":   True,
        "formatted": "\n".join(formatted_lines)
    })


@app.route("/api/completions", methods=["POST"])
def get_completions():
    """
    Get autocomplete suggestions for a partial expression.
    Body: { "prefix": "database.", "context": "full code so far" }
    """
    body   = request.get_json(force=True) or {}
    prefix = body.get("prefix", "")

    MODULE_METHODS = {
        "database": ["connect", "createTable", "insert", "select", "update", "delete",
                     "findOne", "count", "sql", "begin", "transaction"],
        "security": ["hash", "verify", "jwtSign", "jwtVerify", "validate",
                     "encrypt", "decrypt", "random", "sanitize"],
        "ai":       ["ask", "generate", "write", "translate", "summarize",
                     "sentiment", "classify", "edit", "code", "explain", "setKey"],
        "email":    ["configure", "send", "template", "otp", "queue"],
        "http":     ["get", "post", "put", "delete", "fetch"],
        "server":   ["create", "get", "post", "put", "listen", "use"],
        "realtime": ["sync", "broadcast", "join", "leave", "presence", "on"],
        "deploy":   ["to", "status", "rollback", "logs"],
        "auth":     ["login", "logout", "verify", "refresh", "register"],
        "log":      ["info", "warn", "error", "debug"],
        "math":     ["abs", "sqrt", "floor", "ceil", "round", "random", "pi", "sin", "cos"],
        "json":     ["parse", "stringify", "validate"],
        "time":     ["now", "format", "parse", "sleep", "diff"],
        "crypto":   ["hash", "hmac", "uuid", "random", "base64encode", "base64decode"],
        "network":  ["get", "post", "scan", "ping", "dns", "whois", "headers", "payload"],
        "game":     ["canvas", "sprite", "scene", "move", "physics", "collide",
                     "score", "loop", "render", "audio", "load", "map", "npc", "export"],
        "story":    ["create", "chapter", "scene", "character", "dialogue",
                     "write", "translate", "wordCount", "export", "outline"],
        "file":     ["read", "write", "append", "delete", "exists", "list"],
        "biometric":["init", "enroll", "verify", "mfa", "isEnrolled"],
    }

    completions = []
    if "." in prefix:
        module, partial = prefix.rsplit(".", 1)
        module = module.strip()
        methods = MODULE_METHODS.get(module, [])
        completions = [
            {"label": m, "insert": f"{module}.{m}()", "type": "method"}
            for m in methods
            if m.startswith(partial)
        ]
    else:
        # Top-level completions
        keywords = ["fn", "let", "const", "class", "if", "else", "for", "while",
                    "return", "match", "case", "try", "catch", "print", "import"]
        modules  = list(MODULE_METHODS.keys())
        for kw in keywords:
            if kw.startswith(prefix):
                completions.append({"label": kw, "type": "keyword", "insert": kw})
        for mod in modules:
            if mod.startswith(prefix):
                completions.append({"label": mod, "type": "module", "insert": mod})

    return jsonify({"success": True, "completions": completions})


@app.route("/api/examples", methods=["GET"])
def list_examples():
    """Return list of all built-in examples."""
    examples = [
        {"key": "hello",      "name": "Hello World",     "icon": "👋", "category": "basics"},
        {"key": "functions",  "name": "Functions",        "icon": "⚙", "category": "basics"},
        {"key": "classes",    "name": "Classes",          "icon": "🏛", "category": "basics"},
        {"key": "database",   "name": "JovasDB",          "icon": "🗄", "category": "data"},
        {"key": "auth",       "name": "Auth & JWT",       "icon": "🔑", "category": "security"},
        {"key": "security",   "name": "Security Suite",   "icon": "🔒", "category": "security"},
        {"key": "ai",         "name": "AI Module",        "icon": "🤖", "category": "ai"},
        {"key": "email",      "name": "Email",            "icon": "📧", "category": "comms"},
        {"key": "biometric",  "name": "Biometric Auth",   "icon": "🔐", "category": "security"},
        {"key": "realtime",   "name": "Realtime/WS",      "icon": "📡", "category": "comms"},
        {"key": "deploy",     "name": "Deploy",           "icon": "🚀", "category": "infra"},
        {"key": "server",     "name": "HTTP Server",      "icon": "⚡", "category": "backend"},
        {"key": "pipeline",   "name": "Pipeline |>",      "icon": "🔀", "category": "advanced"},
        {"key": "match",      "name": "Match/Case",       "icon": "✸",  "category": "advanced"},
        {"key": "fullapp",    "name": "Full App",         "icon": "✨", "category": "advanced"},
        {"key": "network",    "name": "Network/Hack",     "icon": "🔓", "category": "hacking"},
        {"key": "game",       "name": "Game Dev",         "icon": "🎮", "category": "creative"},
        {"key": "story",      "name": "Novel Writing",    "icon": "📖", "category": "creative"},
    ]
    return jsonify({"success": True, "examples": examples, "total": len(examples)})


# ── SSE: Stream execution output ─────────────────────────────
@app.route("/api/run/stream", methods=["POST"])
def run_stream():
    """
    Stream Jovas code execution output line-by-line via SSE.
    Body: { "code": "...", "session": "..." }
    """
    body       = request.get_json(force=True) or {}
    code       = body.get("code", "")
    session_id = body.get("session", "default")

    def generate():
        result = run_jovas_code(code, session_id)
        for line in result.get("output", []):
            yield f"data: {json.dumps(line)}\n\n"
            time.sleep(0.01)  # small delay for streaming feel
        # Send done event
        done = {"type": "done", "success": result["success"],
                "exec_ms": result["exec_ms"]}
        yield f"data: {json.dumps(done)}\n\n"

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control":               "no-cache",
            "X-Accel-Buffering":           "no",
            "Access-Control-Allow-Origin": "*",
        }
    )


# ══════════════════════════════════════════════════════════════
#  STARTUP
# ══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    host = os.environ.get("HOST", "0.0.0.0")

    print(f"""
╔══════════════════════════════════════════════╗
║        JOVAS BACKEND API SERVER              ║
║        Version {JOVAS_VERSION}                         ║
╠══════════════════════════════════════════════╣
║  http://{host}:{port}                       ║
║                                              ║
║  Endpoints:                                  ║
║    POST /api/run          — execute code     ║
║    POST /api/db/query     — JovasDB query    ║
║    POST /api/lint         — lint code        ║
║    POST /api/format       — format code      ║
║    POST /api/completions  — autocomplete     ║
║    POST /api/share        — share snippet    ║
║    GET  /api/health       — health check     ║
║    GET  /api/version      — version info     ║
║    GET  /api/examples     — list examples    ║
║                                              ║
║  Interpreter: {"Python ✓" if _interp_available else "JS-only (install jovas_*.py)"}             ║
╚══════════════════════════════════════════════╝
    """)

    app.run(host=host, port=port, debug=False, threaded=True)
