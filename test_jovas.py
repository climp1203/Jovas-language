#!/usr/bin/env python3
# ============================================
#   JOVAS LANGUAGE TEST SUITE
#   Tests lexer, parser, and interpreter
#   Run: python test_jovas.py
# ============================================

import sys, os, json, time
sys.path.insert(0, os.path.dirname(__file__))

GOLD  = "\033[38;5;220m"
GREEN = "\033[38;5;82m"
RED   = "\033[38;5;196m"
DIM   = "\033[38;5;244m"
BOLD  = "\033[1m"
RESET = "\033[0m"

passed = 0
failed = 0
errors = []

def test(name, fn):
    global passed, failed
    try:
        fn()
        print(f"  {GREEN}✅{RESET} {name}")
        passed += 1
    except AssertionError as e:
        print(f"  {RED}❌{RESET} {name}")
        print(f"     {DIM}→ {e}{RESET}")
        failed += 1
        errors.append((name, str(e)))
    except Exception as e:
        print(f"  {RED}💥{RESET} {name}")
        print(f"     {DIM}→ {type(e).__name__}: {e}{RESET}")
        failed += 1
        errors.append((name, f"{type(e).__name__}: {e}"))

def run_jovas(source):
    """Run Jovas source and capture output."""
    from jovas_modules import get_modules
    outputs = []

    # Patch print to capture output
    import run as _  # ensure jovas.jo loaded
    import importlib.util
    spec   = importlib.util.spec_from_file_location("jovas_engine",
               os.path.join(os.path.dirname(__file__), "jovas.jo"))
    engine = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(engine)

    captured = []
    interp = engine.Interpreter()
    original_print = interp.genv.get("print")
    interp.genv.set("print", lambda a: captured.append(
        " ".join(str(interp._display(x)) for x in a)
    ))
    interp.run(source)
    return captured

# ══════════════════════════════════════════════
print(f"\n{GOLD}{BOLD}  JOVAS LANGUAGE TEST SUITE{RESET}")
print(f"  {'─'*45}\n")

# ── SECTION 1: Lexer ──────────────────────────
print(f"{GOLD}  ▸ Lexer{RESET}")

def test_lexer_basic():
    from jovas.jo import Lexer, TT
    tokens = Lexer('let x = 42').tokenize()
    types  = [t.type for t in tokens if t.type != TT.EOF]
    assert TT.LET in types, "Missing LET token"
    assert TT.IDENTIFIER in types, "Missing IDENTIFIER token"
    assert TT.NUMBER in types, "Missing NUMBER token"

def test_lexer_string():
    from jovas.jo import Lexer, TT
    tokens = Lexer('"hello world"').tokenize()
    strs   = [t for t in tokens if t.type == TT.STRING]
    assert len(strs) == 1, "Expected 1 STRING token"
    assert strs[0].value == "hello world", f"Got {strs[0].value}"

def test_lexer_keywords():
    from jovas.jo import Lexer, TT, KEYWORDS
    source = "let const fn class if else for while return"
    tokens = Lexer(source).tokenize()
    token_types = {t.type for t in tokens}
    for kw in [TT.LET, TT.CONST, TT.FN, TT.CLASS, TT.IF, TT.FOR, TT.WHILE, TT.RETURN]:
        assert kw in token_types, f"Missing keyword token: {kw}"

def test_lexer_operators():
    from jovas.jo import Lexer, TT
    source = "== != <= >= && ||"
    tokens = Lexer(source).tokenize()
    types  = {t.type for t in tokens}
    for op in [TT.EQ_EQ, TT.BANG_EQ, TT.LT_EQ, TT.GT_EQ, TT.AND, TT.OR]:
        assert op in types, f"Missing operator: {op}"

def test_lexer_indent():
    from jovas.jo import Lexer, TT
    source = "fn greet()\n    return 1"
    tokens = Lexer(source).tokenize()
    types  = [t.type for t in tokens]
    assert TT.INDENT in types, "Missing INDENT token"
    assert TT.DEDENT in types, "Missing DEDENT token"

def test_lexer_comments():
    from jovas.jo import Lexer, TT
    source = "// this is a comment\nlet x = 1"
    tokens = Lexer(source).tokenize()
    types  = [t.type for t in tokens if t.type != TT.NEWLINE and t.type != TT.EOF]
    assert TT.LET in types, "Comment should be skipped"
    # No comment token should exist
    identifiers = [t for t in tokens if t.value == "comment"]
    assert len(identifiers) == 0, "Comment content leaked into tokens"

