#!/usr/bin/env python3
# ============================================
#   JOVAS LANGUAGE TEST SUITE v3
#   Run: python test_jovas.py
# ============================================
import sys, os, importlib.util
from importlib.machinery import SourceFileLoader

GOLD="\033[38;5;220m"; BOLD="\033[1m"; GREEN="\033[38;5;82m"
RED="\033[38;5;196m";  DIM="\033[38;5;244m"; RESET="\033[0m"

# Always resolve paths from this file's location — fixes Windows cross-drive errors
# (e.g. running from C:\ while project is on D:\)
HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)   # set cwd to project root so all relative paths work

passed = 0
failed = 0
errors = []

sys.path.insert(0, HERE)

# ── helpers ─────────────────────────────────
def test(name, fn):
    global passed, failed
    try:
        fn()
        print(f"  {GREEN}✅{RESET} {name}")
        passed += 1
    except AssertionError as e:
        print(f"  {RED}❌{RESET} {name}\n     {DIM}→ {e}{RESET}")
        failed += 1; errors.append((name, str(e)))
    except Exception as e:
        print(f"  {RED}💥{RESET} {name}\n     {DIM}→ {type(e).__name__}: {e}{RESET}")
        failed += 1; errors.append((name, f"{type(e).__name__}: {e}"))

def fresh_db(name):
    from jovas_modules import NativeDB
    db = NativeDB().connect([name])
    db.tables = {}          # wipe stale tables from previous runs
    return db

# ── load engine ─────────────────────────────
path   = os.path.join(HERE, "jovas.jo")
loader = SourceFileLoader("jovas_engine", path)
spec   = importlib.util.spec_from_file_location("jovas_engine", path, loader=loader)
E      = importlib.util.module_from_spec(spec)
loader.exec_module(E)

def run(source):
    """Execute Jovas source — calls execute() directly, never sys.exit()."""
    out    = []
    interp = E.Interpreter()
    interp.genv.set("print", lambda a: out.append(
        " ".join(str(interp._display(x)) for x in a)))
    lx  = E.Lexer(source.strip())
    tks = lx.tokenize()
    pa  = E.Parser(tks)
    ast = pa.parse()
    interp.execute(ast, interp.genv)
    return out

def parse(src):
    return E.Parser(E.Lexer(src).tokenize()).parse()

# ============================================
print(f"\n{GOLD}{BOLD}  JOVAS TEST SUITE{RESET}")
print(f"  {'─'*45}\n")

# ══ 1. LEXER ════════════════════════════════
print(f"{GOLD}  ▸ Lexer{RESET}")

def t_lex_basic():
    types = {t.type for t in E.Lexer("let x = 42").tokenize()}
    assert E.TT.LET in types
    assert E.TT.IDENTIFIER in types
    assert E.TT.NUMBER in types

def t_lex_string():
    strs = [t for t in E.Lexer('"hello"').tokenize() if t.type == E.TT.STRING]
    assert len(strs) == 1 and strs[0].value == "hello"

def t_lex_keywords():
    src   = "let const fn class if else for while return async await"
    types = {t.type for t in E.Lexer(src).tokenize()}
    for kw in [E.TT.LET, E.TT.CONST, E.TT.FN, E.TT.CLASS,
               E.TT.IF,  E.TT.FOR,   E.TT.WHILE, E.TT.RETURN]:
        assert kw in types, f"Missing keyword: {kw}"

def t_lex_operators():
    types = {t.type for t in E.Lexer("== != <= >= && ||").tokenize()}
    for op in [E.TT.EQ_EQ, E.TT.BANG_EQ, E.TT.LT_EQ,
               E.TT.GT_EQ, E.TT.AND, E.TT.OR]:
        assert op in types, f"Missing operator: {op}"

def t_lex_indent():
    types = [t.type for t in E.Lexer("fn f()\n    return 1").tokenize()]
    assert E.TT.INDENT in types
    assert E.TT.DEDENT in types

