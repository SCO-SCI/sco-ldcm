"""Layer 6: the page's dropdown evaluator, exhaustively, without a browser.

The input form on the page decides, at every moment, which filters, models
and velocities may be chosen together, what the typed fields may range over,
and when the metallicity locks to solar.  All of that is one pure JavaScript
function, scoEvaluate, in static/index.html, plus a small amount of glue that
moves a dropdown onto a selectable value and runs the evaluation to a fixed
point (scoFillSelect, scoRefreshOnce, scoRefresh), plus the function that
writes the note explaining any move the page made (scoNoteAfterRefresh).
Layers 1 to 5 test the service; none of them touches this code.  Phase 3
added a fourth model, eleven filters and the first velocity (1 km/s) at which
two models serve disjoint sets of filters, so the evaluator is where Phase 3
changed what a user can do.  This layer tests it exhaustively (decision (h),
E. Mullen, 10 October 2026).

HOW
  The functions are cut out of static/index.html verbatim, by brace matching
  from their declarations, so the code under test is the shipped code and
  cannot drift from it.  They run in V8: in node when it is on the PATH,
  otherwise in the embedded V8 of the mini-racer package (pip install
  mini-racer; needs Python 3.10 or later).  The capability maps
  come from the engines in the v5 checkout (ldc_core.get_capabilities, the
  same function behind /api/capabilities), so nothing here needs a server or
  the network.  The page's glue (how a <select> settles when its options are
  rebuilt) is modelled in Python from the HTML specification's behaviour,
  which was checked in Chromium: a value is kept when its option is still
  selectable, the touched field keeps its value whenever the option exists
  at all, otherwise the first selectable option is taken, and a select whose
  options are all disabled reads as blank.

WHAT IT ASSERTS, per law
  Map     every display name resolves to exactly one storage key; under the
          two laws that serve JWST, PHOENIX-NE is its own key, each of the
          eleven modes holds exactly one grid (PHOENIX-NE, 1 km/s, solar,
          2400-7800 K, log g 3.0-5.5); under the quadratic law no JWST code
          and no PHOENIX-NE appear.
  Sound   every option the evaluator marks available is backed by a grid
          that satisfies every other selected constraint, recomputed here in
          Python from the documented rule, including the Phase 3 rule that
          a stale model or velocity is ignored while the other's options
          are worked out.
  Complete no option is marked unavailable while such a grid exists.
  Tags    every unavailable option carries a reason; the reason equals the
          one the documented three-tier wording rule gives; and it is
          actionable: relaxing the setting it names opens the option (any
          one of them for the no-conjunction form, all of them together and
          none alone for the "or" form).  The bare "Unavailable" never
          appears.  The vocabulary of tags is written out for reading.
  Ranges  the Teff and log g blurbs are the envelope of the surviving grids;
          [Fe/H] locks exactly when every surviving grid is solar-only.
  Settle  from every real (filter, model, velocity) state and from the
          default state, choosing every other filter, every selectable
          model and every selectable velocity settles in at most six
          passes (the deepest chain is recorded) on a combination the
          service holds, or, for a typed temperature no table covers, on
          no model with the "No model available" note.
  Moves   a setting moves only when the chosen filter has no table at it
          (decision (d)): the model stays when the new filter has a table
          under it, the velocity stays when the new filter has a table at
          it, and otherwise each moves to the first selectable value, which
          for the model is ATLAS whenever ATLAS serves the filter.
  Notes   the note after every such move has the decided wording (decision
          (i)): "Filter X requires model M [at xi = V km/s]." when one model
          serves the filter at the settled velocity, "Filter X requires
          model A or B[ at xi = V km/s]." naming every model that would do,
          in dropdown order, when more than one would (the page takes the
          first), "Filter X requires xi = V km/s." when only the velocity
          moved, nothing when nothing moved; and a non-solar [Fe/H] set
          aside by a solar-only table is reported.
  Orders  every real combination is reachable from the default state by at
          least one order of entering its three settings, and every order
          the dropdowns permit lands on exactly that combination.
  JWST    every mode is selectable from the default state and one choice
          settles on (mode, PHOENIX-NE, 1 km/s) with the metallicity locked;
          leaving a mode for an ordinary filter keeps 1 km/s.

RUNNING
  python layer6_page.py --v5 <checkout> [--results DIR] [--engine auto|mini-racer|node]
  Exit 0 when nothing fails, 2 on a failure, 3 when no JavaScript engine is
  available.  Results: layer6_page.json and layer6_tags_<law>.txt.
"""
import argparse, hashlib, itertools, json, os, re, shutil, subprocess, sys, tempfile, time
here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, here)
from common import LAWS

JWST_CODES = ("F210M", "F322W2", "F444W", "SOSS1", "SOSS2", "F277W",
              "G235H", "G235M", "G395H", "G395M", "PRISM")
JWST_MODEL, JWST_XI = "PHOENIX-NE", 1.0
SCO_DEFAULT_XI = 2
DEFAULT_MODEL = "ATLAS"          # the model applyLaw selects on a law switch
FIRST_MODEL = "ATLAS"            # decision (i): the first model in the list

# ------------------------------------------------------------------ extraction
def extract_function(src, name):
    """The text of `function name(...) {...}` from a JavaScript source, by
    brace matching that skips strings, template literals and comments."""
    start = src.index("function " + name + "(")
    i = src.index("{", start)
    depth, k, n = 0, i, len(src)
    mode = "code"                 # code | sq | dq | tpl | line | block
    tpl_depths = []               # brace depth at each `${` inside a template
    while k < n:
        c = src[k]; nxt = src[k + 1] if k + 1 < n else ""
        if mode == "code":
            if c == "/" and nxt == "/": mode = "line"; k += 2; continue
            if c == "/" and nxt == "*": mode = "block"; k += 2; continue
            if c == "'": mode = "sq"
            elif c == '"': mode = "dq"
            elif c == "`": mode = "tpl"
            elif c == "{": depth += 1
            elif c == "}":
                if tpl_depths and depth == tpl_depths[-1]:
                    tpl_depths.pop(); mode = "tpl"
                else:
                    depth -= 1
                    if depth == 0: return src[start:k + 1]
        elif mode == "line":
            if c == "\n": mode = "code"
        elif mode == "block":
            if c == "*" and nxt == "/": mode = "code"; k += 2; continue
        elif mode in ("sq", "dq"):
            if c == "\\": k += 2; continue
            if (mode == "sq" and c == "'") or (mode == "dq" and c == '"'): mode = "code"
        elif mode == "tpl":
            if c == "\\": k += 2; continue
            if c == "`": mode = "code"
            elif c == "$" and nxt == "{": tpl_depths.append(depth); mode = "code"; k += 2; continue
        k += 1
    raise ValueError("unbalanced braces in " + name)

