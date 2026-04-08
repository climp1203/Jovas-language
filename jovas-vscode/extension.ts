import * as vscode from 'vscode';
import * as path from 'path';
import * as fs from 'fs';

// ─────────────────────────────────────────────
//  JOVAS VS CODE EXTENSION — extension.ts
//  Commands: run, lint, format, repl, check
// ─────────────────────────────────────────────

let outputChannel: vscode.OutputChannel;
let diagnosticCollection: vscode.DiagnosticCollection;
let statusBarItem: vscode.StatusBarItem;

export function activate(context: vscode.ExtensionContext) {
    // Create output channel
    outputChannel = vscode.window.createOutputChannel('Jovas');

    // Create diagnostic collection for linting
    diagnosticCollection = vscode.languages.createDiagnosticCollection('jovas');

    // Create status bar item
    statusBarItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 100);
    statusBarItem.text = '$(symbol-misc) Jovas';
    statusBarItem.tooltip = 'Jovas Language';
    statusBarItem.command = 'jovas.runFile';

    context.subscriptions.push(outputChannel);
    context.subscriptions.push(diagnosticCollection);
    context.subscriptions.push(statusBarItem);

    // Show status bar for .jovas files
    const updateStatusBar = () => {
        const editor = vscode.window.activeTextEditor;
        if (editor && (editor.document.fileName.endsWith('.jovas') || editor.document.fileName.endsWith('.jo'))) {
            statusBarItem.show();
        } else {
            statusBarItem.hide();
        }
    };

    context.subscriptions.push(
        vscode.window.onDidChangeActiveTextEditor(updateStatusBar)
    );
    updateStatusBar();

    // ── Register Commands ──

    // Run File
    context.subscriptions.push(
        vscode.commands.registerCommand('jovas.runFile', async () => {
            const editor = vscode.window.activeTextEditor;
            if (!editor) {
                vscode.window.showErrorMessage('No active file to run.');
                return;
            }
            await editor.document.save();
            runJovasFile(editor.document.fileName, 'run');
        })
    );

    // Lint File
    context.subscriptions.push(
        vscode.commands.registerCommand('jovas.lintFile', async () => {
            const editor = vscode.window.activeTextEditor;
            if (!editor) return;
            await editor.document.save();
            lintJovasFile(editor.document);
        })
    );

    // Format File
    context.subscriptions.push(
        vscode.commands.registerCommand('jovas.formatFile', async () => {
            const editor = vscode.window.activeTextEditor;
            if (!editor) return;
            await editor.document.save();
            runJovasFile(editor.document.fileName, 'format');
        })
    );

    // Open REPL
    context.subscriptions.push(
        vscode.commands.registerCommand('jovas.openRepl', () => {
            openJovasRepl();
        })
    );

    // Check Syntax
    context.subscriptions.push(
        vscode.commands.registerCommand('jovas.checkSyntax', async () => {
            const editor = vscode.window.activeTextEditor;
            if (!editor) return;
            await editor.document.save();
            runJovasFile(editor.document.fileName, 'check');
        })
    );

    // New File
    context.subscriptions.push(
        vscode.commands.registerCommand('jovas.newFile', async () => {
            await createNewJovasFile();
        })
    );

    // ── Auto lint on save ──
    context.subscriptions.push(
        vscode.workspace.onDidSaveTextDocument(async (document) => {
            if (document.fileName.endsWith('.jovas') || document.fileName.endsWith('.jo')) {
                const config = vscode.workspace.getConfiguration('jovas');
                if (config.get('autoLintOnSave')) {
                    lintJovasFile(document);
                }
                if (config.get('autoFormatOnSave')) {
                    runJovasFile(document.fileName, 'format');
                }
            }
        })
    );

    // ── Hover provider — show docs on hover ──
    context.subscriptions.push(
        vscode.languages.registerHoverProvider('jovas', {
            provideHover(document, position) {
                const word = document.getText(document.getWordRangeAtPosition(position));
                const docs = getJovasDocs(word);
                if (docs) {
                    return new vscode.Hover(new vscode.MarkdownString(docs));
                }
            }
        })
    );

    // ── Completion provider — IntelliSense ──
    context.subscriptions.push(
        vscode.languages.registerCompletionItemProvider(
            'jovas',
            {
                provideCompletionItems(document, position) {
                    return getCompletionItems();
                }
            },
            '.', '('
        )
    );

    console.log('🟡 Jovas extension activated');
    vscode.window.showInformationMessage('🟡 Jovas Language extension loaded!');
}