test("Lexer — basic tokens",    lambda: test_lexer_basic())
test("Lexer — string literal",  lambda: test_lexer_string())
test("Lexer — all keywords",    lambda: test_lexer_keywords())
test("Lexer — operators",       lambda: test_lexer_operators())
test("Lexer — indent/dedent",   lambda: test_lexer_indent())
test("Lexer — comments skipped",lambda: test_lexer_comments())

# ── SECTION 2: Parser ─────────────────────────
print(f"\n{GOLD}  ▸ Parser{RESET}")

def parse(source):
    from jovas.jo import Lexer, Parser
    return Parser(Lexer(source).tokenize()).parse()

def test_parser_varDecl():
    from jovas.jo import VarDecl
    ast = parse("let x = 42")
    assert len(ast.body) == 1
    assert isinstance(ast.body[0], VarDecl)
    assert ast.body[0].name == "x"

def test_parser_const():
    from jovas.jo import VarDecl
    ast = parse("const MAX = 100")
    node = ast.body[0]
    assert isinstance(node, VarDecl)
    assert node.constant == True
    assert node.name == "MAX"

def test_parser_function():
    from jovas.jo import FunctionDecl
    ast = parse("fn add(a, b)\n    return a")
    node = ast.body[0]
    assert isinstance(node, FunctionDecl)
    assert node.name == "add"
    assert len(node.params) == 2

def test_parser_async_fn():
    from jovas.jo import FunctionDecl
    ast = parse("async fn fetch(url)\n    return url")
    node = ast.body[0]
    assert isinstance(node, FunctionDecl)
    assert node.is_async == True

def test_parser_if():
    from jovas.jo import IfStmt
    ast = parse("if x > 0\n    print(x)")
    assert isinstance(ast.body[0], IfStmt)

def test_parser_for():
    from jovas.jo import ForStmt
    ast = parse("for item in items\n    print(item)")
    node = ast.body[0]
    assert isinstance(node, ForStmt)
    assert node.var == "item"

def test_parser_class():
    from jovas.jo import ClassDecl
    ast = parse("class Dog\n    fn init(name)\n        self.name = name")
    node = ast.body[0]
    assert isinstance(node, ClassDecl)
    assert node.name == "Dog"
    assert len(node.methods) == 1

def test_parser_try_catch():
    from jovas.jo import TryCatch
    ast = parse("try\n    let x = 1\ncatch err\n    print(err)")
    assert isinstance(ast.body[0], TryCatch)

def test_parser_match():
    from jovas.jo import MatchStmt
    ast = parse("match x\n    case \"a\" => print(1)")
    assert isinstance(ast.body[0], MatchStmt)

test("Parser — let declaration",  lambda: test_parser_varDecl())
test("Parser — const declaration", lambda: test_parser_const())
test("Parser — function decl",     lambda: test_parser_function())
test("Parser — async function",    lambda: test_parser_async_fn())
test("Parser — if statement",      lambda: test_parser_if())
test("Parser — for loop",          lambda: test_parser_for())
test("Parser — class declaration", lambda: test_parser_class())
test("Parser — try/catch",         lambda: test_parser_try_catch())
test("Parser — match statement",   lambda: test_parser_match())

# ── SECTION 3: Interpreter ────────────────────
print(f"\n{GOLD}  ▸ Interpreter{RESET}")

def interp_run(source):
    """Run source, return captured print output."""
    import importlib.util
    spec   = importlib.util.spec_from_file_location("jovas_engine",
               os.path.join(os.path.dirname(__file__), "jovas.jo"))
    engine = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(engine)
    captured = []
    interp = engine.Interpreter()
    interp.genv.set("print", lambda a: captured.append(
        " ".join(str(interp._display(x)) for x in a)
    ))
    interp.run(source.strip())
    return captured

def test_print():
    out = interp_run('print("hello")')
    assert out == ["hello"], f"Got {out}"

def test_arithmetic():
    out = interp_run("print(2 + 3)\nprint(10 - 4)\nprint(3 * 4)\nprint(10 / 2)")
    assert out[0] == "5", f"Add: {out[0]}"
    assert out[1] == "6", f"Sub: {out[1]}"
    assert out[2] == "12", f"Mul: {out[2]}"
    assert out[3] == "5.0", f"Div: {out[3]}"

def test_variables():
    out = interp_run('let x = 10\nlet y = 20\nprint(x + y)')
    assert out[0] == "30", f"Got {out[0]}"