PAGE_FUNCTIONS = ("scoEvaluate", "scoNoteKey", "scoShowNote", "scoClearNote", "scoNoteAfterRefresh")

# What the note function needs from the page besides the functions above: the
# globals it reads and writes, and the message element it writes to.
JS_PREAMBLE = """
let SCO_ANCHOR = null;
let SCO_NOTE = null, SCO_NOTE_KEYS = [], SCO_NOTE_STATE = null;
let SCO_CAPS_CURRENT = [];
const statusEl = { textContent: '', classList: { _s: new Set(),
  contains(c) { return this._s.has(c); },
  add(...cs) { cs.forEach(c => this._s.add(c)); },
  remove(...cs) { cs.forEach(c => this._s.delete(c)); } } };
"""
JS_HELPERS = """
var __CAPS = null;
function __setCaps(caps) { __CAPS = caps; SCO_CAPS_CURRENT = caps; return __CAPS.length; }
function __ev(state) { return scoEvaluate(state, __CAPS); }
function __note(origin, final, anchor) {
  SCO_ANCHOR = anchor; SCO_NOTE = null; SCO_NOTE_KEYS = []; SCO_NOTE_STATE = null;
  statusEl.textContent = ''; statusEl.classList._s.clear();
  scoNoteAfterRefresh(origin, final);
  const out = { note: SCO_NOTE, keys: SCO_NOTE_KEYS.slice(), shown: statusEl.textContent };
  SCO_ANCHOR = null; return out;
}
function __noteAgain(final, anchor) {
  // a second refresh in which nothing moved: the note stays or clears
  SCO_ANCHOR = anchor; statusEl.textContent = ''; statusEl.classList._s.clear();
  scoNoteAfterRefresh(final, final);
  const out = { note: SCO_NOTE, shown: statusEl.textContent }; SCO_ANCHOR = null; return out;
}
"""

# ------------------------------------------------------------------ engines
class MiniRacerEngine:
    name = "mini-racer"
    def __init__(self, source):
        from py_mini_racer import MiniRacer
        self.ctx = MiniRacer(); self.ctx.eval(source)
    def call(self, fn, *args): return self.ctx.call(fn, *args)
    def close(self):
        # The context must go before the interpreter does: mini-racer 0.14.1
        # hangs at interpreter exit if a context is still alive (seen on Linux).
        self.ctx = None

class NodeEngine:
    name = "node"
    RUNNER = r"""
const fs = require('fs'), vm = require('vm'), readline = require('readline');
vm.runInThisContext(fs.readFileSync(process.argv[2], 'utf8'));
const rl = readline.createInterface({ input: process.stdin });
rl.on('line', (line) => {
  const req = JSON.parse(line);
  let out;
  try { out = { ok: true, value: globalThis[req.fn](...req.args) }; }
  catch (e) { out = { ok: false, error: String(e && e.stack || e) }; }
  process.stdout.write(JSON.stringify(out === undefined ? null : out) + '\n');
});
"""
    def __init__(self, source, node):
        # The two working files go in a private temporary folder, removed by
        # close(), not in results/ (which the repository tracks). Files and
        # pipe are UTF-8 explicitly: the page's code contains the Greek letter
        # xi, which the Windows default text encoding (the ANSI code page)
        # cannot hold, so relying on the default failed there (12 October 2026).
        self.tmp = tempfile.mkdtemp(prefix="layer6_")
        self.src = os.path.join(self.tmp, "page_source.js")
        self.runner = os.path.join(self.tmp, "runner.js")
        with open(self.src, "w", encoding="utf-8") as fh: fh.write(source)
        with open(self.runner, "w", encoding="utf-8") as fh: fh.write(self.RUNNER)
        self.p = subprocess.Popen([node, self.runner, self.src], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                  text=True, encoding="utf-8", bufsize=1)
    def call(self, fn, *args):
        self.p.stdin.write(json.dumps({"fn": fn, "args": list(args)}) + "\n"); self.p.stdin.flush()
        line = self.p.stdout.readline()
        if not line: raise RuntimeError("node runner exited")
        r = json.loads(line)
        if not r["ok"]: raise RuntimeError(r["error"])
        return r["value"]
    def close(self):
        try: self.p.stdin.close(); self.p.wait(timeout=10)
        except Exception: self.p.kill()
        shutil.rmtree(self.tmp, ignore_errors=True)

def make_engine(source, choice):
    """node when it is on the PATH (the same V8, and quicker over a pipe than
    mini-racer's call marshalling), otherwise the mini-racer package."""
    node = shutil.which("node")
    if choice in ("auto", "node") and node:
        return NodeEngine(source, node)
    if choice in ("auto", "mini-racer"):
        try:
            return MiniRacerEngine(source)
        except ImportError:
            if choice == "mini-racer": raise
    return None

# ------------------------------------------------------------------ the maps
def dump_caps(v5, law, path):
    """Run in a subprocess: load one engine and write its capability map."""
    import logging; logging.disable(logging.CRITICAL)
    from common import load_engine
    core, _ = load_engine(v5, law)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(core.get_capabilities(), fh)

def capability_map(v5, law, results):
    path = os.path.join(results, f"layer6_caps_{law}.json")
    r = subprocess.run([sys.executable, os.path.abspath(__file__), "--dump-caps", law, path, "--v5", v5],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise RuntimeError(f"could not load the {law} engine: {r.stderr[-800:]}")
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)

