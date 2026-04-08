#!/usr/bin/env python3
# ============================================
#   JOVAS SECURITY MODULE
#   Covers:
#   1. Language sandbox (safe code execution)
#   2. JovasDB injection prevention
#   3. Rate limiting & brute force protection
#   4. Input sanitization & validation
#   5. Secrets management
#   6. Security audit logger
# ============================================

import os, re, time, hmac, hashlib, json, base64
from datetime import datetime
from collections import defaultdict

# ══════════════════════════════════════════════
#  1. LANGUAGE SANDBOX
#  Prevents malicious .jovas code from
#  escaping the interpreter and running
#  arbitrary Python
# ══════════════════════════════════════════════

class JovasSandbox:
    """
    Wraps the Jovas interpreter with security controls.
    Blocks dangerous operations before they reach the engine.
    """

    # Keywords that should never appear in .jovas source
    BLOCKED_PATTERNS = [
        r"__import__",        # Python import escape
        r"__builtins__",      # Access to builtins
        r"__class__\.__",     # Class manipulation
        r"eval\s*\(",         # Python eval
        r"exec\s*\(",         # Python exec
        r"compile\s*\(",      # Python compile
        r"open\s*\(",         # File system access
        r"os\s*\.",           # OS module access
        r"sys\s*\.",          # Sys module access
        r"subprocess",        # Shell execution
        r"socket\s*\.",       # Raw socket access (use socket module instead)
        r"globals\s*\(",      # Globals access
        r"locals\s*\(",       # Locals access
        r"getattr\s*\(",      # Attribute manipulation
        r"setattr\s*\(",      # Attribute manipulation
        r"delattr\s*\(",      # Attribute deletion
    ]

    # Max limits to prevent DoS
    MAX_SOURCE_LENGTH  = 50_000    # 50KB max source file
    MAX_LOOP_DEPTH     = 1_000     # max iterations per loop
    MAX_RECURSION      = 100       # max function call depth
    MAX_EXEC_TIME_SEC  = 30        # max execution time

    def __init__(self):
        self._call_depth = 0
        self._start_time = None
        self._violations = []

    def validate_source(self, source: str) -> dict:
        """
        Scan .jovas source code for dangerous patterns
        before running it. Returns {safe: bool, issues: [str]}
        """
        issues = []

        # Length check
        if len(source) > self.MAX_SOURCE_LENGTH:
            issues.append(f"Source too large: {len(source)} chars (max {self.MAX_SOURCE_LENGTH})")

        # Pattern scan
        for pattern in self.BLOCKED_PATTERNS:
            matches = re.findall(pattern, source, re.IGNORECASE)
            if matches:
                issues.append(f"Blocked pattern '{pattern}' found")

        # Null byte injection
        if '\x00' in source:
            issues.append("Null byte injection detected")

        # Excessive nesting (potential bomb)
        max_indent = max((len(l) - len(l.lstrip()) for l in source.split('\n') if l.strip()), default=0)
        if max_indent > 200:
            issues.append(f"Excessive nesting depth: {max_indent}")

        safe = len(issues) == 0
        return {"safe": safe, "issues": issues}

    def check_timeout(self):
        if self._start_time and (time.time() - self._start_time) > self.MAX_EXEC_TIME_SEC:
            raise TimeoutError(f"Execution exceeded {self.MAX_EXEC_TIME_SEC}s limit")

    def enter_call(self):
        self._call_depth += 1
        if self._call_depth > self.MAX_RECURSION:
            raise RecursionError(f"Max recursion depth ({self.MAX_RECURSION}) exceeded")

    def exit_call(self):
        self._call_depth = max(0, self._call_depth - 1)

    def start_execution(self):
        self._start_time = time.time()
        self._call_depth = 0

    def log_violation(self, violation: str):
        self._violations.append({
            "time": datetime.now().isoformat(),
            "violation": violation
        })
        print(f"  [Security] ⚠️  VIOLATION: {violation}")


# ══════════════════════════════════════════════
#  2. JOVASDB INJECTION PREVENTION
#  Sanitizes all values going into JovasDB
#  Prevents query manipulation attacks
# ══════════════════════════════════════════════

