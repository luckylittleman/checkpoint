"""Checkpoint simulator. Run: uvicorn app:app --reload  ->  http://127.0.0.1:8000
Needs: pip install fastapi uvicorn, and Go on your PATH."""
import json, random, re, shlex, shutil, subprocess, tempfile, time
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

BASE = Path(__file__).parent
app = FastAPI()
S = {"active": False}


class Start(BaseModel):
    minutes: int = 60
    count: int = 2
    details: bool = False


class Submit(BaseModel):
    code: str


def questions():
    return json.loads((BASE / "questions.json").read_text(encoding="utf-8"))  # reloaded each start: edit freely


def prep(d):
    (d / "go.mod").write_text("module checkpoint\n\ngo 1.18\n\nrequire github.com/01-edu/z01 v0.0.0\nreplace github.com/01-edu/z01 => ./z01\n")
    (d / "z01").mkdir()
    (d / "z01" / "go.mod").write_text("module github.com/01-edu/z01\n\ngo 1.18\n")
    (d / "z01" / "z01.go").write_text('package z01\n\nimport "os"\n\nfunc PrintRune(r rune) { os.Stdout.WriteString(string(r)) }\n')


def grade(q, code):
    allowed = q.get("allowed_imports")
    if allowed is not None:
        blocks = re.findall(r"import\s*\((.*?)\)", code, re.S) + re.findall(r'import\s+"[^"]+"', code)
        bad = set(re.findall(r'"([^"]+)"', " ".join(blocks))) - set(allowed)
        if bad:
            return {"ok": False, "stage": "rules", "msg": "Forbidden import: " + ", ".join(sorted(bad))}
    d = Path(tempfile.mkdtemp())
    try:
        prep(d)
        (d / "solution.go").write_text(code)
        if q.get("harness"):
            (d / "main.go").write_text(q["harness"])
        try:
            b = subprocess.run(["go", "build", "-o", "prog", "."], cwd=d, capture_output=True, text=True, timeout=60)
        except FileNotFoundError:
            return {"ok": False, "stage": "setup", "msg": "Go not found on PATH."}
        except subprocess.TimeoutExpired:
            return {"ok": False, "stage": "compile", "msg": "Build timed out."}
        if b.returncode:
            return {"ok": False, "stage": "compile", "msg": b.stderr[-1500:]}
        tests = q["tests"]
        for i, t in enumerate(tests, 1):
            try:
                r = subprocess.run([str(d / "prog"), *t["args"]], capture_output=True, text=True, timeout=5)
                got, err = r.stdout, (r.stderr[-600:] if r.returncode else "")
            except subprocess.TimeoutExpired:
                got, err = "", "timeout (5s): infinite loop?"
            if err or got.rstrip("\n") != t["out"].rstrip("\n"):
                return {"ok": False, "stage": "test", "test": i, "total": len(tests),
                        "detail": {"args": t["args"], "expected": t["out"], "got": got, "error": err}}
        return {"ok": True, "total": len(tests)}
    finally:
        shutil.rmtree(d, ignore_errors=True)