def test_string_interpolation():
    out = interp_run('let name = "Jovas"\nprint("Hello, ${name}!")')
    assert out[0] == "Hello, Jovas!", f"Got {out[0]}"

def test_constants():
    out = interp_run('const PORT = 8080\nprint(PORT)')
    assert out[0] == "8080", f"Got {out[0]}"

def test_const_immutable():
    try:
        interp_run('const X = 1\nX = 2')
        assert False, "Should have raised an error"
    except Exception:
        pass  # expected

def test_if_else():
    out = interp_run('let x = 10\nif x > 5\n    print("big")\nelse\n    print("small")')
    assert out[0] == "big", f"Got {out[0]}"

def test_for_loop():
    out = interp_run('let total = 0\nfor n in [1, 2, 3, 4, 5]\n    total = total + n\nprint(total)')
    assert out[0] == "15", f"Got {out[0]}"

def test_while_loop():
    out = interp_run('let i = 0\nwhile i < 3\n    i = i + 1\nprint(i)')
    assert out[0] == "3", f"Got {out[0]}"

def test_repeat():
    out = interp_run('let c = 0\nrepeat 5\n    c = c + 1\nprint(c)')
    assert out[0] == "5", f"Got {out[0]}"

def test_function_call():
    out = interp_run('fn add(a, b)\n    return a + b\nprint(add(3, 7))')
    assert out[0] == "10", f"Got {out[0]}"

def test_recursion():
    out = interp_run('fn fact(n)\n    if n <= 1\n        return 1\n    return n * fact(n - 1)\nprint(fact(6))')
    assert out[0] == "720", f"Got {out[0]}"

def test_class():
    src = 'class Dog\n    fn init(name)\n        self.name = name\n    fn bark()\n        return self.name + " says Woof!"\nlet d = Dog("Rex")\nprint(d.bark())'
    out = interp_run(src)
    assert out[0] == "Rex says Woof!", f"Got {out[0]}"

def test_array():
    out = interp_run('let a = [1, 2, 3]\nprint(len(a))')
    assert out[0] == "3", f"Got {out[0]}"

def test_object():
    out = interp_run('let u = { name: "Alex", age: 25 }\nprint(u.name)')
    assert out[0] == "Alex", f"Got {out[0]}"

def test_null_safety():
    out = interp_run('let u = { profile: null }\nlet av = u?.profile?.avatar\nprint(av)')
    assert out[0] == "null", f"Got {out[0]}"

def test_try_catch():
    src = 'try\n    let x = 10\n    let y = 0\n    if y == 0\n        let boom = "error"\ncatch err\n    print("caught")'
    out = interp_run(src)
    # No crash = pass

def test_bool_logic():
    out = interp_run('print(true && false)\nprint(true || false)\nprint(!true)')
    assert out[0] == "false"
    assert out[1] == "true"
    assert out[2] == "false"

def test_string_ops():
    out = interp_run('let s = "Hello"\nprint(len(s))\nprint(str(42))\nprint(int("10") + 5)')
    assert out[0] == "5"
    assert out[1] == "42"
    assert out[2] == "15"

def test_pipeline():
    src = '''fn double(x)
    return x * 2
fn addTen(x)
    return x + 10
let result = 5 |> double |> addTen
print(result)'''
    out = interp_run(src)
    assert out[0] == "20", f"5*2+10=20, got {out[0]}"

test("Interpreter — print",              lambda: test_print())
test("Interpreter — arithmetic",         lambda: test_arithmetic())
test("Interpreter — variables",          lambda: test_variables())
test("Interpreter — string interpolation",lambda: test_string_interpolation())
test("Interpreter — constants",          lambda: test_constants())
test("Interpreter — const immutable",    lambda: test_const_immutable())
test("Interpreter — if/else",            lambda: test_if_else())
test("Interpreter — for loop",           lambda: test_for_loop())
test("Interpreter — while loop",         lambda: test_while_loop())
test("Interpreter — repeat",             lambda: test_repeat())
test("Interpreter — function call",      lambda: test_function_call())
test("Interpreter — recursion",          lambda: test_recursion())
test("Interpreter — class",              lambda: test_class())
test("Interpreter — array",              lambda: test_array())
test("Interpreter — object",             lambda: test_object())
test("Interpreter — null safety",        lambda: test_null_safety())
test("Interpreter — try/catch",          lambda: test_try_catch())
test("Interpreter — boolean logic",      lambda: test_bool_logic())
test("Interpreter — string builtins",    lambda: test_string_ops())
test("Interpreter — pipeline |>",        lambda: test_pipeline())

