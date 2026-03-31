<div align="center">

```
  ╔═══════════════════════════════════════════════════════╗
  ║  ░░░  ░░░   ░░░   ░░   ░░  ░░░  ░░░                 ║
  ║    ░  ░  ░  ░  ░  ░░   ░░  ░  ░ ░                   ║
  ║    ░  ░░░   ░░░   ░░░░░░░  ░░░  ░░░                 ║
  ║ ░  ░  ░  ░  ░ ░   ░░   ░░  ░  ░    ░                ║
  ║  ░░░  ░░░   ░  ░  ░░   ░░  ░░░  ░░░                 ║
  ╚═══════════════════════════════════════════════════════╝
```

# Jovas

### The AI-Native Backend Programming Language

[![CI](https://github.com/jovas-lang/jovas/actions/workflows/ci.yml/badge.svg)](https://github.com/jovas-lang/jovas/actions)
[![Version](https://img.shields.io/badge/version-1.0.0-FFD700?style=flat&labelColor=000)](https://github.com/jovas-lang/jovas/releases)
[![License](https://img.shields.io/badge/license-MIT-FFD700?style=flat&labelColor=000)](LICENSE)
[![Python](https://img.shields.io/badge/requires-Python%203.10+-FFD700?style=flat&labelColor=000)](https://python.org)
[![Examples](https://img.shields.io/badge/examples-7%20passing-4ADE80?style=flat&labelColor=000)](#examples)

**Jovas** combines the best features of every major backend language into one clean, expressive syntax — with **AI**, **databases**, **security**, **real-time**, and **auto API generation** built right in from day one.

[🌐 Website](https://jovas-lang.github.io/jovas) · [🎮 Playground](https://jovas-lang.github.io/jovas/playground) · [📖 Docs](https://jovas-lang.github.io/jovas/docs) · [🗄️ DB Admin](https://jovas-lang.github.io/jovas/admin)

</div>

---

## Why Jovas?

Every other backend language makes you install 10 packages before you can build anything real. Jovas ships with everything:

| Feature | Jovas | Node.js | Python | Go |
|---|:---:|:---:|:---:|:---:|
| Built-in AI module | ✅ | ❌ | ❌ | ❌ |
| Built-in database | ✅ JovasDB | ❌ | ❌ | ❌ |
| Natural language queries | ✅ | ❌ | ❌ | ❌ |
| Auto API generation | ✅ `expose fn` | ❌ | ❌ | ❌ |
| One-line deployment | ✅ | ❌ | ❌ | ❌ |
| Built-in real-time | ✅ | ❌ socket.io | ❌ | ❌ |
| Built-in email | ✅ templates | ❌ nodemailer | ❌ | ❌ |
| Built-in security | ✅ full suite | ❌ bcrypt+jwt | ❌ | ❌ |
| Smart error messages | ✅ with fixes | ❌ | ❌ | ❌ |
| VS Code extension | ✅ official | ✅ | ✅ | ✅ |

---

## Quick Start

```bash
# Clone
git clone https://github.com/jovas-lang/jovas.git
cd jovas

# Run the demo
python run.py

# Start the interactive REPL
python run.py repl

# Run a .jovas file
python run.py run examples/hello.jovas

# Or use the shortcut (Unix/Mac)
chmod +x jovas
./jovas examples/hello.jovas
```

**Requirements:** Python 3.10+ · No external packages needed

---

## A Complete Backend in 25 Lines

```jovas
// app.jovas

import json

const APP  = "MyApp"
const PORT = 8080

let db = database.connect("myapp")

// Expose fn → auto-generates REST endpoint + docs + validation
expose fn getUsers()
    return db.ask("find all active users")

expose fn createUser(name, email)
    let valid = security.validate(
        { name: name, email: email },
        { name: { required: true }, email: { required: true, type: "email" } }
    )
    if valid.valid == false
        return { error: valid.errors }
    db.insert("users", { name: name, email: email })
    email.sendTemplate("welcome", { name: name, app: APP }, email)
    return { ok: true, token: security.jwtSign({ email: email }, "secret", 3600) }

fn onStart()
    log.info(["${APP} live on port ${PORT}"])

let app = server.create()
app.listen(PORT, onStart)
```

```
→ POST /api/getUsers    auto-created
→ POST /api/createUser  auto-created
→ MyApp live on port 8080
```

---

## Language Tour

<details>
<summary><strong>Variables & Constants</strong></summary>

```jovas
let name    = "Jovas"        // mutable
let port    = 8080
let active  = true
let data    = null
const MAX   = 9999           // immutable — reassignment throws error

// String interpolation
let msg = "Running ${name} on port ${port}"

// Null-safe access — no crashes
let avatar = user?.profile?.avatar
```

</details>

<details>
<summary><strong>Functions</strong></summary>

```jovas
// Basic
fn greet(name)
    return "Hello, ${name}!"

// Async
async fn fetchData(url)
    let res = await http.get(url)
    return res.body

// Expose → auto-generates REST endpoint + docs
expose fn getUser(id)
    return db.findOne("users", { id: id })

// Multiple return values
fn minmax(items)
    return min(items), max(items)

let lo, hi = minmax([3, 1, 9, 2])

// Optional type hints
fn add(a: int, b: int): int
    return a + b
```

</details>

<details>
<summary><strong>Classes</strong></summary>

```jovas
class BankAccount
    fn init(owner, balance)
        self.owner   = owner
        self.balance = balance

    fn deposit(amount)
        self.balance = self.balance + amount
        return self.balance

    fn withdraw(amount)
        if amount > self.balance
            return "Insufficient funds"
        self.balance = self.balance - amount
        return self.balance

let acc = BankAccount("Alice", 1000)
print(acc.deposit(500))    // 1500
print(acc.withdraw(200))   // 1300
```

</details>

<details>
<summary><strong>Control Flow & Pattern Matching</strong></summary>

```jovas
// if / else if / else
if score >= 90
    print("A")
else if score >= 80
    print("B")
else
    print("C")

// Pattern matching
match status
    case "active"  => print("✅ Running")
    case "stopped" => print("🔴 Halted")
    case "pending" => print("⏳ Starting")
    case "default" => print("❓ Unknown")

// Pipeline operator
let result = data |> filterActive |> sortByAge |> limit
```

</details>

<details>
<summary><strong>Error Handling</strong></summary>

```jovas
try
    let data = await db.query("SELECT * FROM users")
    print(data)
catch err
    print("Error: ${err.message}")
finally
    db.close()
```

Jovas also provides **Smart Errors** — every runtime error includes a plain-English explanation and a ready-to-use code fix:

```
╔══════════════════════════════════════════╗
║         JOVAS SMART ERROR                ║
╠══════════════════════════════════════════╣
║  division by zero on line 42             ║
╚══════════════════════════════════════════╝
  💡 Check if the divisor is 0 before dividing:
      if y != 0
          return x / y
```

</details>

<details>
<summary><strong>Async & Threads</strong></summary>

```jovas
async fn fetchUser(id)
    let res = await http.get("https://api.example.com/users/${id}")
    return res.body

// Background thread
thread fn processQueue()
    processHeavyTask()

// Run multiple tasks in parallel
parallel
    task fetchUsers()
    task fetchOrders()
    task fetchProducts()
```

</details>

---

## Built-in Modules (21 total)

### 🗄️ JovasDB — Native Database

```jovas
let db = database.connect("myapp")

let cols = [
    { name: "id",    type: "INTEGER", pk: true },
    { name: "name",  type: "TEXT",    nullable: false },
    { name: "email", type: "TEXT",    unique: true }
]
db.createTable("users", cols)

// CRUD
db.insert("users", { id: 1, name: "Alice", email: "alice@jovas.dev" })
let users = db.select("users", { role: "admin" })
db.update("users", { id: 1 }, { role: "admin" })
db.delete("users", { id: 99 })

// Natural language queries
let active  = db.ask("find all active users")
let orders  = db.ask("find top 5 orders sort by total desc")

// Transactions
let tx = db.begin()
tx.insert("users", { name: "Bob" })
tx.commit()    // or tx.rollback()
```

### 🔒 Security

```jovas
let hashed  = security.hash("mypassword")
let valid   = security.verify("mypassword", hashed)    // true
let token   = security.jwtSign({ userId: 1 }, "secret", 3600)
let payload = security.jwtVerify(token, "secret")

let result = security.validate(data, {
    email:    { required: true, type: "email" },
    age:      { required: true, min: 18 },
    password: { required: true, minLength: 6 }
})

security.defineRole("admin", ["read", "write", "delete"])
let ok = security.permit(user, "delete")
```

### 🤖 AI

```jovas
let reply     = ai.ask("Explain this error: ${err.message}")
let sentiment = ai.sentiment("Jovas is amazing!")   // { sentiment: "positive" }
let summary   = ai.summarize(longText)
let fr        = ai.translate("Hello", "fr")
let category  = ai.classify(text, ["bug", "feature", "question"])
```

### 📧 Email

```jovas
email.configure({ host: "smtp.gmail.com", port: 587,
                  user: "me@gmail.com", password: "pass" })
email.send({ to: "user@example.com", subject: "Hi!", body: "Hello!" })
email.sendTemplate("welcome", { name: "Alex", app: "MyApp" }, "alex@example.com")
let otp = email.otp(6)
```

### 🚀 Deploy

```jovas
deploy.to("cloud", { region: "us-east-1", scale: "auto" })
deploy.scale(5)
deploy.rollback()
```

### ⚡ Real-time

```jovas
realtime.sync("chat", fn(data)
    print("${data.from}: ${data.text}")
)
realtime.broadcast("chat", { from: "Alice", text: "Hello!" })
let online = realtime.presence("chat")
```

### Other Modules

| Module | Key Methods |
|--------|-------------|
| `http` | `get`, `post`, `put`, `patch`, `delete` |
| `server` | `create`, `get`, `post`, `listen` |
| `auth` | `sign`, `verify` |
| `log` | `debug`, `info`, `warn`, `error`, `fatal` |
| `file` | `read`, `write`, `append`, `delete`, `exists` |
| `math` | `sqrt`, `floor`, `ceil`, `pow`, `abs`, `PI` |
| `json` | `parse`, `stringify` |
| `crypto` | `hash`, `md5` |
| `time` | `now`, `sleep`, `format`, `today` |
| `config` | `load`, `get`, `require` |
| `rateLimit` | `check`, `reset` |
| `fmt` | `format`, `formatFile` |
| `lint` | `check`, `checkFile` |
| `debug` | `breakpoint`, `watch`, `inspect`, `trace`, `time`, `assert` |

---

## Examples

| File | Description |
|------|-------------|
| [`examples/hello.jovas`](examples/hello.jovas) | Hello World |
| [`examples/auth.jovas`](examples/auth.jovas) | JWT login & registration flow |
| [`examples/database.jovas`](examples/database.jovas) | JovasDB CRUD, NLQ, transactions |
| [`examples/security.jovas`](examples/security.jovas) | Hashing, JWT, validation, CORS, roles |
| [`examples/api.jovas`](examples/api.jovas) | Auto-generated REST API with `expose fn` |
| [`examples/realtime.jovas`](examples/realtime.jovas) | Real-time chat room with presence |
| [`examples/fullapp.jovas`](examples/fullapp.jovas) | Complete backend application |

---

## CLI Reference

```bash
python run.py run <file.jovas>     # Run a Jovas program
python run.py repl                 # Interactive REPL shell
python run.py check <file.jovas>   # Syntax check only
python run.py version              # Show version info

python jovasdb.py shell <name>     # JovasDB interactive shell
python jovasdb.py demo             # Run JovasDB demo

python test_jovas.py               # Run the full test suite (40+ tests)
```

---

## VS Code Extension

The official extension lives in [`jovas-vscode/`](jovas-vscode/):

- Syntax highlighting for `.jovas` and `.jo` files
- 50+ code snippets (`fn`, `app`, `db`, `dbtx`, `jwt`, `email`, `ai`, `deploy`...)
- Live inline linting
- IntelliSense with hover docs for every module
- **Jovas Dark (Gold)** color theme
- Shortcuts: `Ctrl+Shift+R` run · `Ctrl+Shift+L` lint · `Ctrl+Shift+J` REPL

```bash
cd jovas-vscode
npm install && npm run compile && npm run package
code --install-extension jovas-language-1.0.0.vsix
```

---

## Website

Five fully static HTML pages in [`jovas-website/`](jovas-website/) — deploy to GitHub Pages instantly:

| Page | Description |
|------|-------------|
| `index.html` | Landing page with live code demo |
| `playground.html` | Online IDE with AI-powered execution |
| `admin.html` | JovasDB visual dashboard |
| `docs.html` | Full documentation with search |
| `components.html` | UI component library (Gold & Black) |

---

## Project Structure

```
jovas/
├── jovas.jo              ← Language engine (Lexer · Parser · Interpreter)
├── jovas_modules.py      ← All built-in modules
├── jovasdb.py            ← JovasDB standalone engine + CLI
├── run.py                ← CLI launcher
├── jovas                 ← Shortcut command
├── test_jovas.py         ← Test suite
├── README.md / CHANGELOG.md / CONTRIBUTING.md / LICENSE
├── .github/workflows/ci.yml
├── examples/             ← 7 example programs
├── jovas-vscode/         ← VS Code extension
└── jovas-website/        ← Static website (5 pages)
```

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) — contributions of all kinds are welcome.

---

## Roadmap

- **v1.1** — Real TCP HTTP server · `jovas` global command · JPM package registry
- **v1.2** — Optional static typing · Module system · More stdlib
- **v2.0** — Native compiled runtime · Cloud integrations · VS Code Marketplace

Full history in [CHANGELOG.md](CHANGELOG.md).

---

## License

MIT © 2026 Jovas Language Project

---

<div align="center">

**Built with 🟡 by the Jovas team**

*Technology · Est. MMXXVI*

</div>