def describe(q):
    d = {k: q[k] for k in ("id", "title", "statement", "starter")}
    al = q.get("allowed_imports")
    d["allowed"] = "any" if al is None else (", ".join(al) or "none")
    d["file"] = q["id"] + ".go" if q["kind"] == "func" else "main.go"
    if q["kind"] == "func":
        d["scratch"] = 'package main\n\nimport "fmt"\n\nfunc main() {\n\tfmt.Println()\n}\n'  # your own test file
    ts, h = q["tests"][:4], q.get("harness") or ""
    if q["kind"] == "program":
        d["run"] = "\n".join("$ go run . " + " ".join(json.dumps(a, ensure_ascii=False) for a in t["args"]) + "\n" + t["out"] for t in ts)
        return d
    sig = re.search(r"func .*\{", q["starter"]).group(0)
    d["expected"] = sig + "\n\n}"
    if q.get("main_code"):  # hand-written main.go for questions the generator can't cover
        d["main_code"] = d["scratch"] = q["main_code"]
        d["run"] = q["run"]
        return d
    m = re.search(r"func (\w+)\((.*?)\) ", q["starter"])
    types = [p.split()[-1] for p in m.group(2).split(",")]
    if all(t in ("string", "int", "uint") for t in types) and "parse(" not in h and "Split(" not in h:
        calls = ["\tfmt.Println(%s(%s))" % (m.group(1), ", ".join(json.dumps(a, ensure_ascii=False) if ty == "string" else a for a, ty in zip(t["args"], types))) for t in ts]
        d["main_code"] = 'package main\n\nimport (\n\t"fmt"\n)\n\nfunc main() {\n' + "\n".join(calls) + "\n}\n"
        d["scratch"] = d["main_code"]
        d["run"] = "$ go run .\n" + "\n".join(t["out"] for t in ts)
    return d


def state():
    if not S["active"] and "qs" not in S:
        return {"started": False}
    left = max(0, int(S["deadline"] - time.time()))
    if S["active"] and left == 0:
        S["active"] = False
    i, qs = S["index"], S["qs"]
    out = {"started": True, "finished": not S["active"], "remaining": left, "index": i,
           "total": len(qs), "passed": i, "timed_out": left == 0 and i < len(qs)}
    if S["active"]:
        q = qs[i]
        out["question"] = describe(q)
        tiers = sorted({x["level"] for x in questions()})
        out["question"]["rank"], out["question"]["ranks"] = tiers.index(q["level"]) + 1, len(tiers)  # 5%=1, 10%=2 ...
    return out


@app.post("/api/start")
def start(p: Start):
    tiers = {}
    for q in questions():
        tiers.setdefault(q["level"], []).append(q)
    qs = [random.choice(tiers[k]) for k in sorted(tiers)][: max(1, p.count)]  # one per tier, easy to hard
    S.update(active=True, qs=qs, index=0, details=p.details, deadline=time.time() + p.minutes * 60)
    return state()


@app.get("/api/state")
def get_state():
    return state()


@app.post("/api/submit")
def submit(p: Submit):
    st = state()
    if not S["active"]:
        raise HTTPException(400, "No active session (finished or time is up).")
    res = grade(S["qs"][S["index"]], p.code)
    if res["ok"]:
        S["index"] += 1
        if S["index"] >= len(S["qs"]):
            S["active"] = False
    elif not S["details"] and "detail" in res:
        res["detail"] = None  # hidden tests, like the real thing
    return {"result": res, "state": state()}


class Run(BaseModel):
    sol: str
    main: str = ""
    args: str = ""


@app.post("/api/run")
def run(p: Run):
    if not S["active"]:
        raise HTTPException(400, "No active session (finished or time is up).")
    q = S["qs"][S["index"]]
    d = Path(tempfile.mkdtemp())
    try:
        prep(d)
        (d / "solution.go").write_text(p.sol)
        if q["kind"] == "func":
            (d / "main.go").write_text(p.main)
        try:
            args = shlex.split(p.args)
            b = subprocess.run(["go", "build", "-o", "prog", "."], cwd=d, capture_output=True, text=True, timeout=60)
            if b.returncode:
                return {"output": b.stderr[-3000:]}
            r = subprocess.run([str(d / "prog"), *args], capture_output=True, text=True, timeout=10)
        except FileNotFoundError:
            return {"output": "Go not found on PATH."}
        except subprocess.TimeoutExpired:
            return {"output": "timeout: infinite loop?"}
        except ValueError as e:
            return {"output": "bad arguments: %s" % e}
        return {"output": (r.stdout + r.stderr)[-4000:]}
    finally:
        shutil.rmtree(d, ignore_errors=True)


@app.get("/", response_class=HTMLResponse)
def home():
    return HTMLResponse((BASE / "page.html").read_text(encoding="utf-8"))