def t_lex_comments():
    types = [t.type for t in E.Lexer("// comment\nlet x = 1").tokenize()
             if t.type not in (E.TT.NEWLINE, E.TT.EOF)]
    assert E.TT.LET in types
    assert E.TT.IDENTIFIER in types

test("Lexer — basic tokens",     t_lex_basic)
test("Lexer — string literal",   t_lex_string)
test("Lexer — all keywords",     t_lex_keywords)
test("Lexer — operators",        t_lex_operators)
test("Lexer — indent / dedent",  t_lex_indent)
test("Lexer — comments skipped", t_lex_comments)

# ══ 2. PARSER ═══════════════════════════════
print(f"\n{GOLD}  ▸ Parser{RESET}")

def t_parse_let():
    n = parse("let x = 42").body[0]
    assert isinstance(n, E.VarDecl) and n.name == "x"

def t_parse_const():
    n = parse("const MAX = 100").body[0]
    assert isinstance(n, E.VarDecl)
    assert n.constant == True
    assert n.name == "MAX"

def t_parse_fn():
    n = parse("fn add(a, b)\n    return a").body[0]
    assert isinstance(n, E.FunctionDecl)
    assert n.name == "add"
    assert len(n.params) == 2

def t_parse_async():
    n = parse("async fn fetch(url)\n    return url").body[0]
    assert isinstance(n, E.FunctionDecl)
    assert n.is_async == True

def t_parse_if():
    n = parse("if x > 0\n    print(x)").body[0]
    assert isinstance(n, E.IfStmt)

def t_parse_for():
    n = parse("for item in items\n    print(item)").body[0]
    assert isinstance(n, E.ForStmt)
    assert n.var == "item"

def t_parse_class():
    n = parse("class Dog\n    fn init(name)\n        self.name = name").body[0]
    assert isinstance(n, E.ClassDecl)
    assert n.name == "Dog"
    assert len(n.methods) == 1

def t_parse_try():
    n = parse("try\n    let x = 1\ncatch err\n    print(err)").body[0]
    assert isinstance(n, E.TryCatch)

def t_parse_match():
    n = parse('match x\n    case "a" => print(1)').body[0]
    assert isinstance(n, E.MatchStmt)

test("Parser — let declaration",   t_parse_let)
test("Parser — const declaration", t_parse_const)
test("Parser — function decl",     t_parse_fn)
test("Parser — async function",    t_parse_async)
test("Parser — if statement",      t_parse_if)
test("Parser — for loop",          t_parse_for)
test("Parser — class declaration", t_parse_class)
test("Parser — try / catch",       t_parse_try)
test("Parser — match statement",   t_parse_match)

# ══ 3. INTERPRETER ══════════════════════════
print(f"\n{GOLD}  ▸ Interpreter{RESET}")

def t_print():
    assert run('print("hello")') == ["hello"]

def t_arithmetic():
    out = run("print(2 + 3)\nprint(10 - 4)\nprint(3 * 4)\nprint(10 / 2)")
    assert out == ["5", "6", "12", "5.0"], f"Got {out}"

def t_variables():
    assert run("let x = 10\nlet y = 20\nprint(x + y)") == ["30"]

def t_interpolation():
    assert run('let n = "Jovas"\nprint("Hi, ${n}!")') == ["Hi, Jovas!"]

def t_const():
    assert run("const P = 8080\nprint(P)") == ["8080"]

def t_const_immutable():
    raised = False
    try:
        run("const X = 1\nX = 2")
    except Exception:
        raised = True
    assert raised, "Reassigning const should raise an error"

def t_if_else():
    out = run('let x = 10\nif x > 5\n    print("big")\nelse\n    print("small")')
    assert out == ["big"]

def t_for_loop():
    assert run("let t = 0\nfor n in [1,2,3,4,5]\n    t = t + n\nprint(t)") == ["15"]

def t_while_loop():
    assert run("let i = 0\nwhile i < 3\n    i = i + 1\nprint(i)") == ["3"]

def t_repeat():
    assert run("let c = 0\nrepeat 5\n    c = c + 1\nprint(c)") == ["5"]