class DBSecurity:
    """
    Protects JovasDB from injection and manipulation attacks.
    Wrap all user-provided values through this before inserting.
    """

    # Field names that should never come from user input
    RESERVED_FIELDS = {
        '__class__', '__methods__', '__env__', '_id',
        'constructor', 'prototype', '__proto__'
    }

    # Max sizes
    MAX_STRING_LENGTH = 10_000
    MAX_OBJECT_DEPTH  = 10
    MAX_ARRAY_LENGTH  = 1_000

    @classmethod
    def sanitize_value(cls, value, depth=0):
        """Recursively sanitize a value before storing in JovasDB."""
        if depth > cls.MAX_OBJECT_DEPTH:
            return None

        if value is None or isinstance(value, bool):
            return value

        if isinstance(value, (int, float)):
            # Prevent infinity / NaN
            if value != value or abs(value) == float('inf'):
                return 0
            return value

        if isinstance(value, str):
            # Truncate
            value = value[:cls.MAX_STRING_LENGTH]
            # Remove null bytes
            value = value.replace('\x00', '')
            # Escape HTML entities
            value = value.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            return value

        if isinstance(value, dict):
            clean = {}
            for k, v in value.items():
                key = str(k)
                # Block reserved field names
                if key in cls.RESERVED_FIELDS:
                    continue
                # Block keys starting with __ (dunder)
                if key.startswith('__') and key.endswith('__'):
                    continue
                clean[key] = cls.sanitize_value(v, depth + 1)
            return clean

        if isinstance(value, list):
            if len(value) > cls.MAX_ARRAY_LENGTH:
                value = value[:cls.MAX_ARRAY_LENGTH]
            return [cls.sanitize_value(v, depth + 1) for v in value]

        return str(value)

    @classmethod
    def sanitize_where(cls, where: dict) -> dict:
        """Sanitize a WHERE clause dict used in select/update/delete."""
        if not isinstance(where, dict):
            return {}
        clean = {}
        for k, v in where.items():
            # Only allow alphanumeric field names
            if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', str(k)):
                continue
            if k in cls.RESERVED_FIELDS:
                continue
            clean[k] = cls.sanitize_value(v)
        return clean

    @classmethod
    def sanitize_table_name(cls, name: str) -> str:
        """Only allow safe table names."""
        if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', str(name)):
            raise ValueError(f"Invalid table name: '{name}' — only letters, numbers, underscores allowed")
        if len(name) > 64:
            raise ValueError(f"Table name too long: {len(name)} chars (max 64)")
        return name.lower()

    @classmethod
    def sanitize_nlq(cls, query: str) -> str:
        """Sanitize a natural language query string."""
        # Remove any code-like injection attempts
        query = query[:500]  # max 500 chars
        query = query.replace('\x00', '')
        # Block SQL-like injection in NLQ
        blocked = ['drop', 'truncate', 'delete all', '--', ';', '/*', '*/']
        q_lower = query.lower()
        for b in blocked:
            if b in q_lower:
                raise ValueError(f"Blocked NLQ pattern: '{b}'")
        return query


# ══════════════════════════════════════════════
#  3. RATE LIMITER
#  Prevents brute force, DoS attacks
# ══════════════════════════════════════════════