# ------------------------------------------------------------------ Python reference
def flatten(caps):
    grids = []
    for f in caps:
        for g in f["grids"]:
            grids.append(dict(filter=f["code"], model=g["model"], model_key=g["model_key"], xi=float(g["xi"]),
                              teff_min=g["teff_min"], teff_max=g["teff_max"], logg_min=g["logg_min"], logg_max=g["logg_max"],
                              feh_min=g["feh_min"], feh_max=g["feh_max"], feh_fixed=bool(g["feh_fixed"])))
    return grids

def fmt_xi(v):
    return str(int(v)) if float(v).is_integer() else repr(float(v))

def js_num(v):
    """JavaScript's String(number) for the values this harness uses."""
    return fmt_xi(v) if isinstance(v, (int, float)) else str(v)

class Ref:
    """The documented rule, written again in Python."""
    def __init__(self, grids):
        self.grids = grids
        self.keys = {}
        for g in grids: self.keys.setdefault(g["model"], g["model_key"])

    def model_key_of(self, display):
        if display in (None, ""): return None
        if display in self.keys: return self.keys[display]
        for g in self.grids:
            if g["model_key"] == display: return display
        return display

    def evaluate(self, state):
        g_all = self.grids
        def num(v):
            if v is None or v == "": return None
            try: return float(v)
            except (TypeError, ValueError): return None
        sel = dict(filter=state.get("filter") or None, model=state.get("model") or None,
                   modelKey=self.model_key_of(state.get("model")), xi=num(state.get("xi")),
                   teff=num(state.get("teff")), logg=num(state.get("logg")), feh=num(state.get("feh")))
        def as_typed(text, n):
            t = "" if text is None else str(text).strip()
            return t if t else ("" if n is None else js_num(n))
        sel["teffText"] = as_typed(state.get("teffText"), sel["teff"])
        sel["loggText"] = as_typed(state.get("loggText"), sel["logg"])
        sel["fehText"] = as_typed(state.get("fehText"), sel["feh"])
        # Each grid's violated constraints as a bit mask, once per state, so
        # the explainer's many relaxations are mask tests rather than loops.
        BIT = {"filter": 1, "model": 2, "xi": 4, "teff": 8, "logg": 16, "feh": 32}
        viol, viol_strict = [], []
        for g in g_all:
            v = 0
            if sel["filter"] is not None and g["filter"] != sel["filter"]: v |= BIT["filter"]
            if sel["modelKey"] is not None and g["model_key"] != sel["modelKey"]: v |= BIT["model"]
            if sel["xi"] is not None and g["xi"] != sel["xi"]: v |= BIT["xi"]
            if sel["teff"] is not None and (sel["teff"] < g["teff_min"] or sel["teff"] > g["teff_max"]): v |= BIT["teff"]
            if sel["logg"] is not None and (sel["logg"] < g["logg_min"] or sel["logg"] > g["logg_max"]): v |= BIT["logg"]
            feh_out = sel["feh"] is not None and (sel["feh"] < g["feh_min"] or sel["feh"] > g["feh_max"])
            viol_strict.append(v | (BIT["feh"] if feh_out else 0))
            viol.append(v | (BIT["feh"] if (feh_out and not g["feh_fixed"]) else 0))
        def mask(skip): return sum(BIT[n] for n in skip)
        def ok(i, skipmask, strict=False):
            return ((viol_strict[i] if strict else viol[i]) & ~skipmask) == 0
        def options_for(field, key, also=()):
            m = mask({field, *also})
            return {g[key] for i, g in enumerate(g_all) if ok(i, m)}, {g[key] for g in g_all}
        # the three-tier wording rule
        CONSTRAINTS = [
            ("model", lambda: sel["modelKey"] is not None, lambda: f"with model {sel['model']}"),
            ("filter", lambda: sel["filter"] is not None, lambda: f"with filter {sel['filter']}"),
            ("xi", lambda: sel["xi"] is not None, lambda: f"at ξ = {fmt_xi(sel['xi'])} km/s"),
            ("teff", lambda: sel["teff"] is not None, lambda: f"at Teff = {sel['teffText']}"),
            ("logg", lambda: sel["logg"] is not None, lambda: f"at Log(g) = {sel['loggText']}"),
            ("feh", lambda: sel["feh"] is not None, lambda: f"at [Fe/H] = {sel['fehText']}"),
        ]
        def join_combination(ph): return " ".join(("together " + p) if (i > 0 and p.startswith("with ")) else p for i, p in enumerate(ph))
        def join_or(ph): return " or ".join(p[5:] if (i > 0 and p.startswith("with ") and ph[i - 1].startswith("with ")) else p for i, p in enumerate(ph))
        def explain(field, key, value, never_blocks=()):
            # never_blocks: settings that cannot close this field (the model and
            # the velocity never close a filter since Phase 3) are neither a
            # reason for its tag nor relaxed in search of one.
            idx = [i for i, g in enumerate(g_all) if g[key] == value]
            base = {field, *never_blocks}
            def has(skip, strict=False):
                m = mask(skip); return any(ok(i, m, strict) for i in idx)
            if has(base): return None
            others = [c for c in CONSTRAINTS if c[0] not in base and c[1]()]
            def relax(names, strict=False): return has(base | set(names), strict)
            opens = [c for c in others if relax([c[0]])]
            if any(c[0] == "feh" for c in opens):
                opens = [c for c in opens if c[0] == "feh" or relax([c[0]], True)]
            if len(opens) == 1: return "Unavailable " + opens[0][2]()
            if len(opens) >= 2: return "Unavailable " + join_combination([c[2]() for c in opens])
            for size in range(2, len(others) + 1):
                for combo in itertools.combinations(others, size):
                    if relax([c[0] for c in combo]): return "Unavailable " + join_or([c[2]() for c in combo])
            return "Unavailable"
        f_avail, f_all = options_for("filter", "filter", ("model", "xi"))
        anchor = state.get("anchor") or None
        m_avail0, _ = options_for("model", "model"); x_avail0, _ = options_for("xi", "xi")
        model_stale = sel["model"] is not None and anchor != "model" and sel["model"] not in m_avail0
        xi_stale = sel["xi"] is not None and anchor != "xi" and sel["xi"] not in x_avail0
        m_avail, m_all = options_for("model", "model", ("xi",) if xi_stale else ())
        x_avail, x_all = options_for("xi", "xi", ("model",) if model_stale else ())
        def range_for(field, lo, hi):
            mn, mx, fixed, any_ = float("inf"), float("-inf"), True, False
            m = mask({field})
            for i, g in enumerate(g_all):
                if not ok(i, m): continue
                any_ = True; mn = min(mn, g[lo]); mx = max(mx, g[hi])
                if not g["feh_fixed"]: fixed = False
            return (mn, mx, fixed) if any_ else None
        tr, lr, fr = range_for("teff", "teff_min", "teff_max"), range_for("logg", "logg_min", "logg_max"), range_for("feh", "feh_min", "feh_max")
        return dict(
            filter=dict(available=f_avail, all=f_all, reasons={c: explain("filter", "filter", c, ("model", "xi")) for c in f_all - f_avail}),
            model=dict(available=m_avail, all=m_all, reasons={m: explain("model", "model", m) for m in m_all - m_avail}),
            xi=dict(available=x_avail, all=x_all, reasons={v: explain("xi", "xi", v) for v in x_all - x_avail}),
            teff=tr, logg=lr, feh=fr, feh_locked=bool(fr and fr[2]),
            model_stale=model_stale, xi_stale=xi_stale)

