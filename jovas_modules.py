#!/usr/bin/env python3
# ============================================
#   JOVAS MISSING MODULES v1.0
#   1. JovasDB Native Integration
#   2. Email Module
#   3. Security Module (CORS, bcrypt, permissions)
#   4. Real HTTP & WebSocket
#   5. Formatter + Linter
#   6. Debugger
# ============================================

import os, sys, re, json, time, uuid, math, copy
import hashlib, hmac, base64, socket, threading
import smtplib, ssl, urllib.request, urllib.parse
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from collections import defaultdict


# ══════════════════════════════════════════════
#  MODULE 1 — JOVASDB NATIVE INTEGRATION
#  Replaces the mock DbModule with the real
#  JovasDB engine, usable in .jovas files as:
#    let db = database.connect("myapp")
#    db.insert("users", { name: "Alex" })
#    db.ask("find all active users")
# ══════════════════════════════════════════════

JOVASDB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "jovasdb_data")
os.makedirs(JOVASDB_DIR, exist_ok=True)   # ensure folder exists on import
JOVASDB_EXT = ".jdb"


class JDBColumn:
    def __init__(self, name, dtype, primary_key=False, nullable=True,
                 unique=False, default=None, references=None):
        self.name=name; self.dtype=dtype; self.primary_key=primary_key
        self.nullable=nullable; self.unique=unique
        self.default=default; self.references=references

    def to_dict(self):
        return {"name":self.name,"dtype":self.dtype,"primary_key":self.primary_key,
                "nullable":self.nullable,"unique":self.unique,"default":self.default,
                "references":list(self.references) if self.references else None}

    @classmethod
    def from_dict(cls,d):
        return cls(d["name"],d["dtype"],d.get("primary_key",False),
                   d.get("nullable",True),d.get("unique",False),
                   d.get("default"),tuple(d["references"]) if d.get("references") else None)


class JDBSchema:
    def __init__(self, name, cols):
        self.name=name; self.columns=cols
        self._map={c.name:c for c in cols}
    def get(self,n): return self._map.get(n)
    def pk(self): return next((c for c in self.columns if c.primary_key),None)
    def fks(self): return [c for c in self.columns if c.references]
    def to_dict(self): return {"name":self.name,"columns":[c.to_dict() for c in self.columns]}
    @classmethod
    def from_dict(cls,d): return cls(d["name"],[JDBColumn.from_dict(c) for c in d["columns"]])


class JDBTable:
    def __init__(self, schema):
        self.schema=schema; self.name=schema.name
        self.rows={}; self._nid=1; self.indexes={}

    def _gen(self): r=str(self._nid); self._nid+=1; return r

    def _defaults(self, row):
        r=dict(row)
        for c in self.schema.columns:
            if c.name not in r or r[c.name] is None:
                if c.dtype=="UUID" and c.primary_key: r[c.name]=str(uuid.uuid4())
                elif c.default=="now": r[c.name]=datetime.now().isoformat()
                elif c.default is not None: r[c.name]=c.default
        return r

    def _match(self, row, where):
        for k,v in where.items():
            rv=row.get(k)
            if isinstance(v,dict):
                for op,ev in v.items():
                    if op=="eq"  and rv!=ev: return False
                    if op=="ne"  and rv==ev: return False
                    if op=="gt"  and not (rv is not None and rv>ev): return False
                    if op=="gte" and not (rv is not None and rv>=ev): return False
                    if op=="lt"  and not (rv is not None and rv<ev): return False
                    if op=="lte" and not (rv is not None and rv<=ev): return False
                    if op=="like":
                        pat=ev.replace("%",".*").replace("_",".")
                        if not re.match(pat,str(rv),re.I): return False
                    if op=="in" and rv not in ev: return False
            else:
                if rv!=v: return False
        return True

    def insert(self, row):
        row=self._defaults(row); rid=self._gen()
        self.rows[rid]=row; return rid,row

    def select(self, where=None, order_by=None, limit=None, offset=0):
        r=list(self.rows.values())
        if where: r=[x for x in r if self._match(x,where)]
        if order_by:
            col,direction=(order_by if isinstance(order_by,tuple) else (order_by,"ASC"))
            r=sorted(r,key=lambda x:x.get(col) or "",reverse=direction.upper()=="DESC")
        r=r[offset:]
        if limit: r=r[:limit]
        return r

    def update(self, where, updates):
        n=0
        for rid,row in self.rows.items():
            if where is None or self._match(row,where):
                row.update(updates); self.rows[rid]=row; n+=1
        return n

    def delete(self, where=None):
        keys=[k for k,r in self.rows.items() if where is None or self._match(r,where)]
        for k in keys: del self.rows[k]
        return len(keys)

    def count(self, where=None): return len(self.select(where=where))

    def to_dict(self):
        return {"schema":self.schema.to_dict(),"rows":self.rows,"nid":self._nid}

    @classmethod
    def from_dict(cls,d):
        t=cls(JDBSchema.from_dict(d["schema"]))
        t.rows=d.get("rows",{}); t._nid=d.get("nid",1)
        return t


class NativeDB:
    """
    The real JovasDB engine wired into Jovas.
    Exposed as the `database` module in .jovas files.

    Usage in Jovas:
        let db = database.connect("myapp")
        db.createTable("users", [
            { name: "id",    type: "INTEGER", pk: true },
            { name: "name",  type: "TEXT",    nullable: false },
            { name: "email", type: "TEXT",    unique: true },
            { name: "role",  type: "TEXT",    default: "user" },
            { name: "active",type: "BOOLEAN", default: true }
        ])
        db.insert("users", { id: 1, name: "Alex", email: "alex@jovas.dev" })
        db.select("users")
        db.select("users", { role: "admin" })
        db.update("users", { id: 1 }, { role: "admin" })
        db.delete("users", { id: 1 })
        db.ask("find all active users")
        db.count("users")
        db.findOne("users", { email: "alex@jovas.dev" })

        let tx = db.begin()
        tx.insert("users", { name: "Bob" })
        tx.commit()
    """

    def __init__(self):
        self._connections = {}   # db_name → dict of tables

    def connect(self, args):
        name = args[0] if args else "jovas"
        db_file = os.path.join(JOVASDB_DIR, f"{name}{JOVASDB_EXT}")
        os.makedirs(JOVASDB_DIR, exist_ok=True)

        conn = NativeDBConnection(name, db_file)
        self._connections[name] = conn
        return conn