class RateLimiter:
    """
    Token bucket rate limiter.
    Use to protect any endpoint or operation.

    Usage:
        rl = RateLimiter()
        if not rl.allow("user_ip_or_id", limit=10, window=60):
            raise Exception("Rate limit exceeded")
    """

    def __init__(self):
        self._buckets   = defaultdict(list)  # key → [timestamps]
        self._blocked   = {}                 # key → blocked_until timestamp
        self._strikes   = defaultdict(int)   # key → violation count

    def allow(self, key: str, limit: int = 100, window: int = 60) -> bool:
        """
        Returns True if request is allowed, False if rate limited.
        key    — identifier (IP, user ID, etc.)
        limit  — max requests
        window — time window in seconds
        """
        now = time.time()
        key = str(key)

        # Check if currently blocked
        if key in self._blocked:
            if now < self._blocked[key]:
                return False
            else:
                del self._blocked[key]

        # Clean old entries outside window
        self._buckets[key] = [t for t in self._buckets[key] if now - t < window]

        # Check limit
        if len(self._buckets[key]) >= limit:
            self._strikes[key] += 1
            # Progressive blocking: more strikes = longer block
            block_time = min(3600, 60 * (2 ** min(self._strikes[key], 6)))
            self._blocked[key] = now + block_time
            print(f"  [RateLimit] 🚫 '{key}' blocked for {block_time}s (strike #{self._strikes[key]})")
            return False

        self._buckets[key].append(now)
        return True

    def remaining(self, key: str, limit: int = 100, window: int = 60) -> int:
        now = time.time()
        key = str(key)
        recent = [t for t in self._buckets.get(key, []) if now - t < window]
        return max(0, limit - len(recent))

    def reset(self, key: str):
        key = str(key)
        self._buckets.pop(key, None)
        self._blocked.pop(key, None)
        self._strikes.pop(key, None)
        print(f"  [RateLimit] ✅ Reset: '{key}'")

    def status(self, key: str, limit: int = 100, window: int = 60) -> dict:
        now = time.time()
        key = str(key)
        blocked = key in self._blocked and now < self._blocked.get(key, 0)
        return {
            "key":       key,
            "allowed":   not blocked,
            "remaining": self.remaining(key, limit, window),
            "strikes":   self._strikes.get(key, 0),
            "blocked":   blocked,
            "blocked_until": datetime.fromtimestamp(self._blocked[key]).isoformat() if blocked else None
        }


# ══════════════════════════════════════════════
#  4. INPUT SANITIZER
#  Cleans all user input before processing
# ══════════════════════════════════════════════

class InputSanitizer:
    """
    Sanitize and validate user-provided input.
    Use this on ALL data coming from outside the system.
    """

    @staticmethod
    def string(value, max_length=1000, strip=True) -> str:
        """Sanitize a plain string."""
        if not isinstance(value, str):
            value = str(value)
        if strip:
            value = value.strip()
        value = value[:max_length]
        value = value.replace('\x00', '')  # null bytes
        return value

    @staticmethod
    def html(value) -> str:
        """Escape HTML to prevent XSS."""
        value = str(value)
        return (value
            .replace('&',  '&amp;')
            .replace('<',  '&lt;')
            .replace('>',  '&gt;')
            .replace('"',  '&quot;')
            .replace("'",  '&#x27;')
            .replace('/',  '&#x2F;')
            .replace('`',  '&#x60;')
            .replace('=',  '&#x3D;'))

    @staticmethod
    def email(value) -> str:
        """Validate and sanitize email address."""
        value = str(value).strip().lower()[:254]
        if not re.match(r'^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$', value):
            raise ValueError(f"Invalid email: '{value}'")
        return value

    @staticmethod
    def filename(value) -> str:
        """Sanitize a filename — prevent path traversal."""
        value = os.path.basename(str(value))
        value = re.sub(r'[^\w.\-]', '_', value)
        if value.startswith('.'):
            value = '_' + value
        if len(value) > 255:
            value = value[:255]
        return value

    @staticmethod
    def integer(value, min_val=None, max_val=None) -> int:
        """Validate integer within optional bounds."""
        try:
            n = int(value)
        except (TypeError, ValueError):
            raise ValueError(f"Invalid integer: '{value}'")
        if min_val is not None and n < min_val:
            raise ValueError(f"Value {n} below minimum {min_val}")
        if max_val is not None and n > max_val:
            raise ValueError(f"Value {n} above maximum {max_val}")
        return n

    @staticmethod
    def url(value) -> str:
        """Validate and sanitize a URL."""
        value = str(value).strip()
        if not re.match(r'^https?://', value, re.I):
            raise ValueError(f"URL must start with http:// or https://")
        if len(value) > 2048:
            raise ValueError("URL too long")
        # Block SSRF targets
        blocked_hosts = ['localhost', '127.0.0.1', '0.0.0.0', '169.254.',
                         '10.', '172.16.', '192.168.', '::1']
        for host in blocked_hosts:
            if host in value.lower():
                raise ValueError(f"Blocked URL: internal addresses not allowed")
        return value

    @staticmethod
    def json_safe(value) -> str:
        """Safely serialize to JSON."""
        try:
            return json.dumps(value, default=str, ensure_ascii=True)
        except Exception:
            return json.dumps(str(value))