# ── SECTION 4: JovasDB ────────────────────────
print(f"\n{GOLD}  ▸ JovasDB{RESET}")

def test_db_connect():
    from jovas_modules import NativeDB
    db_mod = NativeDB()
    conn   = db_mod.connect(["test_ci"])
    assert conn is not None

def test_db_create_table():
    from jovas_modules import NativeDB
    conn = NativeDB().connect(["test_ci_tables"])
    conn.createTable(["items", [
        {"name":"id",   "type":"INTEGER","pk":True},
        {"name":"name", "type":"TEXT",   "nullable":False},
    ]])
    assert "items" in conn.tables

def test_db_insert_select():
    from jovas_modules import NativeDB
    conn = NativeDB().connect(["test_ci_crud"])
    conn.createTable(["vals",[{"name":"id","type":"INTEGER","pk":True},{"name":"v","type":"TEXT"}]])
    conn.insert(["vals",{"id":1,"v":"hello"}])
    conn.insert(["vals",{"id":2,"v":"world"}])
    rows = conn.select(["vals"])
    assert len(rows) == 2, f"Expected 2, got {len(rows)}"

def test_db_update():
    from jovas_modules import NativeDB
    conn = NativeDB().connect(["test_ci_upd"])
    conn.createTable(["u",[{"name":"id","type":"INTEGER","pk":True},{"name":"n","type":"TEXT"}]])
    conn.insert(["u",{"id":1,"n":"old"}])
    n = conn.update(["u",{"id":1},{"n":"new"}])
    assert n == 1
    row = conn.findOne(["u",{"id":1}])
    assert row["n"] == "new", f"Got {row['n']}"

def test_db_delete():
    from jovas_modules import NativeDB
    conn = NativeDB().connect(["test_ci_del"])
    conn.createTable(["d",[{"name":"id","type":"INTEGER","pk":True}]])
    conn.insert(["d",{"id":1}])
    conn.insert(["d",{"id":2}])
    n = conn.delete(["d",{"id":1}])
    assert n == 1
    assert conn.count(["d"]) == 1

def test_db_transaction_commit():
    from jovas_modules import NativeDB
    conn = NativeDB().connect(["test_ci_tx"])
    conn.createTable(["tx",[{"name":"id","type":"INTEGER","pk":True}]])
    tx = conn.begin()
    tx.insert(["tx",{"id":1}])
    tx.insert(["tx",{"id":2}])
    tx.commit()
    assert conn.count(["tx"]) == 2

def test_db_transaction_rollback():
    from jovas_modules import NativeDB
    conn = NativeDB().connect(["test_ci_rb"])
    conn.createTable(["rb",[{"name":"id","type":"INTEGER","pk":True}]])
    tx = conn.begin()
    tx.insert(["rb",{"id":1}])
    tx.rollback()
    assert conn.count(["rb"]) == 0

def test_db_nlq():
    from jovas_modules import NativeDB
    conn = NativeDB().connect(["test_ci_nlq"])
    conn.createTable(["users",[
        {"name":"id","type":"INTEGER","pk":True},
        {"name":"name","type":"TEXT"},
        {"name":"role","type":"TEXT"},
        {"name":"active","type":"BOOLEAN","default":True}
    ]])
    conn.insert(["users",{"id":1,"name":"Alice","role":"admin","active":True}])
    conn.insert(["users",{"id":2,"name":"Bob","role":"user","active":False}])
    rows = conn.ask(["find all active users"])
    assert len(rows) >= 1, f"NLQ returned {len(rows)} rows"

test("JovasDB — connect",              lambda: test_db_connect())
test("JovasDB — createTable",          lambda: test_db_create_table())
test("JovasDB — insert & select",      lambda: test_db_insert_select())
test("JovasDB — update",               lambda: test_db_update())
test("JovasDB — delete",               lambda: test_db_delete())
test("JovasDB — transaction commit",   lambda: test_db_transaction_commit())
test("JovasDB — transaction rollback", lambda: test_db_transaction_rollback())
test("JovasDB — natural language",     lambda: test_db_nlq())

# ── SECTION 5: Security Module ────────────────
print(f"\n{GOLD}  ▸ Security Module{RESET}")

def test_password_hash():
    from jovas_modules import SecurityModule
    s = SecurityModule()
    h = s.hash(["mysecret"])
    assert h.startswith("$jvt$"), f"Bad hash prefix: {h[:10]}"
    assert s.verify(["mysecret", h]) == True
    assert s.verify(["wrongpass", h]) == False