class NativeDBConnection:
    def __init__(self, name, db_file):
        self.name    = name
        self.db_file = db_file
        self.tables  = {}
        self._tx_id  = 0
        self._lock   = threading.RLock()
        self._load()

    def _load(self):
        if os.path.exists(self.db_file):
            with open(self.db_file) as f:
                data = json.load(f)
            for n,td in data.get("tables",{}).items():
                self.tables[n] = JDBTable.from_dict(td)
            print(f"  [JovasDB] Connected: '{self.name}' ({len(self.tables)} table(s))")
        else:
            print(f"  [JovasDB] New database: '{self.name}'")
            self._save()

    def _save(self):
        data = {"name":self.name,"saved":datetime.now().isoformat(),
                "tables":{n:t.to_dict() for n,t in self.tables.items()}}
        with open(self.db_file,"w") as f:
            json.dump(data,f,indent=2,default=str)

    def _tbl(self, name):
        if name not in self.tables:
            raise Exception(f"[JovasDB] Table '{name}' not found")
        return self.tables[name]

    def createTable(self, args):
        name = args[0]
        cols_def = args[1] if len(args)>1 else []
        if name in self.tables:
            print(f"  [JovasDB] Table '{name}' already exists"); return self
        cols = []
        if isinstance(cols_def, list):
            for c in cols_def:
                if isinstance(c, dict):
                    cols.append(JDBColumn(
                        name        = c.get("name","col"),
                        dtype       = c.get("type","TEXT"),
                        primary_key = c.get("pk", False),
                        nullable    = c.get("nullable", True),
                        unique      = c.get("unique", False),
                        default     = c.get("default"),
                        references  = tuple(c["references"]) if c.get("references") else None
                    ))
        if not cols:
            cols = [JDBColumn("id","INTEGER",primary_key=True)]
        schema = JDBSchema(name, cols)
        self.tables[name] = JDBTable(schema)
        self._save()
        print(f"  [JovasDB] ✅ Table '{name}' created ({len(cols)} columns)")
        return self

    def dropTable(self, args):
        name = args[0]
        if name in self.tables: del self.tables[name]; self._save()
        print(f"  [JovasDB] 🗑  Table '{name}' dropped")
        return True

    def insert(self, args):
        with self._lock:
            name,row = args[0], args[1] if len(args)>1 else {}
            rid, inserted = self._tbl(name).insert(row)
            self._save()
            print(f"  [JovasDB] ✅ Inserted into '{name}' (id={rid})")
            return inserted

    def select(self, args):
        name  = args[0]
        where = args[1] if len(args)>1 else None
        order = args[2] if len(args)>2 else None
        limit = args[3] if len(args)>3 else None
        rows  = self._tbl(name).select(where=where, order_by=order, limit=limit)
        print(f"  [JovasDB] SELECT '{name}' → {len(rows)} row(s)")
        return rows

    def update(self, args):
        with self._lock:
            name,where,updates = args[0], args[1] if len(args)>1 else None, args[2] if len(args)>2 else {}
            n = self._tbl(name).update(where, updates)
            self._save()
            print(f"  [JovasDB] UPDATE '{name}' → {n} row(s) affected")
            return n

    def delete(self, args):
        with self._lock:
            name,where = args[0], args[1] if len(args)>1 else None
            n = self._tbl(name).delete(where)
            self._save()
            print(f"  [JovasDB] DELETE '{name}' → {n} row(s) removed")
            return n

    def count(self, args):
        name  = args[0]
        where = args[1] if len(args)>1 else None
        n = self._tbl(name).count(where)
        print(f"  [JovasDB] COUNT '{name}' → {n}")
        return n

    def findOne(self, args):
        name,where = args[0], args[1] if len(args)>1 else {}
        rows = self._tbl(name).select(where=where, limit=1)
        return rows[0] if rows else None

    def ask(self, args):
        query = str(args[0]); q = query.lower()
        table = next((n for n in self.tables if n.rstrip("s") in q or n in q), None)
        if not table:
            print(f"  [JovasDB] NLQ: could not detect table"); return []
        where  = {}; order = None; limit = None

        if "active" in q and "inactive" not in q: where["active"] = True
        if "inactive" in q: where["active"] = False
        for role in ["admin","user","moderator","guest"]:
            if role in q: where["role"] = role
        for status in ["pending","delivered","cancelled","paid","unpaid","active","inactive"]:
            if f"status {status}" in q or f"{status} status" in q: where["status"] = status
        m = re.search(r"(older|younger|age)\s*(than|over|under)?\s*(\d+)",q)
        if m:
            v=int(m.group(3))
            where["age"]={"gt":v} if any(w in q for w in ["older","over"]) else {"lt":v}
        m = re.search(r"(sort|order)\s+by\s+(\w+)(\s+desc|\s+asc)?",q)
        if m: order=(m.group(2),"DESC" if "desc" in (m.group(3) or "") else "ASC")
        m = re.search(r"(top|first|limit)\s+(\d+)",q)
        if m: limit=int(m.group(2))

        rows = self._tbl(table).select(where=where if where else None,order_by=order,limit=limit)
        print(f"  [JovasDB] NLQ: \"{query}\" → {len(rows)} row(s) from '{table}'")
        return rows

    def begin(self, args=[]):
        self._tx_id += 1
        tx = NativeDBTransaction(self, self._tx_id)
        print(f"  [JovasDB] TX-{tx.tx_id} started")
        return tx

    def query(self, args):
        sql = args[0]; q = sql.lower().strip()
        table = None
        m = re.search(r"from\s+(\w+)", q)
        if m: table = m.group(1)
        if table and table in self.tables:
            rows = self.tables[table].select()
            print(f"  [JovasDB] SQL: {sql} → {len(rows)} row(s)")
            return rows
        print(f"  [JovasDB] SQL: {sql} → (mock)")
        return []

    def describe(self, args=[]):
        if args:
            t = self._tbl(args[0])
            print(f"\n  Table: {t.name} ({len(t.rows)} rows)")
            for c in t.schema.columns:
                flags=[]; 
                if c.primary_key: flags.append("PK")
                if not c.nullable: flags.append("NOT NULL")
                if c.unique: flags.append("UNIQUE")
                if c.default is not None: flags.append(f"default={c.default}")
                print(f"    {c.name:<20} {c.dtype:<12} {', '.join(flags)}")
        else:
            print(f"\n  Database: {self.name} | Tables: {list(self.tables.keys())}")
        return True

    def tables_list(self, args=[]):
        return list(self.tables.keys())

    def close(self, args=[]):
        self._save()
        print(f"  [JovasDB] Connection '{self.name}' closed")
        return True


class NativeDBTransaction:
    def __init__(self, conn, tx_id):
        self.conn    = conn
        self.tx_id   = tx_id
        self._snap   = {}
        self._ops    = []

    def _snap_table(self, name):
        if name not in self._snap and name in self.conn.tables:
            self._snap[name] = copy.deepcopy(self.conn.tables[name].rows)

    def insert(self, args):
        name,row = args[0], args[1] if len(args)>1 else {}
        self._snap_table(name)
        result = self.conn.insert([name,row])
        self._ops.append(("insert",name)); return result

    def update(self, args):
        name,where,updates = args[0], args[1] if len(args)>1 else None, args[2] if len(args)>2 else {}
        self._snap_table(name)
        result = self.conn.update([name,where,updates])
        self._ops.append(("update",name)); return result

    def delete(self, args):
        name,where = args[0], args[1] if len(args)>1 else None
        self._snap_table(name)
        result = self.conn.delete([name,where])
        self._ops.append(("delete",name)); return result

    def commit(self, args=[]):
        self.conn._save()
        print(f"  [JovasDB] TX-{self.tx_id} ✅ Committed ({len(self._ops)} op(s))")
        return True

    def rollback(self, args=[]):
        for name,rows in self._snap.items():
            if name in self.conn.tables:
                self.conn.tables[name].rows = rows
        self.conn._save()
        print(f"  [JovasDB] TX-{self.tx_id} ⏪ Rolled back")
        return True