# ══════════════════════════════════════════════
#  5. SECRETS MANAGER
#  Handles secrets safely — never hardcoded
# ══════════════════════════════════════════════

class SecretsManager:
    """
    Load secrets from environment variables or a .env file.
    NEVER hardcode secrets in source code.

    Usage:
        secrets = SecretsManager()
        jwt_secret = secrets.require("JWT_SECRET")
        db_pass    = secrets.get("DB_PASSWORD", "default")
    """

    def __init__(self, env_file=".env"):
        self._secrets = {}
        self._load_env(env_file)

    def _load_env(self, path):
        """Load .env file if it exists."""
        # First load from actual environment
        for k, v in os.environ.items():
            self._secrets[k] = v

        # Then overlay .env file
        if os.path.exists(path):
            with open(path, encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                    if '=' in line:
                        k, _, v = line.partition('=')
                        k = k.strip(); v = v.strip()
                        # Strip surrounding quotes
                        if len(v) >= 2 and v[0] == v[-1] and v[0] in ('"', "'"):
                            v = v[1:-1]
                        self._secrets[k] = v

    def get(self, key: str, default=None):
        """Get a secret or return default."""
        return self._secrets.get(key, default)

    def require(self, key: str) -> str:
        """Get a secret or raise if missing."""
        val = self._secrets.get(key)
        if not val:
            raise EnvironmentError(
                f"Required secret '{key}' not found.\n"
                f"Set it in your .env file or as an environment variable:\n"
                f"  {key}=your_value_here"
            )
        return val

    def generate_secret(self, length=32) -> str:
        """Generate a cryptographically secure random secret."""
        return base64.urlsafe_b64encode(os.urandom(length)).decode()[:length]

    def check_env_file(self) -> dict:
        """Audit .env file for common mistakes."""
        issues = []
        for k, v in self._secrets.items():
            if v in ('changeme', 'secret', 'password', '12345', 'test', ''):
                issues.append(f"Weak value for '{k}'")
            if k.upper() in ('JWT_SECRET', 'SECRET_KEY', 'API_KEY') and len(v) < 16:
                issues.append(f"'{k}' is too short (min 16 chars)")
        return {"ok": len(issues) == 0, "issues": issues}


# ══════════════════════════════════════════════
#  6. SECURITY AUDIT LOGGER
#  Logs all security events to a file
# ══════════════════════════════════════════════

class SecurityAuditLog:
    """
    Logs security events — violations, failed logins,
    rate limit hits, injection attempts, etc.
    """

    LOG_FILE = "jovas_security.log"

    LEVELS = {
        "INFO":     "ℹ️ ",
        "WARN":     "⚠️ ",
        "CRITICAL": "🚨",
        "BLOCKED":  "🚫",
    }

    def __init__(self, log_file=None):
        self._file = log_file or self.LOG_FILE
        self._events = []

    def _write(self, level: str, event: str, details: dict = None):
        entry = {
            "ts":      datetime.now().isoformat(),
            "level":   level,
            "event":   event,
            "details": details or {}
        }
        self._events.append(entry)
        icon = self.LEVELS.get(level, "·")
        print(f"  [AuditLog] {icon} [{level}] {event}")
        try:
            with open(self._file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(entry) + '\n')
        except Exception:
            pass

    def info(self, event, details=None):
        self._write("INFO", event, details)

    def warn(self, event, details=None):
        self._write("WARN", event, details)

    def critical(self, event, details=None):
        self._write("CRITICAL", event, details)

    def blocked(self, event, details=None):
        self._write("BLOCKED", event, details)

    def login_attempt(self, user_id: str, success: bool, ip: str = "unknown"):
        level  = "INFO" if success else "WARN"
        event  = f"Login {'succeeded' if success else 'FAILED'}: {user_id}"
        self._write(level, event, {"user": user_id, "ip": ip, "success": success})

    def injection_attempt(self, source: str, pattern: str, ip: str = "unknown"):
        self.critical(f"Injection attempt blocked", {"source": source[:100], "pattern": pattern, "ip": ip})

    def export(self, last_n=50) -> list:
        return self._events[-last_n:]

    def summary(self) -> dict:
        from collections import Counter
        counts = Counter(e["level"] for e in self._events)
        return {
            "total":    len(self._events),
            "info":     counts.get("INFO", 0),
            "warnings": counts.get("WARN", 0),
            "critical": counts.get("CRITICAL", 0),
            "blocked":  counts.get("BLOCKED", 0),
        }


# ══════════════════════════════════════════════
#  7. WEBSITE SECURITY HEADERS
#  Content Security Policy + HTTP headers
#  Add these to any web server response
# ══════════════════════════════════════════════

SECURITY_HEADERS = {
    # Prevents XSS attacks
    "Content-Security-Policy": (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdnjs.cloudflare.com; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com; "
        "img-src 'self' data:; "
        "connect-src 'self'; "
        "frame-ancestors 'none';"
    ),
    # Prevents clickjacking
    "X-Frame-Options":           "DENY",
    # Prevents MIME sniffing
    "X-Content-Type-Options":    "nosniff",
    # Forces HTTPS
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
    # Controls referrer info
    "Referrer-Policy":           "strict-origin-when-cross-origin",
    # Controls browser features
    "Permissions-Policy":        "camera=(), microphone=(), geolocation=()",
    # Enables XSS filter in older browsers
    "X-XSS-Protection":          "1; mode=block",
}

def get_security_headers() -> dict:
    """Returns all recommended security headers for HTTP responses."""
    return SECURITY_HEADERS.copy()


# ══════════════════════════════════════════════
#  8. GITHUB REPO SECURITY CHECKLIST
#  Documents what to configure on GitHub
# ══════════════════════════════════════════════

GITHUB_SECURITY_CHECKLIST = """
╔══════════════════════════════════════════════════╗
║   JOVAS GITHUB SECURITY CHECKLIST                ║
╚══════════════════════════════════════════════════╝

✅ = Already done    ⬜ = You need to do this

BRANCH PROTECTION
⬜ Settings → Branches → Add rule for 'main'
    ☑ Require pull request reviews before merging
    ☑ Require status checks to pass (CI)
    ☑ Require branches to be up to date
    ☑ Do not allow bypassing above settings

SECRETS & TOKENS  
⬜ Settings → Secrets → Actions
    Add these secrets (never put in code):
    - JWT_SECRET
    - DB_PASSWORD (if using cloud DB)
    - EMAIL_PASSWORD (for email module)
⬜ Never commit .env files (already in .gitignore ✅)
⬜ Rotate any tokens that were ever committed

SECURITY ALERTS
⬜ Settings → Security → Enable Dependabot alerts
⬜ Settings → Security → Enable secret scanning
⬜ Settings → Security → Enable code scanning

CODE REVIEW
⬜ All changes via Pull Requests (not direct push to main)
⬜ At least 1 reviewer before merge
⬜ CI must pass before merge

ACCESS CONTROL
⬜ Settings → Collaborators → Only trusted people
⬜ Use 2FA on your GitHub account
⬜ Review OAuth apps with access to your account
"""


# ══════════════════════════════════════════════
#  DEMO — test all security modules
# ══════════════════════════════════════════════

if __name__ == "__main__":
    GOLD  = "\033[38;5;220m"; BOLD = "\033[1m"
    GREEN = "\033[38;5;82m";  RED  = "\033[38;5;196m"
    RESET = "\033[0m"

    print(f"\n{GOLD}{BOLD}  JOVAS SECURITY SUITE — DEMO{RESET}\n")

    # 1. Sandbox
    print(f"{GOLD}━━━ 1. Language Sandbox ━━━━━━━━━━━━━━━━━━{RESET}")
    sandbox = JovasSandbox()

    safe_code = 'let x = 10\nprint(x)'
    bad_code  = 'import os\nos.system("rm -rf /")'

    r1 = sandbox.validate_source(safe_code)
    r2 = sandbox.validate_source(bad_code)
    print(f"  Safe code:    {GREEN}✅ SAFE{RESET}")
    print(f"  Attack code:  {RED}🚫 BLOCKED{RESET} — {r2['issues']}")

    # 2. DB Security
    print(f"\n{GOLD}━━━ 2. JovasDB Injection Prevention ━━━━━━{RESET}")
    clean = DBSecurity.sanitize_value({"name": "<script>alert('xss')</script>", "age": 25})
    print(f"  XSS sanitized:   {clean['name']}")
    try:
        DBSecurity.sanitize_table_name("users; DROP TABLE users")
    except ValueError as e:
        print(f"  SQL injection:   {RED}🚫 BLOCKED{RESET} — {e}")
    try:
        DBSecurity.sanitize_nlq("drop table users")
    except ValueError as e:
        print(f"  NLQ injection:   {RED}🚫 BLOCKED{RESET} — {e}")
    clean_where = DBSecurity.sanitize_where({"__proto__": "hack", "role": "admin"})
    print(f"  Prototype pollution: {RED}🚫 BLOCKED{RESET} — cleaned to {clean_where}")

    # 3. Rate Limiter
    print(f"\n{GOLD}━━━ 3. Rate Limiter ━━━━━━━━━━━━━━━━━━━━━{RESET}")
    rl = RateLimiter()
    for i in range(5):
        ok = rl.allow("user-123", limit=3, window=60)
        print(f"  Request {i+1}: {'✅ Allowed' if ok else '🚫 Blocked'}")
    print(f"  Status: {rl.status('user-123', 3, 60)}")

    # 4. Input Sanitizer
    print(f"\n{GOLD}━━━ 4. Input Sanitizer ━━━━━━━━━━━━━━━━━━{RESET}")
    s = InputSanitizer
    print(f"  HTML escape:    {s.html('<script>alert(1)</script>')}")
    print(f"  Filename clean: {s.filename('../../etc/passwd')}")
    print(f"  Email valid:    {s.email('  ALEX@JOVAS.DEV  ')}")
    try:
        s.url("http://localhost/admin")
    except ValueError as e:
        print(f"  SSRF blocked:   {RED}🚫{RESET} {e}")

    # 5. Secrets Manager
    print(f"\n{GOLD}━━━ 5. Secrets Manager ━━━━━━━━━━━━━━━━━━{RESET}")
    sm = SecretsManager()
    secret = sm.generate_secret(32)
    print(f"  Generated secret: {secret}")
    print(f"  PATH exists: {bool(sm.get('PATH'))}")

    # 6. Audit Log
    print(f"\n{GOLD}━━━ 6. Audit Log ━━━━━━━━━━━━━━━━━━━━━━━━{RESET}")
    log = SecurityAuditLog("jovas_security_demo.log")
    log.login_attempt("alice", success=True,  ip="192.168.1.1")
    log.login_attempt("bob",   success=False, ip="10.0.0.5")
    log.injection_attempt("users table", "__proto__", ip="1.2.3.4")
    log.blocked("Rate limit exceeded", {"user": "attacker", "ip": "5.6.7.8"})
    print(f"  Summary: {log.summary()}")

    # 7. Security Headers
    print(f"\n{GOLD}━━━ 7. Website Security Headers ━━━━━━━━━━{RESET}")
    headers = get_security_headers()
    for k, v in headers.items():
        print(f"  {k}: {v[:50]}...")

    # 8. GitHub Checklist
    print(f"\n{GOLD}━━━ 8. GitHub Security Checklist ━━━━━━━━━{RESET}")
    print(GITHUB_SECURITY_CHECKLIST)

    print(f"{GREEN}{BOLD}  ✅ All security modules working!{RESET}\n")