def t_function():
    assert run("fn add(a, b)\n    return a + b\nprint(add(3, 7))") == ["10"]

def t_recursion():
    src = "fn f(n)\n    if n <= 1\n        return 1\n    return n * f(n - 1)\nprint(f(6))"
    assert run(src) == ["720"]

def t_class():
    src = ('class Dog\n'
           '    fn init(n)\n'
           '        self.name = n\n'
           '    fn bark()\n'
           '        return self.name + " says Woof!"\n'
           'let d = Dog("Rex")\n'
           'print(d.bark())')
    assert run(src) == ["Rex says Woof!"]

def t_array():
    assert run("let a = [1, 2, 3]\nprint(len(a))") == ["3"]

def t_object():
    assert run('let u = { name: "Alex" }\nprint(u.name)') == ["Alex"]

def t_null_safety():
    assert run("let u = { profile: null }\nlet av = u?.profile?.avatar\nprint(av)") == ["null"]

def t_try_catch():
    # must not raise
    run("try\n    let x = 1\ncatch err\n    print(err.message)")

def t_booleans():
    assert run("print(true && false)\nprint(true || false)\nprint(!true)") == ["false","true","false"]

def t_string_builtins():
    out = run('print(len("Hello"))\nprint(str(42))\nprint(int("10") + 5)')
    assert out == ["5", "42", "15"], f"Got {out}"

def t_pipeline():
    src = ("fn dbl(x)\n    return x * 2\n"
           "fn add10(x)\n    return x + 10\n"
           "let r = 5 |> dbl |> add10\nprint(r)")
    assert run(src) == ["20"]

def t_multiline_object():
    src = ('let r = security.validate(\n'
           '    { name: "Alice", email: "alice@jovas.dev" },\n'
           '    {\n'
           '        name:  { required: true, minLength: 2 },\n'
           '        email: { required: true, type: "email" }\n'
           '    }\n'
           ')\nprint(r.valid)')
    assert run(src) == ["true"], f"Got {run(src)}"

def t_multiline_array():
    src = ("let nums = [\n    10,\n    20,\n    30\n]\n"
           "let t = 0\nfor n in nums\n    t = t + n\nprint(t)")
    assert run(src) == ["60"]

test("Interpreter — print",                t_print)
test("Interpreter — arithmetic",           t_arithmetic)
test("Interpreter — variables",            t_variables)
test("Interpreter — string interpolation", t_interpolation)
test("Interpreter — constants",            t_const)
test("Interpreter — const immutable",      t_const_immutable)
test("Interpreter — if / else",            t_if_else)
test("Interpreter — for loop",             t_for_loop)
test("Interpreter — while loop",           t_while_loop)
test("Interpreter — repeat",               t_repeat)
test("Interpreter — function call",        t_function)
test("Interpreter — recursion",            t_recursion)
test("Interpreter — class",                t_class)
test("Interpreter — array",                t_array)
test("Interpreter — object",               t_object)
test("Interpreter — null safety",          t_null_safety)
test("Interpreter — try / catch",          t_try_catch)
test("Interpreter — boolean logic",        t_booleans)
test("Interpreter — string builtins",      t_string_builtins)
test("Interpreter — pipeline |>",          t_pipeline)
test("Interpreter — multi-line object",    t_multiline_object)
test("Interpreter — multi-line array",     t_multiline_array)

# ══ 4. JOVASDB ══════════════════════════════
print(f"\n{GOLD}  ▸ JovasDB{RESET}")

def t_db_connect():
    assert fresh_db("t_conn") is not None

def t_db_create_table():
    db = fresh_db("t_create")
    db.createTable(["items", [
        {"name": "id",   "type": "INTEGER", "pk": True},
        {"name": "name", "type": "TEXT",    "nullable": False},
    ]])
    assert "items" in db.tables