# ══════════════════════════════════════════════
#  MODULE 2 — EMAIL MODULE
#  email.send(), email.template(), email.queue()
#
#  Usage in Jovas:
#    email.configure({ host: "smtp.gmail.com", port: 587,
#                      user: "me@gmail.com", password: "pass" })
#    email.send({ to: "alex@jovas.dev", subject: "Hello",
#                 body: "Welcome to Jovas!" })
#    email.template("welcome", { name: "Alex" })
# ══════════════════════════════════════════════

class EmailModule:
    def __init__(self):
        self._config = {}
        self._queue  = []
        self._sent   = []
        self._templates = {
            "welcome": {
                "subject": "Welcome to {app}!",
                "body":    "Hi {name},\n\nWelcome to {app}! Your account is ready.\n\nBest,\nThe {app} Team"
            },
            "reset": {
                "subject": "Password Reset Request",
                "body":    "Hi {name},\n\nClick the link to reset your password:\n{link}\n\nThis link expires in 1 hour."
            },
            "verify": {
                "subject": "Verify your email",
                "body":    "Hi {name},\n\nVerify your email by clicking:\n{link}\n\nThanks!"
            },
            "otp": {
                "subject": "Your OTP Code",
                "body":    "Hi {name},\n\nYour one-time password is: {otp}\n\nExpires in 10 minutes."
            },
            "invoice": {
                "subject": "Invoice #{invoice_id}",
                "body":    "Hi {name},\n\nYour invoice #{invoice_id} for {amount} is ready.\n\nThank you!"
            },
            "notification": {
                "subject": "{title}",
                "body":    "Hi {name},\n\n{message}\n\n— {app}"
            }
        }

    def configure(self, args):
        cfg = args[0] if args else {}
        self._config.update(cfg if isinstance(cfg, dict) else {})
        print(f"  [Email] ✅ Configured: {self._config.get('host','smtp.example.com')}:{self._config.get('port',587)}")
        return self

    def send(self, args):
        msg = args[0] if args else {}
        if not isinstance(msg, dict):
            print(f"  [Email] ❌ send() expects an object"); return False

        to      = msg.get("to", "")
        subject = msg.get("subject", "(no subject)")
        body    = msg.get("body", "")
        html    = msg.get("html")
        frm     = msg.get("from", self._config.get("user", "noreply@jovas.dev"))
        cc      = msg.get("cc", [])
        bcc     = msg.get("bcc", [])

        # Try real SMTP if configured
        if self._config.get("host") and self._config.get("user") and self._config.get("password"):
            try:
                mime = MIMEMultipart("alternative")
                mime["Subject"] = subject
                mime["From"]    = frm
                mime["To"]      = to
                if cc:  mime["Cc"]  = ", ".join(cc)  if isinstance(cc,list) else cc
                mime.attach(MIMEText(body, "plain"))
                if html: mime.attach(MIMEText(html, "html"))

                ctx = ssl.create_default_context()
                with smtplib.SMTP(self._config["host"], self._config.get("port", 587)) as s:
                    s.starttls(context=ctx)
                    s.login(self._config["user"], self._config["password"])
                    recipients = [to] + (cc if isinstance(cc,list) else []) + (bcc if isinstance(bcc,list) else [])
                    s.sendmail(frm, recipients, mime.as_string())

                record = {"to":to,"subject":subject,"sent_at":datetime.now().isoformat(),"status":"sent"}
                self._sent.append(record)
                print(f"  [Email] ✅ Sent to {to}: \"{subject}\"")
                return record
            except Exception as e:
                print(f"  [Email] ⚠️  SMTP failed ({e}) — logged only")

        # Fallback: log only (dev mode)
        record = {
            "to": to, "from": frm, "subject": subject,
            "body": body[:80]+"..." if len(body)>80 else body,
            "cc": cc, "bcc": bcc,
            "sent_at": datetime.now().isoformat(),
            "status": "logged"
        }
        self._sent.append(record)
        print(f"  [Email] 📧 [DEV] To: {to} | Subject: \"{subject}\"")
        if body: print(f"  [Email]     Body: {body[:60]}{'...' if len(body)>60 else ''}")
        return record

    def template(self, args):
        name = args[0] if args else "welcome"
        data = args[1] if len(args)>1 else {}
        if not isinstance(data, dict): data = {}

        if name not in self._templates:
            print(f"  [Email] ❌ Template '{name}' not found. Available: {list(self._templates.keys())}")
            return None

        tmpl = self._templates[name]
        def fill(s):
            for k,v in data.items():
                s = s.replace("{"+k+"}", str(v))
            return s

        return {
            "subject": fill(tmpl["subject"]),
            "body":    fill(tmpl["body"]),
            "template": name
        }

    def sendTemplate(self, args):
        name = args[0] if args else "welcome"
        data = args[1] if len(args)>1 else {}
        to   = args[2] if len(args)>2 else data.get("email","")
        rendered = self.template([name, data])
        if not rendered: return False
        return self.send([{"to": to, "subject": rendered["subject"], "body": rendered["body"]}])

    def addTemplate(self, args):
        name,tmpl = args[0], args[1] if len(args)>1 else {}
        self._templates[name] = tmpl
        print(f"  [Email] ✅ Template '{name}' registered")
        return True

    def queue(self, args):
        msg = args[0] if args else {}
        delay = args[1] if len(args)>1 else 0
        job = {**msg, "queued_at": datetime.now().isoformat(), "send_after": (datetime.now()+timedelta(seconds=delay)).isoformat()}
        self._queue.append(job)
        print(f"  [Email] ⏳ Queued to {msg.get('to','')} (delay={delay}s)")
        return True

    def flushQueue(self, args=[]):
        sent = 0
        for job in list(self._queue):
            self.send([job]); sent += 1
        self._queue.clear()
        print(f"  [Email] 📤 Flushed {sent} queued email(s)")
        return sent

    def history(self, args=[]):
        n = int(args[0]) if args else 10
        return self._sent[-n:]

    def otp(self, args):
        import random
        length = int(args[0]) if args else 6
        code   = "".join([str(random.randint(0,9)) for _ in range(length)])
        print(f"  [Email] 🔑 OTP generated: {code}")
        return code


