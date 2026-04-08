# 🟡 Jovas Language — VS Code Extension

> Official VS Code extension for the Jovas programming language

---

## Features

### ✨ Syntax Highlighting
Full syntax highlighting for `.jovas` and `.jo` files:
- Keywords (`let`, `const`, `fn`, `class`, `async`, `await`, `expose`...)
- Built-in modules (`db`, `http`, `auth`, `ai`, `email`, `security`...)
- String interpolation (`"Hello, ${name}!"`)
- Operators (`|>`, `?.`, `=>`, `&&`, `||`...)
- Comments, numbers, booleans, null

### 📝 Snippets
50+ code snippets covering every Jovas feature:

| Prefix | What it generates |
|--------|-------------------|
| `fn` | Function declaration |
| `afn` | Async function |
| `expose` | Auto-API endpoint |
| `class` | Class with init |
| `app` | Full app boilerplate |
| `db` | JovasDB connection + table |
| `dbask` | Natural language DB query |
| `dbtx` | Database transaction |
| `jwt` | JWT sign + verify |
| `hash` | Password hash + verify |
| `validate` | Input validation |
| `email` | Send email |
| `emailt` | Email from template |
| `ai` | AI module call |
| `deploy` | One-line deployment |
| `sync` | Realtime subscription |
| `try` | Try-catch-finally |
| `match` | Pattern matching |
| `pipe` | Pipeline operator chain |
| `log` | Structured logging |
| `inspect` | Debug variable inspection |

### 🔴 Live Linting
Errors and warnings appear inline as you type:
- Constant reassignment
- Division by zero
- Infinite loop risk
- Unreachable code after return

### 💡 IntelliSense
- Auto-complete for all keywords and modules
- Hover documentation for every built-in
- Bracket matching and auto-closing pairs
- Indentation rules for Jovas blocks

### 🎨 Jovas Dark (Gold) Theme
A custom dark theme in the signature Jovas gold & black palette.

### ⌨️ Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| `Ctrl+Shift+R` | Run current `.jovas` file |
| `Ctrl+Shift+L` | Lint current file |
| `Ctrl+Shift+F` | Format current file |
| `Ctrl+Shift+J` | Open Jovas REPL |

---

## Installation

### From VS Code Marketplace (once published)
Search for **"Jovas Language"** in the Extensions panel.

### Manual Install
```bash
# 1. Clone the repo
git clone https://github.com/jovas-lang/jovas-vscode
cd jovas-vscode

# 2. Install dependencies
npm install

# 3. Compile TypeScript
npm run compile

# 4. Package the extension
npm run package

# 5. Install the .vsix file
code --install-extension jovas-language-1.0.0.vsix
```

---

## Extension Settings

| Setting | Default | Description |
|---------|---------|-------------|
| `jovas.pythonPath` | `python` | Python interpreter path |
| `jovas.runnerPath` | *(auto)* | Path to `run.py` launcher |
| `jovas.autoLintOnSave` | `true` | Lint on every save |
| `jovas.autoFormatOnSave` | `false` | Format on every save |
| `jovas.showOutputPanel` | `true` | Show output when running |
| `jovas.dbDataDir` | `./jovasdb_data` | JovasDB data directory |

---

## Requirements
- VS Code 1.85.0 or higher
- Python 3.10+ (for running `.jovas` files)
- Jovas runtime (`jovas.jo` + `run.py` + `jovas_modules.py`)

---

## File Icons
`.jovas` files display a gold diamond icon in the file explorer.

---

## License
MIT © Jovas Language Project