def test_jwt():
    from jovas_modules import SecurityModule
    s = SecurityModule()
    token = s.jwtSign([{"userId":1}, "secret", 3600])
    assert token.count(".") == 2, "JWT should have 3 parts"
    result = s.jwtVerify([token, "secret"])
    assert result["valid"] == True
    assert result["payload"]["userId"] == 1

def test_validation():
    from jovas_modules import SecurityModule
    s = SecurityModule()
    ok  = s.validate([{"email":"a@b.com","age":25},{"email":{"required":True,"type":"email"},"age":{"min":18}}])
    bad = s.validate([{"email":"notanemail","age":10},{"email":{"type":"email"},"age":{"min":18}}])
    assert ok["valid"]  == True,  f"Valid input failed: {ok}"
    assert bad["valid"] == False, f"Invalid input passed: {bad}"

def test_roles():
    from jovas_modules import SecurityModule
    s = SecurityModule()
    s.defineRole(["admin",["read","write","delete"]])
    s.defineRole(["user", ["read"]])
    assert s.permit([{"id":1,"role":"admin"},"delete"]) == True
    assert s.permit([{"id":2,"role":"user"},"delete"])  == False

test("Security — password hash/verify", lambda: test_password_hash())
test("Security — JWT sign/verify",      lambda: test_jwt())
test("Security — input validation",     lambda: test_validation())
test("Security — role permissions",     lambda: test_roles())

# ── SECTION 6: Email Module ───────────────────
print(f"\n{GOLD}  ▸ Email Module{RESET}")

def test_email_send():
    from jovas_modules import EmailModule
    em = EmailModule()
    result = em.send([{"to":"test@example.com","subject":"Test","body":"Hello!"}])
    assert result is not None
    assert result.get("status") in ("logged","sent")

def test_email_template():
    from jovas_modules import EmailModule
    em = EmailModule()
    r = em.template(["welcome",{"name":"Alex","app":"TestApp"}])
    assert r is not None
    assert "Alex" in r["body"]
    assert "TestApp" in r["body"]

def test_email_otp():
    from jovas_modules import EmailModule
    em = EmailModule()
    otp = em.otp([6])
    assert len(otp) == 6, f"OTP length: {len(otp)}"
    assert otp.isdigit(), f"OTP not numeric: {otp}"

test("Email — send (dev mode)",  lambda: test_email_send())
test("Email — template render",  lambda: test_email_template())
test("Email — OTP generation",   lambda: test_email_otp())

# ── SECTION 7: Linter ─────────────────────────
print(f"\n{GOLD}  ▸ Linter{RESET}")

def test_lint_clean():
    from jovas_modules import JovasLinter
    r = JovasLinter().check(["let x = 1\nprint(x)"])
    assert r["errors"] == 0, f"Clean code had errors: {r['issues']}"

def test_lint_const_reassign():
    from jovas_modules import JovasLinter
    r = JovasLinter().check(["const X = 1\nX = 2"])
    assert r["errors"] >= 1, "Should catch const reassignment"

def test_lint_div_zero():
    from jovas_modules import JovasLinter
    r = JovasLinter().check(["let x = 10 / 0"])
    assert r["errors"] >= 1, "Should catch division by zero"

def test_lint_unreachable():
    from jovas_modules import JovasLinter
    r = JovasLinter().check(["fn f()\n    return 1\n    print(\"dead\")"])
    assert r["errors"] >= 1, "Should catch unreachable code"

test("Linter — clean code passes",        lambda: test_lint_clean())
test("Linter — const reassignment",       lambda: test_lint_const_reassign())
test("Linter — division by zero",         lambda: test_lint_div_zero())
test("Linter — unreachable code",         lambda: test_lint_unreachable())

# ── RESULTS ───────────────────────────────────
total = passed + failed
print(f"\n  {'─'*45}")
print(f"  {GOLD}{BOLD}Results:{RESET}  {GREEN}{passed} passed{RESET}  ·  {RED if failed else DIM}{failed} failed{RESET}  ·  {total} total")

if errors:
    print(f"\n  {RED}Failed tests:{RESET}")
    for name, err in errors:
        print(f"  {DIM}  • {name}{RESET}")
        print(f"  {DIM}    {err}{RESET}")

pct = int(passed / total * 100) if total else 0
bar = "█" * (pct // 5) + "░" * (20 - pct // 5)
print(f"\n  [{GOLD}{bar}{RESET}] {pct}%\n")

if failed > 0:
    sys.exit(1)