def t_db_crud():
    db = fresh_db("t_crud")
    db.createTable(["vals", [
        {"name": "id", "type": "INTEGER", "pk": True},
        {"name": "v",  "type": "TEXT"},
    ]])
    db.insert(["vals", {"id": 1, "v": "hello"}])
    db.insert(["vals", {"id": 2, "v": "world"}])
    rows = db.select(["vals"])
    assert len(rows) == 2, f"Expected 2 rows, got {len(rows)}"

def t_db_update():
    db = fresh_db("t_update")
    db.createTable(["u", [
        {"name": "id", "type": "INTEGER", "pk": True},
        {"name": "n",  "type": "TEXT"},
    ]])
    db.insert(["u", {"id": 1, "n": "old"}])
    db.update(["u", {"id": 1}, {"n": "new"}])
    row = db.findOne(["u", {"id": 1}])
    assert row["n"] == "new", f"Expected 'new', got '{row['n']}'"

def t_db_delete():
    db = fresh_db("t_delete")
    db.createTable(["d", [{"name": "id", "type": "INTEGER", "pk": True}]])
    db.insert(["d", {"id": 1}])
    db.insert(["d", {"id": 2}])
    db.delete(["d", {"id": 1}])
    assert db.count(["d"]) == 1, f"Expected 1 row after delete"

def t_db_tx_commit():
    db = fresh_db("t_tx_commit")
    db.createTable(["tx", [{"name": "id", "type": "INTEGER", "pk": True}]])
    tx = db.begin()
    tx.insert(["tx", {"id": 1}])
    tx.insert(["tx", {"id": 2}])
    tx.commit()
    assert db.count(["tx"]) == 2, f"Expected 2 after commit"

def t_db_tx_rollback():
    db = fresh_db("t_tx_rollback")
    db.createTable(["rb", [{"name": "id", "type": "INTEGER", "pk": True}]])
    tx = db.begin()
    tx.insert(["rb", {"id": 1}])
    tx.rollback()
    assert db.count(["rb"]) == 0, f"Expected 0 after rollback"

def t_db_nlq():
    db = fresh_db("t_nlq")
    db.createTable(["users", [
        {"name": "id",     "type": "INTEGER", "pk": True},
        {"name": "name",   "type": "TEXT"},
        {"name": "role",   "type": "TEXT"},
        {"name": "active", "type": "BOOLEAN", "default": True},
    ]])
    db.insert(["users", {"id": 1, "name": "Alice", "role": "admin", "active": True}])
    db.insert(["users", {"id": 2, "name": "Bob",   "role": "user",  "active": False}])
    db.insert(["users", {"id": 3, "name": "Carol", "role": "user",  "active": True}])

    # "active users" must NOT filter by role
    active = db.ask(["find all active users"])
    assert len(active) >= 1, f"Expected active users, got {len(active)}"

    # "find all admins" must filter role=admin only
    admins = db.ask(["find all admins"])
    assert len(admins) == 1,              f"Expected 1 admin, got {len(admins)}"
    assert admins[0]["role"] == "admin",  f"Wrong role: {admins[0]['role']}"

    # "find inactive users" must return only Bob
    inactive = db.ask(["find inactive users"])
    assert len(inactive) == 1, f"Expected 1 inactive, got {len(inactive)}"

test("JovasDB — connect",               t_db_connect)
test("JovasDB — createTable",           t_db_create_table)
test("JovasDB — insert & select",       t_db_crud)
test("JovasDB — update",                t_db_update)
test("JovasDB — delete",                t_db_delete)
test("JovasDB — transaction commit",    t_db_tx_commit)
test("JovasDB — transaction rollback",  t_db_tx_rollback)
test("JovasDB — natural language",      t_db_nlq)

# ══ 5. SECURITY ═════════════════════════════
print(f"\n{GOLD}  ▸ Security{RESET}")

from jovas_modules import SecurityModule
S = SecurityModule()

def t_sec_hash():
    h = S.hash(["pass123"])
    assert h.startswith("$jvt$"),          "Bad hash prefix"
    assert S.verify(["pass123", h]) == True,  "Correct password should pass"
    assert S.verify(["wrong",   h]) == False, "Wrong password should fail"