# ------------------------------------------------------------------ the page glue, modelled
def read_state(form, anchor):
    """scoReadState: the form as the evaluator receives it."""
    def n(s): return None if s.strip() == "" else float(s)
    return dict(filter=form["filter"] or None, model=form["model"] or None,
                xi=None if form["xi"] == "" else float(form["xi"]),
                teff=n(form["teff"]), logg=n(form["logg"]), feh=n(form["feh"]),
                teffText=form["teff"].strip(), loggText=form["logg"].strip(), fehText=form["feh"].strip(),
                anchor=anchor)

def fill_select(options, prev, is_anchor):
    """scoFillSelect on a select with no placeholder: (value, disabled) pairs."""
    selectable = [v for v, d in options if not d]
    if is_anchor and any(v == prev for v, _ in options): return prev
    if prev in selectable: return prev
    if selectable: return selectable[0]
    return ""                     # every option disabled: the select reads blank

def snapshot(form):
    return dict(filter=form["filter"], model=form["model"], xi=form["xi"], teff=form["teff"].strip(),
                logg=form["logg"].strip(), feh=form["feh"].strip(), fehLocked=form["feh_disabled"])

def refresh_once(form, anchor, ev):
    f = ev(read_state(form, anchor))["fields"]
    codes = [o["code"] for o in f["filter"]["options"]]
    form["filter"] = form["filter"] if form["filter"] in codes else ""
    form["model"] = fill_select([(o["value"], not o["available"]) for o in f["model"]["options"]], form["model"], anchor == "model")
    keep = form["xi"]
    if keep == "" and any(float(v) == SCO_DEFAULT_XI for v in f["xi"]["available"]): keep = str(SCO_DEFAULT_XI)
    form["xi"] = fill_select([(js_num(o["value"]), not o["available"]) for o in f["xi"]["options"]], keep, anchor == "xi")
    if f["feh"]["locked"]: form["feh"] = "0.0"; form["feh_disabled"] = True
    else: form["feh_disabled"] = False
    return f

def settle(form, anchor, ev):
    """scoRefresh: passes until the form stops changing (cap 6). The form
    already holds the user's change. Returns (passes, origin, final)."""
    origin = snapshot(form); before = None; passes = 0
    for _ in range(6):
        refresh_once(form, anchor, ev); passes += 1
        after = (form["filter"], form["model"], form["xi"], form["feh"], form["feh_disabled"])
        if after == before: break
        before = after
    return passes, origin, snapshot(form)

def new_form(filter_="", model=DEFAULT_MODEL, xi="", teff="", logg="", feh=""):
    return dict(filter=filter_, model=model, xi=xi, teff=teff, logg=logg, feh=feh, feh_disabled=False)

# ------------------------------------------------------------------ the tag parser (for actionability)
PHRASE = re.compile(r"(?:together )?(?:with )?(model|filter) (\S+)|at ξ = (\S+) km/s|at (Teff|Log\(g\)|\[Fe/H\]) = (\S+)")
FIELD_OF = {"model": "model", "filter": "filter", "Teff": "teff", "Log(g)": "logg", "[Fe/H]": "feh"}

def parse_tag(tag):
    """-> (form, [field names]) where form is 'single' | 'combination' | 'or' | 'bare'."""
    if tag == "Unavailable": return "bare", []
    body = tag[len("Unavailable "):]
    parts = body.split(" or ")
    fields = []
    for part in parts:
        for m in PHRASE.finditer(part):
            if m.group(1): fields.append(m.group(1))
            elif m.group(3): fields.append("xi")
            else: fields.append(FIELD_OF[m.group(4)])
    if len(parts) > 1: return "or", fields
    return ("combination" if len(fields) > 1 else "single"), fields

# ------------------------------------------------------------------ assertions
class Report:
    def __init__(self, law, limit=25):
        self.law, self.limit = law, limit
        self.failures = {}; self.counts = {}
    def fail(self, check, detail):
        lst = self.failures.setdefault(check, [])
        if len(lst) < self.limit: lst.append(detail)
        self.counts[check] = self.counts.get(check, 0) + 1
    def ok(self): return not self.counts

def opt_value(o): return o["code"] if "code" in o else o["value"]

def state_key(state):
    return tuple(state.get(k) for k in ("filter", "model", "xi", "teff", "logg", "feh", "anchor"))

class Avail:
    """Cached: which values each dropdown offers in a state, from the JS evaluator."""
    def __init__(self, ev): self.ev, self.cache = ev, {}
    def __call__(self, state):
        k = state_key(state)
        if k not in self.cache:
            F = self.ev(state)["fields"]
            self.cache[k] = {f: {opt_value(o) for o in F[f]["options"] if o["available"]} for f in ("filter", "model", "xi")}
        return self.cache[k]

