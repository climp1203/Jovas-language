# Changelog

All notable changes to the Jovas language are documented here.

---

## [1.0.0] — 2026-03-29

### 🎉 Initial Release

#### Language Core
- Lexer — full tokenizer for `.jovas` and `.jo` files
- Parser — AST builder with 20+ node types
- Interpreter — tree-walk executor with closures and scope chains
- REPL — interactive Jovas shell (`python run.py repl`)
- CLI — `run`, `check`, `version` commands

#### Syntax Features
- `let` / `const` variable declarations
- `fn` / `async fn` / `expose fn` function declarations
- `class` with `self` and `init`
- `if` / `else if` / `else` conditionals
- `for item in list` loops
- `while` and `repeat N` loops
- `match` / `case` pattern matching
- `try` / `catch` / `finally` error handling
- `await` for async operations
- `thread fn` and `parallel` for concurrency
- String interpolation with `${expr}`
- Null-safe access with `?.`
- Pipeline operator `|>`
- Optional type hints `fn greet(name: string): string`
- Multiple return values `return x, y`
- Constants with `const` (immutable, enforced at runtime)

#### Built-in Standard Library (21 modules)
- `http` — GET, POST, PUT, PATCH, DELETE with real network calls
- `database` — JovasDB native integration
- `auth` — JWT sign/verify
- `security` — PBKDF2 hashing, JWT, validation, CORS, roles
- `email` — SMTP, templates (welcome/OTP/invoice/reset), queue
- `ai` — ask, sentiment, summarize, translate, classify, embed
- `server` — HTTP server with routing
- `deploy` — one-line cloud deployment
- `realtime` — pub/sub, presence, events
- `log` — structured logging (debug/info/warn/error/fatal)
- `file` — read, write, append, delete, exists, list
- `math` — sqrt, floor, ceil, pow, abs, PI, E
- `json` — parse, stringify
- `crypto` — SHA256 hash, MD5
- `time` — now, sleep, format, today
- `env` — get, set environment variables
- `config` — load .env files
- `rateLimit` — per-key rate limiting with windows
- `fmt` — source code formatter
- `lint` — static analysis linter
- `debug` — breakpoints, watch, inspect, trace, timer, assert

#### JovasDB
- Full PostgreSQL-style database engine
- Table schemas with typed columns
- B-tree style indexes
- Foreign key relationships and validation
- ACID transactions (commit/rollback with snapshots)
- Migration system (up/down)
- Natural language queries via `db.ask()`
- Persistent `.jdb` file format
- Interactive shell (`python jovasdb.py shell <name>`)

#### Tooling
- VS Code extension — syntax highlighting, 50+ snippets, Gold theme, IntelliSense, live linting
- Jovas Formatter (`fmt.format()`, `fmt.formatFile()`)
- Jovas Linter (`lint.check()`, `lint.checkFile()`)
- Debugger — breakpoints, watches, stack trace, timing, log export

#### Frontend / Website
- Landing page (`jovas-website/index.html`)
- Online playground with AI execution (`playground.html`)
- JovasDB admin dashboard (`admin.html`)
- Documentation site with search (`docs.html`)
- UI component library (`components.html`)

#### Examples
- `hello.jovas` — Hello World
- `fullapp.jovas` — Complete backend application
- `auth.jovas` — JWT authentication flow
- `database.jovas` — JovasDB CRUD and NLQ
- `security.jovas` — Full security module demo
- `api.jovas` — Auto-generated REST API with `expose fn`
- `realtime.jovas` — Real-time chat with presence

#### GitHub
- README with full feature overview
- LICENSE (MIT)
- .gitignore
- GitHub Actions CI (syntax check, run examples, cross-platform, VS Code validation)
- Test suite (`test_jovas.py`) with 40+ tests

---

## Roadmap

### [1.1.0] — Planned
- Real TCP HTTP server (replace mock with actual `socket` server)
- `jovas` command shortcut (instead of `python run.py`)
- JPM package registry server
- More standard library modules (CSV, XML, PDF)
- Improved error messages with line/column highlighting

### [1.2.0] — Planned
- Optional static typing with full type inference
- Generics / parameterized types
- Module system (`export fn`, `import from "file"`)
- Compiled output to Python bytecode
- Performance benchmarks vs Node.js / Python

### [2.0.0] — Vision
- Native compiled runtime (Go or Rust backend)
- Jovas package registry (jpm.jovas.dev)
- Cloud deployment integration (AWS, GCP, Azure)
- Visual Studio Code marketplace publication
- Jovas community forum