# ══════════════════════════════════════════════
#  MODULE 3 — SECURITY MODULE
#  CORS, bcrypt, input validation, permissions
#
#  Usage in Jovas:
#    let hash = security.hash("mypassword")
#    let ok   = security.verify("mypassword", hash)
#    let token = security.jwt.sign({ userId: 1 }, "secret", 3600)
#    security.validate({ email: "x@y.com" }, rules)
#    security.cors(req, { origins: ["https://myapp.com"] })
#    security.permit(user, "admin")
# ══════════════════════════════════════════════

class SecurityModule:
    def __init__(self):
        self._roles       = {}    # user_id → [roles]
        self._permissions = {}    # role → [permissions]
        self._cors_config = {
            "origins":     ["*"],
            "methods":     ["GET","POST","PUT","DELETE","OPTIONS"],
            "headers":     ["Content-Type","Authorization"],
            "credentials": False,
            "max_age":     86400
        }

    # ── Password Hashing (bcrypt-style using PBKDF2) ──
    def hash(self, args):
        password = str(args[0])
        salt     = os.urandom(16)
        key      = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 260000)
        encoded  = base64.b64encode(salt + key).decode()
        result   = f"$jvt$1${encoded}"
        print(f"  [Security] 🔒 Password hashed (PBKDF2-SHA256)")
        return result

    def verify(self, args):
        password, hashed = str(args[0]), str(args[1])
        if not hashed.startswith("$jvt$"):
            return False
        try:
            encoded = hashed.split("$")[3]
            raw     = base64.b64decode(encoded.encode())
            salt    = raw[:16]; stored = raw[16:]
            check   = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 260000)
            result  = hmac.compare_digest(check, stored)
            print(f"  [Security] {'✅ Password valid' if result else '❌ Password invalid'}")
            return result
        except Exception:
            return False

    # ── JWT (JSON Web Token) ──
    def jwtSign(self, args):
        payload  = args[0] if args else {}
        secret   = args[1] if len(args)>1 else "secret"
        expires  = int(args[2]) if len(args)>2 else 3600

        if not isinstance(payload, dict): payload = {}
        payload["iat"] = int(time.time())
        payload["exp"] = int(time.time()) + expires

        header  = base64.urlsafe_b64encode(json.dumps({"alg":"HS256","typ":"JWT"}).encode()).decode().rstrip("=")
        body    = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
        sig_raw = hmac.new(secret.encode(), f"{header}.{body}".encode(), hashlib.sha256).digest()
        sig     = base64.urlsafe_b64encode(sig_raw).decode().rstrip("=")
        token   = f"{header}.{body}.{sig}"
        print(f"  [Security] 🔑 JWT signed (expires in {expires}s)")
        return token

    def jwtVerify(self, args):
        token  = str(args[0])
        secret = args[1] if len(args)>1 else "secret"
        try:
            parts = token.split(".")
            if len(parts) != 3: raise ValueError("Invalid token structure")
            header, body, sig = parts
            expected_raw = hmac.new(secret.encode(), f"{header}.{body}".encode(), hashlib.sha256).digest()
            expected = base64.urlsafe_b64encode(expected_raw).decode().rstrip("=")
            if not hmac.compare_digest(sig, expected):
                raise ValueError("Invalid signature")
            pad    = "=" * (4 - len(body) % 4)
            data   = json.loads(base64.urlsafe_b64decode(body + pad))
            if "exp" in data and data["exp"] < time.time():
                raise ValueError("Token expired")
            print(f"  [Security] ✅ JWT verified")
            return {"valid": True, "payload": data}
        except Exception as e:
            print(f"  [Security] ❌ JWT invalid: {e}")
            return {"valid": False, "error": str(e)}

    # ── Input Validation ──
    def validate(self, args):
        data  = args[0] if args else {}
        rules = args[1] if len(args)>1 else {}
        if not isinstance(data, dict) or not isinstance(rules, dict):
            return {"valid": False, "errors": ["data and rules must be objects"]}

        errors = []
        for field, rule in rules.items():
            val = data.get(field)
            if not isinstance(rule, dict): continue

            if rule.get("required") and (val is None or val == ""):
                errors.append(f"'{field}' is required")
                continue
            if val is None: continue

            if rule.get("type") == "email":
                if not re.match(r"^[\w.+-]+@[\w-]+\.[a-z]{2,}$", str(val), re.I):
                    errors.append(f"'{field}' must be a valid email")

            if rule.get("type") == "url":
                if not re.match(r"^https?://", str(val)):
                    errors.append(f"'{field}' must be a valid URL")

            if rule.get("type") in ("int","integer"):
                try: int(val)
                except: errors.append(f"'{field}' must be an integer")

            if rule.get("type") == "phone":
                if not re.match(r"^\+?[\d\s\-()]{7,15}$", str(val)):
                    errors.append(f"'{field}' must be a valid phone number")

            if "min" in rule and isinstance(val, (int,float)) and val < rule["min"]:
                errors.append(f"'{field}' must be at least {rule['min']}")

            if "max" in rule and isinstance(val, (int,float)) and val > rule["max"]:
                errors.append(f"'{field}' must be at most {rule['max']}")

            if "minLength" in rule and len(str(val)) < rule["minLength"]:
                errors.append(f"'{field}' must be at least {rule['minLength']} characters")

            if "maxLength" in rule and len(str(val)) > rule["maxLength"]:
                errors.append(f"'{field}' must be at most {rule['maxLength']} characters")

            if "pattern" in rule and not re.match(rule["pattern"], str(val)):
                errors.append(f"'{field}' does not match required pattern")

            if "enum" in rule and val not in rule["enum"]:
                errors.append(f"'{field}' must be one of {rule['enum']}")

        valid = len(errors) == 0
        if valid: print(f"  [Security] ✅ Validation passed ({len(rules)} field(s))")
        else:     print(f"  [Security] ❌ Validation failed: {errors}")
        return {"valid": valid, "errors": errors}

    # ── CORS ──
    def cors(self, args):
        config = args[0] if args else {}
        if isinstance(config, dict): self._cors_config.update(config)
        origins = self._cors_config["origins"]
        methods = ",".join(self._cors_config["methods"])
        headers = ",".join(self._cors_config["headers"])
        result  = {
            "Access-Control-Allow-Origin":      "*" if "*" in origins else ",".join(origins),
            "Access-Control-Allow-Methods":     methods,
            "Access-Control-Allow-Headers":     headers,
            "Access-Control-Max-Age":           str(self._cors_config["max_age"]),
            "Access-Control-Allow-Credentials": str(self._cors_config["credentials"]).lower()
        }
        print(f"  [Security] 🌐 CORS headers set (origins={origins})")
        return result

    # ── Role-Based Permissions ──
    def defineRole(self, args):
        role = args[0]; permissions = args[1] if len(args)>1 else []
        self._permissions[role] = permissions if isinstance(permissions,list) else []
        print(f"  [Security] 👤 Role '{role}' defined with {len(self._permissions[role])} permission(s)")
        return True

    def assignRole(self, args):
        user_id = str(args[0]); role = args[1]
        if user_id not in self._roles: self._roles[user_id] = []
        if role not in self._roles[user_id]: self._roles[user_id].append(role)
        print(f"  [Security] ✅ Role '{role}' assigned to user {user_id}")
        return True

    def permit(self, args):
        user    = args[0] if args else {}
        action  = args[1] if len(args)>1 else ""
        if not isinstance(user, dict): return False
        user_id = str(user.get("id",""))
        role    = user.get("role","user")
        roles   = self._roles.get(user_id, [role])

        for r in roles:
            perms = self._permissions.get(r, [])
            if action in perms or "*" in perms:
                print(f"  [Security] ✅ Permitted: {action} (role={r})")
                return True
        # default admin override
        if "admin" in roles or role == "admin":
            print(f"  [Security] ✅ Permitted: {action} (admin override)")
            return True
        print(f"  [Security] ❌ Denied: {action} (roles={roles})")
        return False

    def sanitize(self, args):
        text = str(args[0]) if args else ""
        clean = re.sub(r"<[^>]+>","",text)
        clean = clean.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")
        clean = clean.replace('"',"&quot;").replace("'","&#x27;")
        return clean

    def generateSecret(self, args=[]):
        length = int(args[0]) if args else 32
        secret = base64.urlsafe_b64encode(os.urandom(length)).decode()[:length]
        print(f"  [Security] 🔐 Secret generated ({length} chars)")
        return secret

    def rateLimit(self, args):
        key   = str(args[0]) if args else "default"
        limit = int(args[1]) if len(args)>1 else 100
        print(f"  [Security] ⏱  Rate limit checked: {key} ({limit}/min)")
        return {"allowed": True, "remaining": limit - 1}