def check_state(law, state, js, ref, rep, vocab, avail):
    """Soundness, completeness, tags, ranges, locks for one evaluator call."""
    F = js["fields"]
    key = {k: state.get(k) for k in ("filter", "model", "xi", "teff", "logg", "feh", "anchor")}
    # A stale model or velocity (one the chosen filter has no table at) is
    # moved by the next settling pass, so its tags are never rendered; the
    # actionability test, which relaxes one setting at a time, is for the
    # states a user can see.
    stale = ref["model_stale"] or ref["xi_stale"]
    # availability
    for field, jkey in (("filter", "code"), ("model", "value"), ("xi", "value")):
        got = {o[jkey] for o in F[field]["options"] if o["available"]}
        if field == "xi": got = {float(v) for v in got}
        want = ref[field]["available"]
        if got != want:
            rep.fail(f"{field}_availability", dict(state=key, js=sorted(map(str, got)), ref=sorted(map(str, want))))
        got_all = {o[jkey] for o in F[field]["options"]}
        if field == "xi": got_all = {float(v) for v in got_all}
        if got_all != ref[field]["all"]:
            rep.fail(f"{field}_universe", dict(state=key, js=sorted(map(str, got_all)), ref=sorted(map(str, ref[field]["all"]))))
        if set(F[field]["available"]) != set(o[jkey] for o in F[field]["options"] if o["available"]):
            rep.fail(f"{field}_available_list", dict(state=key))
        # tags
        for o in F[field]["options"]:
            if o["available"]:
                if o["reason"] is not None: rep.fail(f"{field}_reason_on_available", dict(state=key, option=opt_value(o)))
                continue
            tag = o["reason"]
            vocab[tag] = vocab.get(tag, 0) + 1
            if not tag or tag == "Unavailable" or "undefined" in tag or "NaN" in tag or "null" in tag:
                rep.fail(f"{field}_tag_bare", dict(state=key, option=opt_value(o), tag=tag)); continue
            v = opt_value(o)
            want_tag = ref[field]["reasons"].get(float(v) if field == "xi" else v)
            if tag != want_tag:
                rep.fail(f"{field}_tag_wording", dict(state=key, option=v, js=tag, ref=want_tag))
            # actionable: relax what the tag names
            form, names = parse_tag(tag)
            if form == "bare" or not names:
                rep.fail(f"{field}_tag_unparsed", dict(state=key, option=v, tag=tag)); continue
            if stale: continue
            def opens(relaxed):
                s = dict(state)
                for nme in relaxed:
                    s[nme] = None
                    if nme in ("teff", "logg", "feh"): s[nme + "Text"] = ""
                return v in avail(s)[field]
            if form == "or":
                if not opens(names): rep.fail(f"{field}_tag_or_not_actionable", dict(state=key, option=v, tag=tag))
                for nme in names:
                    if opens([nme]): rep.fail(f"{field}_tag_or_overstated", dict(state=key, option=v, tag=tag, alone=nme))
            else:
                for nme in names:
                    if not opens([nme]): rep.fail(f"{field}_tag_not_actionable", dict(state=key, option=v, tag=tag, named=nme))
    # ranges and the lock
    for field in ("teff", "logg"):
        r = F[field]["range"]; want = ref[field]
        got = None if r is None else (r["min"], r["max"])
        if (want is None and got is not None) or (want is not None and (got is None or got != (want[0], want[1]))):
            rep.fail(f"{field}_range", dict(state=key, js=got, ref=None if want is None else want[:2]))
    if bool(F["feh"]["locked"]) != ref["feh_locked"]:
        rep.fail("feh_lock", dict(state=key, js=F["feh"]["locked"], ref=ref["feh_locked"]))
    if F["feh"]["locked"] and F["feh"].get("value") != 0.0:
        rep.fail("feh_lock_value", dict(state=key, value=F["feh"].get("value")))
    # blurbs
    n_f = len(F["filter"]["available"]); n_m = len(F["model"]["available"])
    if F["filter"]["blurb"] != f"{n_f} filter" + ("" if n_f == 1 else "s"): rep.fail("filter_blurb", dict(state=key, blurb=F["filter"]["blurb"]))
    want_m = F["model"]["available"][0] if n_m == 1 else (f"{n_m} models" if n_m else "—")
    if F["model"]["blurb"] != want_m: rep.fail("model_blurb", dict(state=key, blurb=F["model"]["blurb"], want=want_m))
    if F["model"]["locked"] or F["xi"]["locked"]: rep.fail("never_lock", dict(state=key))