export function deactivate() {
    diagnosticCollection.clear();
    diagnosticCollection.dispose();
    outputChannel.dispose();
    statusBarItem.dispose();
}

// ─────────────────────────────────────────────
//  HELPERS
// ─────────────────────────────────────────────

function getRunnerPath(filePath: string): string {
    const config = vscode.workspace.getConfiguration('jovas');
    const configPath = config.get<string>('runnerPath');
    if (configPath && fs.existsSync(configPath)) return configPath;

    // Auto-detect run.py next to the file or in workspace
    const dir = path.dirname(filePath);
    const candidates = [
        path.join(dir, 'run.py'),
        path.join(dir, '..', 'run.py'),
    ];
    const workspaceFolders = vscode.workspace.workspaceFolders;
    if (workspaceFolders) {
        candidates.push(path.join(workspaceFolders[0].uri.fsPath, 'run.py'));
    }
    for (const c of candidates) {
        if (fs.existsSync(c)) return c;
    }
    return 'run.py';
}

function getPythonPath(): string {
    const config = vscode.workspace.getConfiguration('jovas');
    return config.get<string>('pythonPath') || 'python';
}

function runJovasFile(filePath: string, command: 'run' | 'check' | 'format') {
    const python   = getPythonPath();
    const runner   = getRunnerPath(filePath);
    const terminal = vscode.window.createTerminal({
        name: `Jovas — ${command}`,
        cwd: path.dirname(filePath),
    });

    const cmdMap = { run: 'run', check: 'check', format: 'fmt' };
    terminal.sendText(`${python} "${runner}" ${command} "${filePath}"`);
    terminal.show();
}

function openJovasRepl() {
    const workspaceFolders = vscode.workspace.workspaceFolders;
    const cwd = workspaceFolders ? workspaceFolders[0].uri.fsPath : process.cwd();
    const runner   = path.join(cwd, 'run.py');
    const python   = getPythonPath();
    const terminal = vscode.window.createTerminal({ name: 'Jovas REPL', cwd });
    terminal.sendText(`${python} "${runner}" repl`);
    terminal.show();
}

async function createNewJovasFile() {
    const folders = vscode.workspace.workspaceFolders;
    const defaultUri = folders ? vscode.Uri.joinPath(folders[0].uri, 'app.jovas') : undefined;
    const uri = await vscode.window.showSaveDialog({
        defaultUri,
        filters: { 'Jovas Files': ['jovas', 'jo'] },
        title: 'Create new .jovas file'
    });
    if (!uri) return;

    const template = [
        '// ' + path.basename(uri.fsPath) + ' — built with Jovas v1.0',
        '',
        'import json',
        '',
        'const APP  = "MyApp"',
        'const PORT = 8080',
        '',
        'fn main()',
        '    print("Hello from ${APP}!")',
        '',
        'main()',
    ].join('\n');

    fs.writeFileSync(uri.fsPath, template, 'utf8');
    const doc = await vscode.workspace.openTextDocument(uri);
    await vscode.window.showTextDocument(doc);
}

