# Contributing to Jovas

Thank you for your interest in contributing to Jovas! This guide will help you get started.

---

## Ways to Contribute

- 🐛 **Report bugs** — Open an issue with a minimal reproduction
- 💡 **Suggest features** — Open a discussion with your idea
- 📝 **Improve docs** — Fix typos, add examples, improve clarity
- 🔧 **Submit code** — Bug fixes, new features, new modules
- 🧪 **Write tests** — Add cases to `test_jovas.py`
- 🌐 **Improve the website** — Enhance the frontend pages

---

## Getting Started

```bash
# 1. Fork the repo on GitHub, then clone your fork
git clone https://github.com/YOUR_USERNAME/jovas.git
cd jovas

# 2. Verify it works
python run.py version
python run.py run examples/hello.jovas

# 3. Run the test suite
python test_jovas.py

# 4. Create a branch for your change
git checkout -b feature/my-feature
```

---

## Project Structure

```
jovas/
├── jovas.jo              ← Core language engine (Lexer + Parser + Interpreter)
├── jovas_modules.py      ← All built-in modules (db, email, security, etc.)
├── jovasdb.py            ← JovasDB standalone database engine
├── run.py                ← CLI launcher
├── test_jovas.py         ← Test suite
├── examples/             ← Example .jovas programs
├── jovas-vscode/         ← VS Code extension
│   ├── package.json
│   ├── extension.ts
│   ├── syntaxes/         ← TextMate grammar
│   ├── snippets/         ← Code snippets
│   └── themes/           ← Color theme
└── jovas-website/        ← Website
    ├── index.html
    ├── playground.html
    ├── admin.html
    ├── docs.html
    └── components.html
```

---

## Adding a New Module

1. Open `jovas_modules.py`
2. Create a new class with methods that accept `args` lists:

```python
class MyModule:
    def myMethod(self, args):
        value = args[0] if args else None
        # ... your logic ...
        return result
```

3. Register it in `get_modules()` at the bottom of `jovas_modules.py`:

```python
def get_modules():
    return {
        # ... existing modules ...
        "mymodule": MyModule(),
    }
```

4. It's now available in `.jovas` files:

```jovas
let result = mymodule.myMethod("hello")
```

5. Add tests in `test_jovas.py`

---

## Adding a New Language Feature

The language pipeline is: **Lexer → Parser → Interpreter**

### Add a new keyword

1. In `jovas.jo`, find `class TT:` and add your token:
   ```python
   MYKEYWORD = "MYKEYWORD"
   ```
2. Add it to `KEYWORDS` dict:
   ```python
   "mykeyword": TT.MYKEYWORD,
   ```

### Add a new AST node

```python
class MyNode(Node):
    def __init__(self, value):
        self.value = value
```

### Add parsing

In `class Parser`, add a new `parse_mynode()` method and call it from `parse_stmt()`.

### Add execution

In `class Interpreter`, handle `MyNode` in `execute()`.

---

## Adding a VS Code Snippet

Open `jovas-vscode/snippets/jovas.json` and add:

```json
"My Snippet": {
  "prefix": "myprefix",
  "body": [
    "let ${1:name} = ${2:value}"
  ],
  "description": "Description of what this does"
}
```

---

## Writing Tests

Add test functions to `test_jovas.py`:

```python
def test_my_feature():
    out = interp_run('let x = 42\nprint(x)')
    assert out[0] == "42", f"Expected 42, got {out[0]}"

test("My feature description", lambda: test_my_feature())
```

---

## Submitting a Pull Request

1. Make sure all tests pass: `python test_jovas.py`
2. Run the examples: `python run.py run examples/hello.jovas`
3. Add tests for your changes
4. Update `CHANGELOG.md` under `[Unreleased]`
5. Submit your PR with a clear description

---

## Code Style

- Python: follow existing style — concise, readable, consistent
- Jovas examples: use 4-space indentation, descriptive variable names
- Comments: explain *why*, not *what*

---

## Reporting Bugs

Please include:
- Jovas version (`python run.py version`)
- Python version (`python --version`)
- Operating system
- Minimal `.jovas` code that reproduces the bug
- Expected vs actual output

---

## License

By contributing, you agree your code will be released under the **MIT License**.

Thank you for helping make Jovas better! 🟡