# ------------------------------------------------------------------ main
def run_law(law, caps, engine, results, rep_limit, typed_level):
    t0 = time.time()
    engine.call("__setCaps", caps)
    ev = lambda state: engine.call("__ev", state)
    grids = flatten(caps); ref = Ref(grids)
    rep = Report(law, rep_limit); vocab = {}; avail = Avail(ev)
    codes = [f["code"] for f in caps]
    models = []                          # display names in first-appearance order (the dropdown order)
    for g in grids:
        if g["model"] not in models: models.append(g["model"])
    xis = sorted({g["xi"] for g in grids})
    combos = {(g["filter"], g["model"], g["xi"]) for g in grids}
    by_filter = {}
    for g in grids: by_filter.setdefault(g["filter"], []).append(g)

    # ---- map properties
    for name in models:
        ks = {g["model_key"] for g in grids if g["model"] == name}
        if len(ks) != 1: rep.fail("map_display_name_keys", dict(model=name, keys=sorted(ks)))
    if law == "quad":
        for c in JWST_CODES:
            if c in codes: rep.fail("map_quad_has_jwst", dict(code=c))
        if JWST_MODEL in models: rep.fail("map_quad_has_phoenix_ne", {})
    else:
        for c in JWST_CODES:
            gs = by_filter.get(c, [])
            if len(gs) != 1 or gs[0]["model"] != JWST_MODEL or gs[0]["model_key"] != JWST_MODEL or gs[0]["xi"] != JWST_XI \
               or not gs[0]["feh_fixed"] or (gs[0]["teff_min"], gs[0]["teff_max"]) != (2400, 7800) or (gs[0]["logg_min"], gs[0]["logg_max"]) != (3.0, 5.5):
                rep.fail("map_jwst_grid", dict(code=c, grids=gs))
        other_keys = {g["model_key"] for g in grids if g["model"] != JWST_MODEL}
        if JWST_MODEL in other_keys: rep.fail("map_phoenix_ne_key_shared", {})
    if models and models[0] != FIRST_MODEL: rep.fail("map_first_model", dict(first=models[0]))

    # ---- A. the evaluator, exhaustively over the discrete fields, every anchor
    n_states = 0
    for flt in [""] + codes:
        for mdl in [""] + models:
            for xi in [""] + [fmt_xi(x) for x in xis]:
                for anchor in (None, "model", "xi"):
                    state = read_state(new_form(flt, mdl, xi), anchor)
                    check_state(law, state, ev(state), ref.evaluate(state), rep, vocab, avail); n_states += 1
    # ---- A'. with typed values (teff, logg, feh), no anchor
    # Values chosen against the published ranges: below every table, inside
    # PHOENIX-COND only, inside PHOENIX-COND and PHOENIX-NE, inside all, above
    # PHOENIX-NE, inside ATLAS only, above every table; and likewise for
    # log g and [Fe/H].
    TEFFS = ["2000", "2350", "3000", "5800", "7900", "20000", "60000"]
    LOGGS = ["2.0", "4.5", "5.25", "7.0"]
    FEHS = ["-0.3", "0.0", "0.5", "2.0"]
    typed = []
    if typed_level >= 1:
        typed += [(t, "", "") for t in TEFFS] + [("", l, "") for l in LOGGS] + [("", "", f) for f in FEHS]
    if typed_level >= 2:
        typed += [("3000", "7.0", ""), ("2000", "", "-0.3"), ("", "7.0", "2.0"), ("5800", "4.5", "0.5"),
                  ("7900", "5.25", "-0.3"), ("60000", "2.0", "2.0"), ("3000", "4.5", "-0.3"), ("20000", "4.5", "0.0")]
    n_typed = 0
    for teff, logg, feh in typed:
        for flt in [""] + codes:
            for mdl in [""] + models:
                for xi in [""] + [fmt_xi(x) for x in xis]:
                    state = read_state(new_form(flt, mdl, xi, teff, logg, feh), None)
                    check_state(law, state, ev(state), ref.evaluate(state), rep, vocab, avail); n_typed += 1

    # ---- B. settling and the moves, from every real state and the default
    def settled(flt, mdl, xi, feh=""):
        form = new_form(flt, mdl, xi, feh=feh); settle(form, None, ev); return form
    def expect_note(origin, final, anchor, F1):
        """The decided wording, computed here from the map."""
        model_moved = origin["model"] != "" and origin["model"] != final["model"] and anchor != "model"
        xi_moved = origin["xi"] != "" and origin["xi"] != final["xi"] and anchor != "xi"
        feh_aside = final["fehLocked"] and origin["feh"] != "" and float(origin["feh"]) != 0
        text = ""
        if model_moved and final["model"] == "":
            text = f"No model available for filter = {F1}."
        elif model_moved:
            # the models that would do at the settled velocity, in dropdown order
            feh = None if final["feh"] == "" else float(final["feh"])
            would = [m for m in models if any(
                g["model"] == m and (final["xi"] == "" or g["xi"] == float(final["xi"]))
                and (feh is None or g["feh_fixed"] or g["feh_min"] <= feh <= g["feh_max"]) for g in by_filter[F1])]
            xi_part = f" at ξ = {final['xi']} km/s" if (xi_moved and final["xi"] != "") else ""
            lst = final["model"] if len(would) <= 1 else ", ".join(would[:-1]) + " or " + would[-1]
            text = f"Filter {F1} requires model {lst}{xi_part}."
        elif xi_moved:
            text = f"Filter {F1} requires ξ = {final['xi']} km/s."
        if feh_aside:
            table = (f"the {final['model']} table" if final["model"] else "the selected table") + \
                    (f" at ξ = {final['xi']} km/s" if final["xi"] != "" and float(final["xi"]) != 2 else "")
            text += (" " if text else "") + f"[Fe/H] {origin['feh']} replaced by 0.0: {table} is solar-only."
        return text if text else None
    starts = [("", DEFAULT_MODEL, "")] + sorted(combos, key=lambda c: (codes.index(c[0]), models.index(c[1]), c[2]))
    deepest = 0; n_trans = 0; n_notes = 0; kept_xi = 0; moved_xi = 0
    for (F0, M0, X0) in starts:
        base = settled(F0, M0, fmt_xi(X0) if X0 != "" else "")
        if F0 != "" and (base["filter"], base["model"], base["xi"]) != (F0, M0, fmt_xi(X0)):
            rep.fail("start_state_not_stable", dict(start=(F0, M0, X0), settled=(base["filter"], base["model"], base["xi"]))); continue
        # choose every other filter
        for F1 in codes:
            if F1 == F0: continue
            for feh_typed in ([""] if base["feh_disabled"] else ["", "0.3"]):
                form = dict(base); form["filter"] = F1
                if feh_typed: form["feh"] = feh_typed
                passes, origin, final = settle(form, "filter", ev); n_trans += 1
                deepest = max(deepest, passes)
                if passes >= 6: rep.fail("settle_cap_hit", dict(start=(F0, M0, X0), chose=F1))
                if final["filter"] != F1: rep.fail("filter_not_kept", dict(start=(F0, M0, X0), chose=F1, final=final))
                if final["model"] == "" or final["xi"] == "" or (F1, final["model"], float(final["xi"])) not in combos:
                    rep.fail("settled_state_not_a_table", dict(start=(F0, M0, X0), chose=F1, final=final)); continue
                # decision (d): a setting moves only when the chosen filter has no table at it
                has_model = any(g["model"] == base["model"] for g in by_filter[F1])
                has_xi = any(g["xi"] == float(base["xi"]) for g in by_filter[F1])
                both = (F1, base["model"], float(base["xi"])) in combos
                if both:
                    if final["model"] != base["model"] or final["xi"] != base["xi"]:
                        rep.fail("moved_without_need", dict(start=(F0, M0, X0), chose=F1, final=final))
                else:
                    if has_model and final["model"] != base["model"]: rep.fail("model_moved_though_served", dict(start=(F0, M0, X0), chose=F1, final=final))
                    if has_xi and final["xi"] != base["xi"]: rep.fail("xi_moved_though_served", dict(start=(F0, M0, X0), chose=F1, final=final))
                    if not has_model:
                        first = next(m for m in models if any(g["model"] == m and (has_xi and g["xi"] == float(base["xi"]) or not has_xi) for g in by_filter[F1]))
                        if final["model"] != first: rep.fail("model_not_first_selectable", dict(start=(F0, M0, X0), chose=F1, final=final, expected=first))
                        if FIRST_MODEL in {g["model"] for g in by_filter[F1]} and final["model"] != FIRST_MODEL:
                            rep.fail("model_not_atlas_when_served", dict(start=(F0, M0, X0), chose=F1, final=final))
                    if not has_xi:
                        first_xi = min(g["xi"] for g in by_filter[F1] if (not has_model) or g["model"] == base["model"])
                        if final["xi"] != fmt_xi(first_xi): rep.fail("xi_not_first_selectable", dict(start=(F0, M0, X0), chose=F1, final=final, expected=fmt_xi(first_xi)))
                    if has_xi: kept_xi += 1
                    else: moved_xi += 1
                # the note
                got = engine.call("__note", origin, final, "filter"); n_notes += 1
                want = expect_note(origin, final, "filter", F1)
                if got["note"] != want:
                    rep.fail("note_wording", dict(start=(F0, M0, X0), chose=F1, feh=feh_typed, js=got["note"], expected=want))
                elif want is not None:
                    if got["shown"] != want: rep.fail("note_not_shown", dict(start=(F0, M0, X0), chose=F1))
                    # lifetime: a refresh that moves nothing keeps it; a changed key clears it
                    again = engine.call("__noteAgain", final, None)
                    if again["note"] != want: rep.fail("note_not_kept", dict(start=(F0, M0, X0), chose=F1))
        # choose every selectable model and velocity: nothing else may move
        for anchor, field in (("model", "model"), ("xi", "xi")):
            f = ev(read_state(base, None))["fields"][field]
            for o in f["options"]:
                if not o["available"]: continue
                v = o["value"] if field == "model" else js_num(o["value"])
                if v == base[field]: continue
                form = dict(base); form[field] = v
                passes, origin, final = settle(form, anchor, ev); n_trans += 1; deepest = max(deepest, passes)
                other = "xi" if field == "model" else "model"
                if final["filter"] != base["filter"] or final[field] != v or final[other] != base[other]:
                    rep.fail(f"{field}_choice_moved_something", dict(start=(F0, M0, X0), chose=v, final=final))
                if base["filter"] and (final["model"] == "" or final["xi"] == "" or (final["filter"], final["model"], float(final["xi"])) not in combos):
                    rep.fail("settled_state_not_a_table", dict(start=(F0, M0, X0), chose=(field, v), final=final))
                got = engine.call("__note", origin, final, anchor)
                if got["note"] is not None: rep.fail("note_after_plain_choice", dict(start=(F0, M0, X0), chose=(field, v), note=got["note"]))
        # typed temperatures: the Phase 2 path, still consistent after Phase 3
        if F0 == "": continue
        for teff in ("2000", "3000", "5800", "7900", "20000", "60000"):
            form = dict(base); form["teff"] = teff
            passes, origin, final = settle(form, "teff", ev); n_trans += 1; deepest = max(deepest, passes)
            got = engine.call("__note", origin, final, "teff")
            if final["model"] == "":
                if not any(g["teff_min"] <= float(teff) <= g["teff_max"] for g in by_filter[F0]):
                    want = f"No model available for filter = {F0} and Teff = {teff}."
                    if got["note"] != want: rep.fail("typed_no_model_note", dict(start=(F0, M0, X0), teff=teff, js=got["note"], expected=want))
                else:
                    rep.fail("typed_lost_model", dict(start=(F0, M0, X0), teff=teff, final=final))
                continue
            if final["xi"] == "" or (F0, final["model"], float(final["xi"])) not in combos:
                rep.fail("typed_settled_not_a_table", dict(start=(F0, M0, X0), teff=teff, final=final)); continue
            g = next(g for g in by_filter[F0] if g["model"] == final["model"] and g["xi"] == float(final["xi"]))
            if not (g["teff_min"] <= float(teff) <= g["teff_max"]):
                if any(g2["teff_min"] <= float(teff) <= g2["teff_max"] for g2 in by_filter[F0]):
                    rep.fail("typed_not_moved_to_covering_table", dict(start=(F0, M0, X0), teff=teff, final=final))
            moved = final["model"] != base["model"] or final["xi"] != base["xi"]
            if moved and (got["note"] is None or not got["note"].startswith(f"Teff at {teff} K ")):
                rep.fail("typed_note", dict(start=(F0, M0, X0), teff=teff, final=final, note=got["note"]))
            if not moved and got["note"] is not None:
                rep.fail("typed_note_without_move", dict(start=(F0, M0, X0), teff=teff, note=got["note"]))

    # ---- C. order independence from the default state
    default = settled("", DEFAULT_MODEL, "")
    n_orders_ok = 0; n_targets = 0; unreachable = []; order_hist = {}
    for (F, M, X) in sorted(combos):
        n_targets += 1; landed = 0; permitted = []
        for order in itertools.permutations(("filter", "model", "xi")):
            form = dict(default); ok_ = True
            for step in order:
                v = {"filter": F, "model": M, "xi": fmt_xi(X)}[step]
                if form[step] == v: continue
                f = ev(read_state(form, None))["fields"][step]
                sel_ok = any((o.get("code") if step == "filter" else (o["value"] if step == "model" else js_num(o["value"]))) == v and o["available"] for o in f["options"])
                if not sel_ok: ok_ = False; break
                form[step] = v; settle(form, step, ev)
            if not ok_: continue
            permitted.append("".join(s[0] for s in order))
            if (form["filter"], form["model"], form["xi"]) == (F, M, fmt_xi(X)): landed += 1
            else: rep.fail("order_landed_elsewhere", dict(target=(F, M, X), order=order, final=snapshot(form)))
        if not permitted: unreachable.append((F, M, X)); rep.fail("unreachable_from_default", dict(target=(F, M, X)))
        else: n_orders_ok += 1
        if "fmx" not in permitted and "fxm" not in permitted: rep.fail("not_reachable_filter_first", dict(target=(F, M, X), permitted=permitted))
        order_hist[len(permitted)] = order_hist.get(len(permitted), 0) + 1

    # ---- D. JWST
    jwst = {}
    if law != "quad":
        f = ev(read_state(default, None))["fields"]["filter"]
        for c in JWST_CODES:
            o = next((o for o in f["options"] if o["code"] == c), None)
            if o is None or not o["available"]: rep.fail("jwst_not_selectable_from_default", dict(code=c, option=o)); continue
            form = dict(default); form["filter"] = c
            passes, origin, final = settle(form, "filter", ev)
            if (final["model"], final["xi"], final["fehLocked"]) != (JWST_MODEL, fmt_xi(JWST_XI), True):
                rep.fail("jwst_one_step", dict(code=c, final=final))
            got = engine.call("__note", origin, final, "filter")
            want = f"Filter {c} requires model {JWST_MODEL} at ξ = {fmt_xi(JWST_XI)} km/s."
            if got["note"] != want: rep.fail("jwst_note", dict(code=c, js=got["note"], expected=want))
            # leaving for every ordinary filter keeps 1 km/s when that filter has a table at 1
            kept = moved = 0
            for F1 in codes:
                if F1 in JWST_CODES: continue
                form2 = dict(final); form2 = new_form(F1, final["model"], final["xi"], feh="0.0"); form2["feh_disabled"] = True
                settle(form2, "filter", ev)
                has1 = any(g["xi"] == JWST_XI for g in by_filter[F1])
                if has1 and form2["xi"] != fmt_xi(JWST_XI): rep.fail("jwst_leave_xi_not_kept", dict(code=c, chose=F1, final=snapshot(form2)))
                if form2["model"] == JWST_MODEL: rep.fail("jwst_leave_model_stuck", dict(code=c, chose=F1, final=snapshot(form2)))
                kept += has1; moved += (not has1)
            jwst[c] = dict(passes=passes, kept_1kms=kept, moved=moved)

    # ---- write the vocabulary
    with open(os.path.join(results, f"layer6_tags_{law}.txt"), "w", encoding="utf-8") as fh:
        fh.write(f"# {law}: {len(vocab)} distinct tags over {sum(vocab.values())} tagged options\n")
        for tag, n in sorted(vocab.items(), key=lambda kv: (-kv[1], kv[0])): fh.write(f"{n:8d}  {tag}\n")
    return dict(filters=len(codes), models=models, velocities=[fmt_xi(x) for x in xis], grids=len(grids),
                discrete_states=n_states, typed_states=n_typed, tags=sum(vocab.values()), distinct_tags=len(vocab),
                transitions=n_trans, notes_checked=n_notes, deepest_settle=deepest,
                xi_kept_on_filter_change=kept_xi, xi_moved_on_filter_change=moved_xi,
                order_targets=n_targets, order_reachable=n_orders_ok, permitted_orders_histogram=order_hist,
                jwst=jwst, failures=rep.counts, examples=rep.failures, seconds=round(time.time() - t0, 1))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--v5", required=True); ap.add_argument("--results", default=os.path.join(here, "results"))
    ap.add_argument("--laws", default=",".join(LAWS)); ap.add_argument("--engine", choices=["auto", "mini-racer", "node"], default="auto")
    ap.add_argument("--typed", type=int, choices=[0, 1, 2], default=2, help="how many typed-value combinations to sweep (2 = all)")
    ap.add_argument("--examples", type=int, default=25); ap.add_argument("--dump-caps", nargs=2, metavar=("LAW", "PATH"))
    a = ap.parse_args()
    if a.dump_caps:
        dump_caps(a.v5, a.dump_caps[0], a.dump_caps[1]); return 0
    os.makedirs(a.results, exist_ok=True)
    page = os.path.join(a.v5, "static", "index.html")
    src = open(page, encoding="utf-8").read()
    parts = {name: extract_function(src, name) for name in PAGE_FUNCTIONS}
    source = JS_PREAMBLE + "\n".join(parts.values()) + JS_HELPERS
    engine = make_engine(source, a.engine)
    if engine is None:
        print("layer 6: no JavaScript engine. Install one:  pip install mini-racer   (or put node on the PATH)"); return 3
    summary = {"engine": engine.name, "page": page, "page_md5": hashlib.md5(src.encode("utf-8")).hexdigest(),
               "extracted": {n: dict(chars=len(t), lines=t.count("\n") + 1, md5=hashlib.md5(t.encode("utf-8")).hexdigest()) for n, t in parts.items()}}
    worst = 0
    for law in a.laws.split(","):
        caps = capability_map(a.v5, law, a.results)
        r = run_law(law, caps, engine, a.results, a.examples, a.typed); summary[law] = r
        nf = sum(r["failures"].values())
        print(f"layer 6, {law}: {r['filters']} filters, {r['grids']} grids; {r['discrete_states'] + r['typed_states']} states, "
              f"{r['tags']} tags ({r['distinct_tags']} distinct), {r['transitions']} transitions, deepest settle {r['deepest_settle']}, "
              f"{r['order_reachable']}/{r['order_targets']} combinations reachable; {nf} failures" +
              (f"  e.g. {json.dumps(next(iter(r['examples'].values()))[0], default=str)[:300]}" if nf else "") + f"  [{r['seconds']} s, {engine.name}]")
        worst = max(worst, nf)
    with open(os.path.join(a.results, "layer6_page.json"), "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=1, default=str)
    engine.close()
    return 2 if worst else 0

if __name__ == "__main__":
    sys.exit(main())