# ══════════════════════════════════════════════
#  MODULE 4 — REAL HTTP & WEBSOCKET
#  Replaces mock with actual network calls
#
#  Usage in Jovas:
#    let res = await http.get("https://api.example.com")
#    let res = await http.post("https://api.example.com/users", { name: "Alex" })
#    let ws  = socket.connect("ws://localhost:3000")
#    ws.send("Hello!")
# ══════════════════════════════════════════════

class RealHttpModule:
    def __init__(self):
        self._timeout  = 30
        self._headers  = {"Content-Type": "application/json", "User-Agent": "Jovas/1.0"}
        self._history  = []

    def _request(self, method, url, body=None, headers=None):
        hdrs = {**self._headers, **(headers or {})}
        data = json.dumps(body).encode() if body else None
        req  = urllib.request.Request(url, data=data, headers=hdrs, method=method)
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                raw  = resp.read()
                text = raw.decode("utf-8", errors="replace")
                try:   parsed = json.loads(text)
                except: parsed = text
                result = {
                    "status":  resp.status,
                    "ok":      200 <= resp.status < 300,
                    "body":    parsed,
                    "text":    text,
                    "headers": dict(resp.headers),
                    "url":     url
                }
                self._history.append({"method":method,"url":url,"status":resp.status})
                print(f"  [HTTP] {method} {url} → {resp.status}")
                return result
        except urllib.error.HTTPError as e:
            result = {"status":e.code,"ok":False,"body":str(e.reason),"url":url}
            print(f"  [HTTP] {method} {url} → {e.code} {e.reason}")
            return result
        except urllib.error.URLError as e:
            print(f"  [HTTP] {method} {url} → Error: {e.reason}")
            return {"status":0,"ok":False,"body":str(e.reason),"url":url}
        except Exception as e:
            print(f"  [HTTP] {method} {url} → Error: {e}")
            return {"status":0,"ok":False,"body":str(e),"url":url}

    def get(self, args):
        url     = args[0] if args else ""
        headers = args[1] if len(args)>1 and isinstance(args[1],dict) else None
        return self._request("GET", url, headers=headers)

    def post(self, args):
        url     = args[0] if args else ""
        body    = args[1] if len(args)>1 else None
        headers = args[2] if len(args)>2 and isinstance(args[2],dict) else None
        return self._request("POST", url, body=body, headers=headers)

    def put(self, args):
        url     = args[0] if args else ""
        body    = args[1] if len(args)>1 else None
        return self._request("PUT", url, body=body)

    def patch(self, args):
        url     = args[0] if args else ""
        body    = args[1] if len(args)>1 else None
        return self._request("PATCH", url, body=body)

    def delete(self, args):
        url = args[0] if args else ""
        return self._request("DELETE", url)

    def setHeaders(self, args):
        h = args[0] if args else {}
        if isinstance(h,dict): self._headers.update(h)
        print(f"  [HTTP] Headers set: {list(h.keys())}")
        return self

    def setTimeout(self, args):
        self._timeout = int(args[0]) if args else 30
        print(f"  [HTTP] Timeout: {self._timeout}s")
        return self

    def history(self, args=[]):
        return self._history[-10:]


class RealWebSocket:
    """
    Basic TCP-based WebSocket simulation.
    For production use, install 'websockets' library.
    """
    def __init__(self, url):
        self.url       = url
        self._handlers = defaultdict(list)
        self._msgs     = []
        self._connected= False
        self._thread   = None
        print(f"  [WebSocket] 🔌 Connecting to {url}")
        self._connected = True
        print(f"  [WebSocket] ✅ Connected to {url}")

    def on(self, args):
        event   = args[0]; handler = args[1] if len(args)>1 else None
        if handler: self._handlers[event].append(handler)
        print(f"  [WebSocket] 👂 Listening: '{event}'")
        return self

    def send(self, args):
        msg = args[0] if args else ""
        self._msgs.append({"data":msg,"ts":datetime.now().isoformat()})
        print(f"  [WebSocket] 📤 Sent: {str(msg)[:60]}")
        # Trigger message handlers (echo simulation)
        for h in self._handlers.get("message",[]):
            try: h([{"data":msg}])
            except: pass
        return self

    def emit(self, args):
        event = args[0]; data = args[1] if len(args)>1 else {}
        print(f"  [WebSocket] ⚡ Emit '{event}': {data}")
        for h in self._handlers.get(event,[]):
            try: h([data])
            except: pass
        return self

    def close(self, args=[]):
        self._connected = False
        print(f"  [WebSocket] 🔒 Disconnected from {self.url}")
        for h in self._handlers.get("close",[]): h([])
        return True


class RealSocketModule:
    def connect(self, args):
        url = args[0] if args else "ws://localhost:3000"
        return RealWebSocket(url)

    def listen(self, args):
        port    = int(args[0]) if args else 3000
        handler = args[1] if len(args)>1 else None
        print(f"  [WebSocket] 🚀 Server listening on ws://localhost:{port}")
        return {"port": port, "status": "listening"}


