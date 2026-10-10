# -*- coding: utf-8 -*-
"""
ORION / NEX — Backend Flask (Netlify + Railway)
"""
import os, json, uuid, random
from datetime import datetime
from pathlib import Path
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS

from services import netflix, crunchyroll, hbomax, primevideo

BASE = Path(__file__).parent
VAULT = BASE / "vault"
HISTORY = BASE / "history.json"

SERVICES = {
    "Netflix":     {"module": netflix,     "folder":"netflix",     "icon":"N", "color":"net"},
    "Crunchyroll": {"module": crunchyroll, "folder":"crunchyroll", "icon":"C", "color":"crunchy"},
    "Spotify":     {"module": None,        "folder":"spotify",     "icon":"S", "color":"spotify"},
    "Surfshark":   {"module": None,        "folder":"surfshark",   "icon":"S", "color":"surf"},
    "HBO Max":     {"module": hbomax,      "folder":"hbomax",      "icon":"H", "color":"hbo"},
    "Prime Video": {"module": primevideo,  "folder":"primevideo",  "icon":"P", "color":"surf"},
}

for svc in SERVICES.values():
    (VAULT / svc["folder"]).mkdir(parents=True, exist_ok=True)

app = Flask(__name__, static_folder=None)
CORS(app, resources={r"/api/*": {"origins": "*"}})

# ---------- helpers ----------
def _load_history():
    if not HISTORY.exists(): return []
    try: return json.loads(HISTORY.read_text(encoding="utf-8"))
    except: return []

def _save_history(h):
    HISTORY.write_text(json.dumps(h, indent=2, ensure_ascii=False), encoding="utf-8")

def _log(record):
    h = _load_history(); h.insert(0, record)
    _save_history(h[:500])

def _count(folder):
    p = VAULT / folder
    if not p.exists(): return 0
    return len([f for f in p.iterdir() if f.suffix.lower() in (".txt",".json",".cookie")])

def _pick_cookie(service):
    folder = VAULT / SERVICES[service]["folder"]
    files = [f for f in folder.iterdir() if f.suffix.lower() in (".txt",".json",".cookie")]
    if not files: return None, None
    f = random.choice(files)
    try: return f.name, f.read_text(encoding="utf-8", errors="ignore")
    except: return None, None

def _stats():
    total = sum(_count(s["folder"]) for s in SERVICES.values())
    h = _load_history()
    today = datetime.now().strftime("%Y-%m-%d")
    today_ops = [r for r in h if r.get("timestamp","").startswith(today)]
    total_ok = sum(1 for r in h if r.get("success"))
    rate = round((total_ok / len(h) * 100), 1) if h else 0.0
    return {"activations_today": len(today_ops), "success_rate": rate,
            "cookies_active": total, "avg_time": 18}

# ---------- API ----------
@app.route("/")
def root():
    return jsonify({"app":"ORION / NEX API","status":"online","endpoints":["/api/stats","/api/stock","/api/history","/api/activate","/api/stock/upload"]})

@app.route("/api/stats")
def api_stats(): return jsonify(_stats())

@app.route("/api/stock")
def api_stock():
    out = []
    for name, meta in SERVICES.items():
        out.append({"name": name, "available": _count(meta["folder"]),
                    "icon": meta["icon"], "color": meta["color"], "status":"Saudável"})
    return jsonify(out)

@app.route("/api/history")
def api_history(): return jsonify(_load_history()[:200])

@app.route("/api/stock/upload", methods=["POST"])
def api_upload():
    service = request.form.get("service")
    if service not in SERVICES:
        return jsonify({"success": False, "error": "Serviço inválido"}), 400
    files = request.files.getlist("files")
    if not files:
        return jsonify({"success": False, "error": "Nenhum arquivo"}), 400
    folder = VAULT / SERVICES[service]["folder"]
    saved = 0
    for f in files:
        content = f.read().decode("utf-8", errors="ignore")
        if not content.strip(): continue
        safe = f.filename or f"cookie_{uuid.uuid4().hex[:8]}.txt"
        safe = "".join(c for c in safe if c.isalnum() or c in "._-") or f"cookie_{uuid.uuid4().hex[:6]}.txt"
        (folder / safe).write_text(content, encoding="utf-8")
        saved += 1
    return jsonify({"success": True, "saved": saved, "total": _count(SERVICES[service]["folder"])})

@app.route("/api/activate", methods=["POST"])
def api_activate():
    data = request.get_json(force=True) or {}
    service = data.get("service")
    tv_code = (data.get("tv_code") or "").strip()
    source = data.get("source", "stock")
    own_cookie = data.get("own_cookie", "")

    if service not in SERVICES:
        return jsonify({"success": False, "error": "Serviço desconhecido"}), 400
    if not tv_code:
        return jsonify({"success": False, "error": "Código da TV vazio"}), 400

    meta = SERVICES[service]
    if meta["module"] is None:
        return jsonify({"success": False, "error": f"Serviço '{service}' ainda não implementado"}), 501

    cookie_file = None
    cookie_content = own_cookie
    if source == "stock":
        cookie_file, cookie_content = _pick_cookie(service)
        if not cookie_content:
            return jsonify({"success": False, "error": "Estoque vazio para este serviço"}), 400

    started = datetime.now()
    try:
        result = meta["module"].run_activation(cookie_content, tv_code)
    except Exception as e:
        result = {"success": False, "error": f"Erro interno: {e}"}
    elapsed = int((datetime.now() - started).total_seconds())

    record = {
        "id": f"NX-{random.randint(10000,99999)}",
        "service": service, "code": tv_code, "source": source,
        "cookie_file": cookie_file, "success": bool(result.get("success")),
        "error": result.get("error"), "message": result.get("message"),
        "country": result.get("country"), "plan": result.get("plan"),
        "account": result.get("account"), "timestamp": datetime.now().isoformat(),
        "elapsed": elapsed,
    }
    _log(record)

    # Se sucesso e usou estoque, apaga o cookie usado
    if result.get("success") and source == "stock" and cookie_file:
        try: (VAULT / SERVICES[service]["folder"] / cookie_file).unlink()
        except: pass

    return jsonify(result)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)