function lintJovasFile(document: vscode.TextDocument) {
    const source = document.getText();
    const lines  = source.split('\n');
    const diagnostics: vscode.Diagnostic[] = [];

    // Simple lint rules mirroring JovasLinter
    const consts = new Set<string>();
    let afterReturn = false;

    lines.forEach((rawLine, i) => {
        const line = rawLine.trim();
        const lineNum = i;

        if (line.startsWith('//') || line.startsWith('#')) return;

        // Const declaration
        const constMatch = line.match(/^const\s+(\w+)\s*=/);
        if (constMatch) consts.add(constMatch[1]);

        // Const reassignment
        const assignMatch = line.match(/^(\w+)\s*=(?!=)/);
        if (assignMatch && consts.has(assignMatch[1])) {
            const range = new vscode.Range(lineNum, 0, lineNum, rawLine.length);
            diagnostics.push(new vscode.Diagnostic(
                range,
                `Cannot reassign constant '${assignMatch[1]}'`,
                vscode.DiagnosticSeverity.Error
            ));
        }

        // Division by zero
        if (/\/\s*0(?!\.\d)/.test(line)) {
            const col = rawLine.indexOf('/');
            const range = new vscode.Range(lineNum, col, lineNum, col + 3);
            diagnostics.push(new vscode.Diagnostic(
                range,
                'Possible division by zero',
                vscode.DiagnosticSeverity.Warning
            ));
        }

        // Infinite loop risk
        if (/while\s+true\b/i.test(line)) {
            const range = new vscode.Range(lineNum, 0, lineNum, rawLine.length);
            diagnostics.push(new vscode.Diagnostic(
                range,
                'Infinite loop risk — ensure there is a break or return',
                vscode.DiagnosticSeverity.Warning
            ));
        }

        // Unreachable code
        if (afterReturn && line && !line.startsWith('else') && !line.startsWith('catch')) {
            const range = new vscode.Range(lineNum, 0, lineNum, rawLine.length);
            diagnostics.push(new vscode.Diagnostic(
                range,
                'Unreachable code after return',
                vscode.DiagnosticSeverity.Warning
            ));
            afterReturn = false;
        }
        if (/^return\b/.test(line)) afterReturn = true;
        else if (line) afterReturn = false;
    });

    diagnosticCollection.set(document.uri, diagnostics);

    const errors   = diagnostics.filter(d => d.severity === vscode.DiagnosticSeverity.Error).length;
    const warnings = diagnostics.filter(d => d.severity === vscode.DiagnosticSeverity.Warning).length;

    if (diagnostics.length === 0) {
        vscode.window.setStatusBarMessage('$(check) Jovas: No issues found', 3000);
    } else {
        vscode.window.setStatusBarMessage(
            `$(warning) Jovas: ${errors} error(s), ${warnings} warning(s)`, 5000
        );
    }
}

// ─────────────────────────────────────────────
//  HOVER DOCS
// ─────────────────────────────────────────────
function getJovasDocs(word: string): string | null {
    const docs: Record<string, string> = {
        'let':       '**let** — Declare a mutable variable\n```jovas\nlet name = "Jovas"\n```',
        'const':     '**const** — Declare an immutable constant\n```jovas\nconst PORT = 8080\n```',
        'fn':        '**fn** — Declare a function\n```jovas\nfn greet(name)\n    return "Hello, ${name}!"\n```',
        'async':     '**async** — Declare an async function\n```jovas\nasync fn fetchData(url)\n    let res = await http.get(url)\n    return res.body\n```',
        'await':     '**await** — Wait for an async operation\n```jovas\nlet res = await http.get(url)\n```',
        'expose':    '**expose** — Auto-generate a REST endpoint for this function\n```jovas\nexpose fn getUser(id)\n    return db.findOne("users", { id: id })\n// → POST /api/getUser auto-created\n```',
        'class':     '**class** — Declare a class\n```jovas\nclass User\n    fn init(name)\n        self.name = name\n```',
        'self':      '**self** — Reference to the current class instance\n```jovas\nself.name = "Alex"\n```',
        'import':    '**import** — Import a built-in module\n```jovas\nimport math\nimport json\n```',
        'match':     '**match** — Pattern matching\n```jovas\nmatch status\n    case "active"  => print("Running")\n    case "stopped" => print("Halted")\n    case "default" => print("Unknown")\n```',
        'print':     '**print()** — Print to console\n```jovas\nprint("Hello!")\nprint("Value: ${x}")\n```',
        'http':      '**http** — Built-in HTTP client\n```jovas\nlet res = await http.get("https://api.example.com")\nlet res = await http.post("https://api.example.com", { name: "Alex" })\n```',
        'database':  '**database** — JovasDB native integration\n```jovas\nlet db = database.connect("myapp")\ndb.insert("users", { name: "Alex" })\nlet rows = db.select("users")\n```',
        'db':        '**db** — Default JovasDB connection\n```jovas\ndb.insert("users", { name: "Alex" })\nlet rows = db.ask("find all active users")\n```',
        'auth':      '**auth** — Authentication module\n```jovas\nlet token = auth.sign({ userId: 1 }, "secret")\nlet data  = auth.verify(token, "secret")\n```',
        'email':     '**email** — Email module\n```jovas\nemail.send({ to: "user@example.com", subject: "Hi", body: "Hello!" })\nemail.sendTemplate("welcome", { name: "Alex" }, "user@example.com")\n```',
        'security':  '**security** — Security module\n```jovas\nlet hash = security.hash("password")\nlet ok   = security.verify("password", hash)\nlet token = security.jwtSign({ userId: 1 }, "secret", 3600)\n```',
        'ai':        '**ai** — Built-in AI module\n```jovas\nlet reply     = ai.ask("Explain recursion")\nlet sentiment = ai.sentiment("Jovas is awesome!")\nlet summary   = ai.summarize(longText)\n```',
        'deploy':    '**deploy** — One-line deployment\n```jovas\ndeploy.to("cloud", { region: "us-east-1", scale: "auto" })\ndeploy.rollback()\ndeploy.scale(5)\n```',
        'realtime':  '**realtime** — Built-in real-time pub/sub\n```jovas\nrealtime.sync("chat", fn(data)\n    print(data)\n)\nrealtime.broadcast("chat", { from: "Alex", text: "Hello!" })\n```',
        'log':       '**log** — Built-in logging\n```jovas\nlog.info(["Server started", { port: 8080 }])\nlog.warn(["High memory"])\nlog.error(["DB timeout"])\n```',
        'fmt':       '**fmt** — Code formatter\n```jovas\nlet formatted = fmt.format(source)\nfmt.formatFile("app.jovas")\n```',
        'lint':      '**lint** — Code linter\n```jovas\nlet result = lint.check(source)\nif result.clean == false\n    print(result.issues)\n```',
        'debug':     '**debug** — Built-in debugger\n```jovas\ndebug.breakpoint("myFn", 10)\ndebug.watch("userId")\ndebug.inspect({ userId: 42 })\ndebug.time("operation")\n```',
        'server':    '**server** — HTTP server\n```jovas\nlet app = server.create()\napp.get("/", onHome)\napp.listen(8080, onStart)\n```',
    };
    return docs[word] || null;
}