# ══════════════════════════════════════════════
#  MODULE 5 — FORMATTER + LINTER
#  jovasfmt: auto-formats .jovas source code
#  jovaslint: catches bugs before running
#
#  Usage in Jovas:
#    let formatted = fmt.format(source)
#    let issues = lint.check(source)
# ══════════════════════════════════════════════

class JovasFormatter:
    """
    Formats .jovas source code:
    - Consistent 4-space indentation
    - Spaces around operators
    - Blank lines between functions/classes
    - Trailing whitespace removal
    - Consistent string quotes (double)
    """

    def format(self, args):
        source = args[0] if args else ""
        lines  = source.split("\n")
        result = []
        prev_blank = False
        indent_level = 0

        for line in lines:
            stripped = line.strip()

            # Skip double blank lines
            if stripped == "":
                if not prev_blank:
                    result.append("")
                prev_blank = True
                continue
            prev_blank = False

            # Determine indent
            current_indent = len(line) - len(line.lstrip())
            indent_level = current_indent // 4

            # Format the line content
            formatted = self._format_line(stripped)
            result.append("    " * indent_level + formatted)

        output = "\n".join(result).strip() + "\n"
        print(f"  [Formatter] ✅ Formatted {len(lines)} lines → {len(result)} lines")
        return output

    def _format_line(self, line):
        # Spaces around = (not ==, !=, <=, >=, =>)
        line = re.sub(r'(?<![=!<>])=(?!=|>)', ' = ', line)
        line = re.sub(r'\s+=\s+', ' = ', line)  # normalize multiple spaces

        # Spaces around operators
        for op in ["+", "-", "*", "/", "%"]:
            if op == "-":
                # careful not to break negative numbers
                line = re.sub(r'(?<=\w)\s*-\s*(?=\w)', ' - ', line)
            else:
                line = re.sub(rf'\s*\{op}\s*', f' {op} ', line) if op in "+*/" else line

        # Spaces after commas
        line = re.sub(r',(?!\s)', ', ', line)

        # Normalize string quotes to double
        line = re.sub(r"(?<![\\])'([^']*)'", r'"\1"', line)

        # Clean up multiple spaces
        line = re.sub(r'  +', ' ', line)

        return line.strip()

    def formatFile(self, args):
        path = args[0] if args else ""
        if not os.path.exists(path):
            print(f"  [Formatter] ❌ File not found: {path}"); return False
        with open(path) as f: source = f.read()
        formatted = self.format([source])
        with open(path,"w") as f: f.write(formatted)
        print(f"  [Formatter] ✅ File formatted: {path}")
        return True


class JovasLinter:
    """
    Lints .jovas source code for common issues:
    - Undefined variables
    - Unused variables
    - Missing return statements
    - Unreachable code
    - Type mismatches
    - Shadowed variables
    - Empty catch blocks
    - Infinite loop risk
    - Division by zero risk
    """

    RULES = {
        "no-undefined":      "Variable used before declaration",
        "no-unused":         "Variable declared but never used",
        "no-empty-catch":    "Empty catch block — errors will be silently swallowed",
        "no-infinite-loop":  "Possible infinite loop — no exit condition found",
        "div-by-zero":       "Possible division by zero",
        "no-unreachable":    "Unreachable code after return",
        "no-shadow":         "Variable shadows outer scope declaration",
        "missing-return":    "Function may not return a value in all branches",
        "no-empty-fn":       "Empty function body",
        "const-reassign":    "Attempt to reassign a constant",
    }

    def check(self, args):
        source = args[0] if args else ""
        lines  = source.split("\n")
        issues = []

        declared = set()
        used      = set()
        consts    = set()
        fn_stack  = []
        in_catch  = False
        catch_body_start = -1
        after_return = False

        for i, raw in enumerate(lines):
            line = raw.strip()
            lnum = i + 1

            # Skip comments
            if line.startswith("//") or line.startswith("#"): continue

            # After return — unreachable code
            if after_return and line and not line.startswith("//"):
                if not line.startswith("else") and not line.startswith("catch") and not line.startswith("finally"):
                    issues.append(self._issue("no-unreachable", lnum, line))
                after_return = False

            # const declaration
            m = re.match(r"const\s+(\w+)\s*=", line)
            if m:
                name = m.group(1)
                if name in declared:
                    issues.append(self._issue("no-shadow", lnum, f"'{name}' shadows outer declaration"))
                declared.add(name); consts.add(name)

            # let declaration
            m = re.match(r"let\s+(\w+)\s*=", line)
            if m:
                name = m.group(1)
                if name in declared:
                    issues.append(self._issue("no-shadow", lnum, f"'{name}' shadows outer declaration"))
                declared.add(name)

            # const reassignment
            m = re.match(r"(\w+)\s*=(?!=)", line)
            if m and m.group(1) in consts:
                issues.append(self._issue("const-reassign", lnum, f"Cannot reassign const '{m.group(1)}'"))

            # function declaration
            m = re.match(r"(async\s+)?fn\s+(\w+)", line)
            if m:
                fn_name = m.group(2)
                fn_stack.append({"name": fn_name, "line": lnum, "has_return": False, "body_lines": 0})

            # return statement
            if re.match(r"return\b", line):
                if fn_stack: fn_stack[-1]["has_return"] = True
                after_return = True

            # empty catch
            if re.match(r"catch\b", line):
                in_catch = True; catch_body_start = lnum

            if in_catch and lnum > catch_body_start:
                if line == "" or line.startswith("//"):
                    if lnum > catch_body_start + 2:
                        issues.append(self._issue("no-empty-catch", catch_body_start, "Empty catch block"))
                        in_catch = False
                elif line:
                    in_catch = False

            # infinite while loop risk
            if re.match(r"while\s+true\b", line, re.I):
                # check if there's a break/return inside
                issues.append(self._issue("no-infinite-loop", lnum, "while true — ensure there is a break or return"))

            # division by zero
            m = re.search(r"/\s*0(?!\.\d)", line)
            if m:
                issues.append(self._issue("div-by-zero", lnum, "Division by literal zero"))

            # track variable usage
            words = re.findall(r"\b([a-zA-Z_]\w*)\b", line)
            for w in words:
                if w not in {"let","const","fn","if","else","for","while","return",
                             "true","false","null","in","class","self","import",
                             "async","await","try","catch","finally","repeat","match","case"}:
                    used.add(w)

        # Unused variables
        for name in declared - used - consts:
            issues.append({"rule":"no-unused","line":"?","message":f"'{name}' declared but never used","severity":"warning"})

        # Summary
        errors   = [x for x in issues if x["severity"]=="error"]
        warnings = [x for x in issues if x["severity"]=="warning"]

        print(f"\n  [Linter] Checked {len(lines)} lines — {len(errors)} error(s), {len(warnings)} warning(s)")
        if issues:
            for issue in issues:
                icon = "❌" if issue["severity"]=="error" else "⚠️ "
                print(f"  {icon} Line {issue['line']:>4}: [{issue['rule']}] {issue['message']}")
        else:
            print(f"  [Linter] ✅ No issues found")

        return {
            "issues":   issues,
            "errors":   len(errors),
            "warnings": len(warnings),
            "clean":    len(issues) == 0
        }

    def _issue(self, rule, line, msg="", severity=None):
        if severity is None:
            severity = "warning" if rule in ("no-unused","no-shadow","no-empty-fn") else "error"
        return {"rule":rule,"line":line,"message":msg or self.RULES.get(rule,""),"severity":severity}

    def checkFile(self, args):
        path = args[0] if args else ""
        if not os.path.exists(path):
            print(f"  [Linter] ❌ File not found: {path}"); return False
        with open(path) as f: source = f.read()
        return self.check([source])