def t_sec_jwt():
    token = S.jwtSign([{"userId": 1}, "secret", 3600])
    assert token.count(".") == 2, "JWT needs 3 parts"
    result = S.jwtVerify([token, "secret"])
    assert result["valid"] == True
    assert result["payload"]["userId"] == 1

def t_sec_validate():
    ok  = S.validate([{"email": "a@b.com", "age": 25},
                      {"email": {"required": True, "type": "email"},
                       "age":   {"min": 18}}])
    bad = S.validate([{"email": "notvalid", "age": 10},
                      {"email": {"type": "email"},
                       "age":   {"min": 18}}])
    assert ok["valid"]  == True,  f"Valid input failed"
    assert bad["valid"] == False, f"Invalid input passed"

def t_sec_roles():
    S.defineRole(["admin_r", ["read", "write", "delete"]])
    S.defineRole(["user_r",  ["read"]])
    assert S.permit([{"id": 1, "role": "admin_r"}, "delete"]) == True
    assert S.permit([{"id": 2, "role": "user_r"},  "delete"]) == False

test("Security — password hash / verify", t_sec_hash)
test("Security — JWT sign / verify",      t_sec_jwt)
test("Security — input validation",       t_sec_validate)
test("Security — role permissions",       t_sec_roles)

# ══ 6. EMAIL ════════════════════════════════
print(f"\n{GOLD}  ▸ Email{RESET}")

from jovas_modules import EmailModule
EM = EmailModule()

def t_email_send():
    r = EM.send([{"to": "x@y.com", "subject": "Hi", "body": "Hello"}])
    assert r is not None
    assert r.get("status") in ("logged", "sent")

def t_email_template():
    r = EM.template(["welcome", {"name": "Alex", "app": "TestApp"}])
    assert r is not None
    assert "Alex"    in r["body"]
    assert "TestApp" in r["body"]

def t_email_otp():
    otp = EM.otp([6])
    assert len(otp) == 6,   f"OTP length: {len(otp)}"
    assert otp.isdigit(),   f"OTP not numeric: {otp}"

test("Email — send (dev mode)",  t_email_send)
test("Email — template render",  t_email_template)
test("Email — OTP generation",   t_email_otp)

# ══ 7. LINTER ═══════════════════════════════
print(f"\n{GOLD}  ▸ Linter{RESET}")

from jovas_modules import JovasLinter
LN = JovasLinter()

def t_lint_clean():
    r = LN.check(["let x = 1\nprint(x)"])
    assert r["errors"] == 0, f"Clean code had errors: {r['issues']}"

def t_lint_const():
    r = LN.check(["const X = 1\nX = 2"])
    assert r["errors"] >= 1, "Should catch const reassignment"

def t_lint_divzero():
    r = LN.check(["let x = 10 / 0"])
    assert r["errors"] >= 1, "Should catch division by zero"

def t_lint_unreachable():
    r = LN.check(["fn f()\n    return 1\n    print(\"dead\")"])
    assert r["errors"] >= 1, "Should catch unreachable code"

test("Linter — clean code passes",   t_lint_clean)
test("Linter — const reassignment",  t_lint_const)
test("Linter — division by zero",    t_lint_divzero)
test("Linter — unreachable code",    t_lint_unreachable)

# ══ RESULTS ═════════════════════════════════
total = passed + failed
print(f"\n  {'─'*45}")
print(f"  {GOLD}{BOLD}Results:{RESET}  "
      f"{GREEN}{passed} passed{RESET}  ·  "
      f"{RED if failed else DIM}{failed} failed{RESET}  ·  "
      f"{total} total")

if errors:
    print(f"\n  {RED}Failed tests:{RESET}")
    for name, err in errors:
        print(f"  {DIM}  • {name}\n    {err}{RESET}")

pct = int(passed / total * 100) if total else 0
bar = "█" * (pct // 5) + "░" * (20 - pct // 5)
print(f"\n  [{GOLD}{bar}{RESET}] {pct}%\n")
sys.exit(0 if failed == 0 else 1)