// ─────────────────────────────────────────────
//  COMPLETION ITEMS
// ─────────────────────────────────────────────
function getCompletionItems(): vscode.CompletionItem[] {
    const items: vscode.CompletionItem[] = [];

    const keywords = [
        'let', 'const', 'fn', 'async', 'await', 'expose', 'return',
        'if', 'else', 'for', 'in', 'while', 'repeat', 'match', 'case',
        'try', 'catch', 'finally', 'class', 'self', 'import',
        'thread', 'parallel', 'task', 'true', 'false', 'null'
    ];

    keywords.forEach(kw => {
        const item = new vscode.CompletionItem(kw, vscode.CompletionItemKind.Keyword);
        item.detail = 'Jovas keyword';
        items.push(item);
    });

    const modules = [
        ['print',    'print(value)',      'Print to console'],
        ['len',      'len(array)',         'Get length'],
        ['type',     'type(value)',        'Get type name'],
        ['str',      'str(value)',         'Convert to string'],
        ['int',      'int(value)',         'Convert to integer'],
        ['http',     'http.get(url)',      'HTTP client module'],
        ['database', 'database.connect(name)', 'JovasDB module'],
        ['db',       'db.select(table)',   'Default JovasDB connection'],
        ['auth',     'auth.sign(payload, secret)', 'Auth module'],
        ['email',    'email.send(msg)',    'Email module'],
        ['security', 'security.hash(pw)', 'Security module'],
        ['ai',       'ai.ask(prompt)',     'AI module'],
        ['deploy',   'deploy.to(target, config)', 'Deploy module'],
        ['realtime', 'realtime.sync(channel, fn)', 'Realtime module'],
        ['log',      'log.info([msg])',    'Logging module'],
        ['server',   'server.create()',   'HTTP server module'],
        ['fmt',      'fmt.format(source)', 'Formatter module'],
        ['lint',     'lint.check(source)', 'Linter module'],
        ['debug',    'debug.breakpoint(fn, line)', 'Debugger module'],
        ['math',     'math.sqrt(n)',       'Math module'],
        ['json',     'json.parse(str)',    'JSON module'],
        ['crypto',   'crypto.hash(str)',   'Crypto module'],
        ['time',     'time.now()',         'Time module'],
        ['file',     'file.read(path)',    'File system module'],
        ['config',   'config.load(path)', 'Config module'],
    ];

    modules.forEach(([label, detail, doc]) => {
        const item = new vscode.CompletionItem(label, vscode.CompletionItemKind.Module);
        item.detail = detail;
        item.documentation = new vscode.MarkdownString(doc);
        items.push(item);
    });

    return items;
}