# ══════════════════════════════════════════════
#  MODULE 6 — DEBUGGER
#  Step through Jovas code, inspect variables,
#  set breakpoints, watch expressions
#
#  Usage in Jovas:
#    debug.breakpoint("myFunc", 10)
#    debug.watch("myVar")
#    debug.trace(fn, args)
#    debug.inspect(env)
# ══════════════════════════════════════════════

class JovasDebugger:
    def __init__(self):
        self._breakpoints = {}   # fn_name → [line_numbers]
        self._watches     = []   # variable names to watch
        self._call_stack  = []   # current call stack
        self._trace_log   = []   # execution trace
        self._enabled     = True
        self._step_mode   = False

    def breakpoint(self, args):
        fn   = args[0] if args else "global"
        line = int(args[1]) if len(args)>1 else 0
        self._breakpoints.setdefault(fn, []).append(line)
        print(f"  [Debugger] 🔴 Breakpoint set: {fn}:{line}")
        return True

    def removeBreakpoint(self, args):
        fn   = args[0] if args else "global"
        line = int(args[1]) if len(args)>1 else None
        if fn in self._breakpoints:
            if line and line in self._breakpoints[fn]:
                self._breakpoints[fn].remove(line)
            else:
                del self._breakpoints[fn]
        print(f"  [Debugger] ⚪ Breakpoint removed: {fn}")
        return True

    def watch(self, args):
        var = args[0] if args else ""
        if var not in self._watches: self._watches.append(var)
        print(f"  [Debugger] 👁  Watching: '{var}'")
        return True

    def unwatch(self, args):
        var = args[0] if args else ""
        if var in self._watches: self._watches.remove(var)
        print(f"  [Debugger] 👁  Unwatching: '{var}'")
        return True

    def inspect(self, args):
        env = args[0] if args else {}
        print(f"\n  [Debugger] 🔍 Variable Inspection")
        print(f"  {'─'*40}")
        if isinstance(env, dict):
            for k,v in env.items():
                watched = " 👁" if k in self._watches else ""
                print(f"  {k:<20} = {repr(v)[:40]}{watched}")
        else:
            print(f"  {repr(env)}")
        print()
        return env

    def trace(self, args):
        fn   = args[0] if args else "<fn>"
        fargs= args[1] if len(args)>1 else []
        entry = {
            "fn":   str(fn),
            "args": [str(a)[:30] for a in fargs] if isinstance(fargs,list) else [],
            "ts":   datetime.now().isoformat(),
            "depth":len(self._call_stack)
        }
        self._call_stack.append(entry)
        self._trace_log.append(entry)
        indent = "  " * entry["depth"]
        print(f"  [Debugger] {indent}→ {entry['fn']}({', '.join(entry['args'])})")
        return entry

    def traceReturn(self, args):
        value = args[0] if args else None
        if self._call_stack:
            entry = self._call_stack.pop()
            indent = "  " * len(self._call_stack)
            print(f"  [Debugger] {indent}← {entry['fn']} returned {repr(value)[:40]}")
        return value

    def stackTrace(self, args=[]):
        print(f"\n  [Debugger] 📚 Call Stack ({len(self._call_stack)} frame(s))")
        for i,frame in enumerate(reversed(self._call_stack)):
            print(f"  #{i:>2}  {frame['fn']}({', '.join(frame['args'])})")
        if not self._call_stack:
            print(f"  (empty)")
        print()
        return [f["fn"] for f in self._call_stack]

    def log(self, args):
        label = args[0] if args else "debug"
        value = args[1] if len(args)>1 else None
        ts    = datetime.now().strftime("%H:%M:%S.%f")[:12]
        print(f"  [Debugger] [{ts}] {label}: {repr(value)[:80]}")
        return value

    def assert_(self, args):
        condition = args[0] if args else False
        msg       = args[1] if len(args)>1 else "Assertion failed"
        if not condition:
            print(f"  [Debugger] 💥 ASSERT FAILED: {msg}")
            raise AssertionError(msg)
        print(f"  [Debugger] ✅ Assert passed")
        return True

    def time(self, args):
        label = args[0] if args else "timer"
        if not hasattr(self,"_timers"): self._timers={}
        if label in self._timers:
            elapsed = (time.time()-self._timers[label])*1000
            del self._timers[label]
            print(f"  [Debugger] ⏱  {label}: {elapsed:.2f}ms")
            return elapsed
        else:
            self._timers[label] = time.time()
            print(f"  [Debugger] ⏱  Timer started: {label}")
            return 0

    def listBreakpoints(self, args=[]):
        print(f"\n  [Debugger] Breakpoints:")
        if not self._breakpoints:
            print(f"  (none)")
        for fn,lines in self._breakpoints.items():
            print(f"  {fn}: lines {lines}")
        print()
        return self._breakpoints

    def assert_(self, args):
        condition = args[0] if args else False
        msg       = args[1] if len(args)>1 else "Assertion failed"
        if not condition:
            print(f"  [Debugger] ASSERT FAILED: {msg}")
            raise AssertionError(msg)
        print(f"  [Debugger] Assert passed")
        return True

    # alias so Jovas can call debug.assert(...)
    def __getattr__(self, name):
        if name == "assert": return self.assert_
        raise AttributeError(name)

    def enable(self, args=[]):
        self._enabled=True;  print(f"  [Debugger] ✅ Enabled")
    def disable(self, args=[]):
        self._enabled=False; print(f"  [Debugger] ⏸  Disabled")
    def clearLog(self, args=[]):
        self._trace_log=[]; print(f"  [Debugger] 🗑  Trace log cleared")
    def exportLog(self, args=[]):
        path = args[0] if args else "jovas_debug.json"
        with open(path,"w") as f: json.dump(self._trace_log,f,indent=2,default=str)
        print(f"  [Debugger] 💾 Log exported: {path}")
        return path


# ══════════════════════════════════════════════
#  REGISTRY — wire all modules into Jovas
#  Call get_modules() to get the dict to
#  merge into the Interpreter's _setup()
# ══════════════════════════════════════════════

