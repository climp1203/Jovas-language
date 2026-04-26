# Jovas Language

> **The AI-Native Backend Programming Language**  
> Build backends, games, scripts, APIs and AI apps — zero setup, browser or desktop.

[![Live Demo](https://img.shields.io/badge/Try%20Online-Playground-FFD700?style=flat-square)](https://climp1203.github.io/jovas-language/playground.html)
[![License](https://img.shields.io/badge/License-MIT-green?style=flat-square)](LICENSE)
[![Tests](https://img.shields.io/badge/Tests-137%2F137-brightgreen?style=flat-square)](#)

---

## Quick Start

```bash
# Option 1 — Browser (zero install)
# Open: https://climp1203.github.io/jovas-language/playground.html

# Option 2 — Desktop IDE
git clone https://github.com/climp1203/jovas-language
cd jovas-language/jovas-ide && npm install && npm start

# Option 3 — Python backend
pip install flask flask-cors
python server.py    # → playground status dot turns green ●

# Option 4 — CLI
python run.py run myapp.jovas
python run.py repl
```

---

## The Pitch

Python needs 50 libraries for what Jovas does in one file:

```jovas
let db  = database.connect("myapp")
let usr = db.findOne("users", {id: 1})
let tok = security.jwtSign({id: usr.id}, "secret", 3600)
let ans = ai.ask("Summarize: ${usr.bio}")
email.send({to: usr.email, subject: "Welcome", body: ans})
```

No imports. No pip install. No config. It just works.

---

## Language Syntax

```jovas
// Variables
let name = "Jovas"
const MAX = 100
let items = [1, 2, 3]

// Functions
fn greet(name)
    return "Hello ${name}!"

async fn fetchUser(id)
    let r = await http.get("/users/${id}")
    return r.body

// Classes
class Dog
    fn init(name)
        self.name = name
    fn bark()
        return "${self.name} says Woof!"

let rex = Dog("Rex")
print(rex.bark())

// Control flow
for item in items
    print(item)

match status
    case "active"  => return "running"
    case "default" => return "idle"

// Advanced
let result = data |> clean |> validate |> save  // pipeline
let city   = user?.address?.city                // null-safe

try
    let data = json.parse(raw)
catch err
    log.error(["Failed:", err])
```

---

## 24 Built-in Modules

| Module | Key Methods |
|---|---|
| `database` | `connect`, `insert`, `select`, `update`, `delete`, `sql`, `begin` |
| `security` | `hash`, `verify`, `jwtSign`, `jwtVerify`, `encrypt`, `decrypt` |
| `ai` | `ask`, `write`, `translate`, `summarize`, `sentiment`, `classify` |
| `http` | `get`, `post`, `put`, `delete` |
| `server` | `create`, `get`, `post`, `listen` |
| `realtime` | `sync`, `broadcast`, `join`, `presence` |
| `auth` | `login`, `verify`, `refresh` |
| `email` | `send`, `template`, `otp` |
| `deploy` | `to`, `status`, `rollback` |
| `biometric` | `init`, `enroll`, `verify`, `mfa` |
| `network` | `scan`, `ping`, `dns`, `whois`, `payload` |
| `game` | `canvas`, `sprite`, `physics`, `collide`, `render`, `loop` |
| `story` | `create`, `chapter`, `character`, `write`, `export` |
| `log` | `info`, `warn`, `error` |
| `math` | `abs`, `sqrt`, `floor`, `random`, `pi` |
| `json` | `parse`, `stringify` |
| `crypto` | `hash`, `hmac`, `uuid`, `base64encode` |
| `time` | `now`, `format`, `sleep` |
| `file` | `read`, `write`, `exists` |
| `env` | `get`, `set` |
| `config` | `load`, `get` |
| `fmt` | `indent`, `align` |
| `lint` | `check`, `fix` |
| `debug` | `trace`, `inspect` |

---

## Backend API (server.py)

```bash
python server.py   # runs on http://localhost:5000
```

| Endpoint | Description |
|---|---|
| `POST /api/run` | Execute Jovas code via Python interpreter |
| `POST /api/run/stream` | Stream output via SSE |
| `POST /api/db/query` | JovasDB SQL queries |
| `POST /api/lint` | Static analysis |
| `POST /api/format` | Auto-format code |
| `POST /api/completions` | Autocomplete suggestions |
| `GET  /api/health` | Health + interpreter status |
| `GET  /api/examples` | All 18 examples metadata |

---

## IDE Features

| Feature | Shortcut |
|---|---|
| Run (backend → JS fallback) | `Ctrl+Enter` |
| Share code via URL | `Ctrl+Shift+S` |
| Format code | `Ctrl+Shift+F` |
| Command palette | `Ctrl+P` |
| Toggle sidebar | `Ctrl+B` |
| Toggle comment | `Ctrl+/` |

**Syntax highlighting** · **Autocomplete** · **4 themes** · **Error line markers** · **Real AI (Claude)** · **Share via URL**

---

## Project Structure

```
jovas-language/
├── index.html           ← Website (Home + Docs + UI Kit + Admin)
├── playground.html      ← Full IDE (18 examples, 24 modules)
├── 404.html             ← Smart redirect
├── server.py            ← Flask backend API
├── run.py               ← CLI launcher
├── jovas_interpreter.py ← Python AST interpreter
├── jovas_lexer.py       ← Tokenizer
├── jovas_parser.py      ← Parser → AST
├── jovas_modules.py     ← 24 built-in modules
├── jovasdb.py           ← JovasDB SQL engine
├── jovas_biometric.py   ← Biometric module
├── test_jovas.py        ← 137-test suite (100% passing)
├── jovas-ide/           ← Electron desktop IDE
└── jovas-vscode/        ← VS Code extension
```

---

## Tests

```bash
python test_jovas.py
# TOTAL: 137/137 (100%) ✅
```

---

## Roadmap

- [x] Core language + 24 modules
- [x] JovasDB · Web playground · Desktop IDE · VS Code extension
- [x] Backend API server · Real AI (Claude) · Syntax highlighting
- [x] network · game · story modules
- [ ] Jovas Package Manager (jpm)
- [ ] Mobile PWA · Multilingual coding
- [ ] Jovas Cloud · Community packages

---

MIT License — **Jovas v1.0.0** · Technology · Est. MMXXVI  
[Website](https://climp1203.github.io/jovas-language/) · [Playground](https://climp1203.github.io/jovas-language/playground.html)