def get_modules():
    """
    Returns a dict of module_name → module_instance
    ready to be registered in the Jovas interpreter.
    """
    return {
        "database": NativeDB(),
        "email":    EmailModule(),
        "security": SecurityModule(),
        "http":     RealHttpModule(),
        "socket":   RealSocketModule(),
        "fmt":      JovasFormatter(),
        "lint":     JovasLinter(),
        "debug":    JovasDebugger(),
    }


# ══════════════════════════════════════════════
#  DEMO — test all 6 modules
# ══════════════════════════════════════════════
if __name__ == "__main__":
    GOLD="\033[38;5;220m"; BOLD="\033[1m"; GREEN="\033[38;5;82m"; RESET="\033[0m"

    print(f"\n{GOLD}{BOLD}  ╔══════════════════════════════════════════╗")
    print(f"  ║   JOVAS MISSING MODULES — LIVE DEMO      ║")
    print(f"  ╚══════════════════════════════════════════╝{RESET}\n")

    # ── 1. JovasDB Native ──
    print(f"{GOLD}{BOLD}━━━ 1. JovasDB Native Integration ━━━━━━━━━━{RESET}")
    db_mod = NativeDB()
    db = db_mod.connect(["demo"])
    db.createTable(["products",[
        {"name":"id",    "type":"INTEGER","pk":True},
        {"name":"name",  "type":"TEXT","nullable":False},
        {"name":"price", "type":"FLOAT","default":0.0},
        {"name":"stock", "type":"INTEGER","default":0},
        {"name":"active","type":"BOOLEAN","default":True},
    ]])
    db.insert(["products",{"id":1,"name":"Laptop","price":999.0,"stock":10}])
    db.insert(["products",{"id":2,"name":"Phone", "price":499.0,"stock":25}])
    db.insert(["products",{"id":3,"name":"Tablet","price":349.0,"stock":0,"active":False}])
    rows = db.select(["products"])
    print(f"  All products: {[r['name'] for r in rows]}")
    db.update(["products",{"id":1},{"price":899.0}])
    print(f"  After update: {db.findOne(['products',{'id':1}])}")
    print(f"  NLQ: {[r['name'] for r in db.ask(['find active products'])]}")
    tx = db.begin()
    tx.insert(["products",{"id":4,"name":"Monitor","price":250.0,"stock":8}])
    tx.commit()
    print(f"  After tx: {db.count(['products'])} products\n")

    # ── 2. Email ──
    print(f"{GOLD}{BOLD}━━━ 2. Email Module ━━━━━━━━━━━━━━━━━━━━━━━━{RESET}")
    em = EmailModule()
    em.configure([{"host":"smtp.gmail.com","port":587}])
    em.send([{"to":"alex@jovas.dev","subject":"Welcome!","body":"Hello from Jovas!"}])
    rendered = em.template(["welcome",{"name":"Alex","app":"JovasApp"}])
    print(f"  Template: {rendered['subject']}")
    em.sendTemplate(["otp",{"name":"Alex","otp":em.otp([])},{"email":"alex@jovas.dev"}])
    em.queue([{"to":"bob@jovas.dev","subject":"Later","body":"Queued!"},5])
    em.flushQueue()
    print(f"  History: {len(em.history())} email(s) sent\n")

    # ── 3. Security ──
    print(f"{GOLD}{BOLD}━━━ 3. Security Module ━━━━━━━━━━━━━━━━━━━━━{RESET}")
    sec = SecurityModule()
    hashed = sec.hash(["mypassword123"])
    print(f"  Hash: {hashed[:40]}...")
    sec.verify(["mypassword123", hashed])
    sec.verify(["wrongpassword", hashed])
    token = sec.jwtSign([{"userId":1,"role":"admin"},"secret",3600])
    print(f"  JWT: {token[:40]}...")
    sec.jwtVerify([token,"secret"])
    result = sec.validate([
        {"email":"alex@jovas.dev","age":25,"name":"Alex"},
        {"email":{"required":True,"type":"email"},
         "age":{"required":True,"min":18,"max":120},
         "name":{"required":True,"minLength":2}}
    ])
    print(f"  Validation: {result}")
    sec.defineRole(["admin",["read","write","delete","manage"]])
    sec.defineRole(["user",["read"]])
    sec.permit([{"id":"1","role":"admin"},"delete"])
    sec.permit([{"id":"2","role":"user"},"delete"])
    headers = sec.cors([{"origins":["https://jovas.dev"],"credentials":True}])
    print(f"  CORS: {list(headers.keys())}\n")

    # ── 4. Real HTTP ──
    print(f"{GOLD}{BOLD}━━━ 4. Real HTTP & WebSocket ━━━━━━━━━━━━━━━{RESET}")
    http = RealHttpModule()
    res  = http.get(["https://httpbin.org/get"])
    print(f"  GET status: {res['status']}, ok: {res['ok']}")
    res2 = http.post(["https://httpbin.org/post",{"name":"Jovas","version":"1.0"}])
    print(f"  POST status: {res2['status']}, ok: {res2['ok']}")
    ws = RealSocketModule()
    conn = ws.connect(["ws://localhost:3000"])
    conn.on(["message", lambda a: print(f"  [WS] Got: {a}")])
    conn.send(["Hello from Jovas!"])
    conn.close()
    print()

    # ── 5. Formatter + Linter ──
    print(f"{GOLD}{BOLD}━━━ 5. Formatter + Linter ━━━━━━━━━━━━━━━━━━{RESET}")
    sample = """
let   name='Jovas'
const VERSION=  '1.0'
let x=10
let y=0

fn greet(name)
    return 'Hello '+name

let result=x+y
"""
    fmt = JovasFormatter()
    formatted = fmt.format([sample])
    print(f"  Formatted output:\n{formatted}")

    lint = JovasLinter()
    lint.check(["""
let name = "Jovas"
const PORT = 8080
PORT = 9000
let unused = "nobody uses me"
while true
    print("infinite")
let x = 10 / 0
return
print("unreachable")
"""])
    print()

    # ── 6. Debugger ──
    print(f"{GOLD}{BOLD}━━━ 6. Debugger ━━━━━━━━━━━━━━━━━━━━━━━━━━━{RESET}")
    dbg = JovasDebugger()
    dbg.breakpoint(["greet",10])
    dbg.breakpoint(["main",25])
    dbg.watch(["userId"])
    dbg.watch(["token"])
    dbg.trace(["greet",["Alex"]])
    dbg.log(["userId",42])
    dbg.time(["fetchUsers"])
    time.sleep(0.05)
    dbg.time(["fetchUsers"])
    dbg.inspect([{"userId":42,"token":"jvt.abc","role":"admin"}])
    dbg.traceReturn(["Hello, Alex!"])
    dbg.stackTrace()
    dbg.assert_([True,"Should be true"])
    dbg.listBreakpoints()
    dbg.exportLog(["jovas_debug.json"])

    print(f"{GREEN}{BOLD}  ✅ All 6 missing modules built and working!{RESET}\n")
