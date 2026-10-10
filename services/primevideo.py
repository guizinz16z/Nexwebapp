# -*- coding: utf-8 -*-
import re, json, requests
from urllib.parse import urlparse, parse_qs

AMZ_CBL_URL = "https://www.amazon.com/a/code"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
HDRS = {"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"}

def _normalize(raw):
    if not raw: return ""
    s = raw.strip()
    if s.startswith("[") and s.endswith("]"):
        try:
            arr = json.loads(s); lines = ["# Netscape HTTP Cookie File"]
            for c in arr:
                dom = c.get("domain", ".amazon.com")
                pfx = "#HttpOnly_" if c.get("httpOnly") and not dom.startswith("#HttpOnly_") else ""
                lines.append(f"{pfx}{dom}\tTRUE\t{c.get('path','/')}\t"
                             f"{'TRUE' if c.get('secure') else 'FALSE'}\t"
                             f"{int(c.get('expirationDate',0))}\t{c.get('name','')}\t{c.get('value','')}")
            return "\n".join(lines)
        except: pass
    if "=" in s and "\t" not in s:
        return "# Netscape HTTP Cookie File\n" + "\n".join(
            f".amazon.com\tTRUE\t/\tFALSE\t0\t{p.split('=',1)[0].strip()}\t{p.split('=',1)[1].strip()}"
            for p in s.split(";") if "=" in p)
    lines = ["# Netscape HTTP Cookie File"]
    for line in s.splitlines():
        line = line.strip()
        if not line or (line.startswith("#") and not line.startswith("#HttpOnly_")): continue
        p = line.split("\t")
        if len(p) >= 7 and p[5].strip(): lines.append(line)
    return "\n".join(lines) if len(lines) > 1 else s

def _parse_cookies(raw):
    ck = {}
    for line in (raw or "").splitlines():
        line = line.strip()
        if not line or (line.startswith("#") and not line.startswith("#HttpOnly_")): continue
        p = line.split("\t")
        if len(p) >= 7 and p[5].strip():
            ck[p[5].strip()] = "\t".join(p[6:]).strip().strip('"')
    return ck

def _amz_header(cd):
    pairs = []
    for k, v in cd.items():
        ak = re.sub(r"-main-av$", "-main", k)
        pairs += [f"{ak}={v}"] + ([f"{k}={v}"] if ak != k else [])
    return "; ".join(pairs)

def _validate(cd):
    if not any(k in cd for k in ("at-main","at-main-av","session-token")):
        return False, "Cookies essenciais ausentes"
    try:
        r = requests.get(AMZ_CBL_URL, headers={**HDRS, "Cookie": _amz_header(cd)},
                         allow_redirects=False, timeout=10)
        if r.status_code == 200 and ("cbl-input-code-form" in r.text or "cbl-registration-field" in r.text):
            return True, None
        if r.status_code in (301,302,307) and "signin" in r.headers.get("Location",""):
            return False, "Sessão expirada"
        return False, f"HTTP {r.status_code}"
    except Exception as e: return False, str(e)

def _pair(cd, tv_code):
    code = re.sub(r"[^A-Za-z0-9]", "", tv_code or "").upper()
    if len(code) != 6: return False, "Código deve ter 6 caracteres"
    s = requests.Session(); ck = _amz_header(cd); h = {**HDRS, "Cookie": ck}
    try: r = s.get(AMZ_CBL_URL, headers=h, allow_redirects=False, timeout=10)
    except Exception as e: return False, f"Falha ao conectar: {e}"
    if r.status_code in (301,302) and "signin" in r.headers.get("Location",""):
        return False, "Sessão Prime Video expirada"
    if r.status_code != 200: return False, f"Página CBL indisponível (HTTP {r.status_code})"
    csrf = re.search(r"name=['\"]csrfToken['\"][^>]*value=['\"]([^'\"]+)['\"]", r.text, re.I)
    if not csrf: return False, "CSRF não encontrado"
    lang = re.search(r"name=['\"]language['\"][^>]*value=['\"]([^'\"]+)['\"]", r.text, re.I)
    for k, v in s.cookies.get_dict().items(): ck += f"; {k}={v}"
    ph = {**h, "Cookie": ck, "Content-Type": "application/x-www-form-urlencoded",
          "Origin": "https://www.amazon.com", "Referer": AMZ_CBL_URL}
    try:
        pr = s.post(AMZ_CBL_URL, data={"csrfToken": csrf.group(1), "cbl-code": code,
                    "language": lang.group(1) if lang else "en_US"},
                    headers=ph, allow_redirects=False, timeout=12)
    except Exception as e: return False, f"Falha ao enviar código: {e}"
    loc = pr.headers.get("Location", "")
    st = parse_qs(urlparse(loc).query).get("cbl-status", [""])[0]
    if any(k in loc or k in st for k in ("success","successfully_authorized")):
        return True, "OK"
    if "invalid_code" in st or "invalid_code" in loc:
        return False, "Código inválido ou expirado"
    if "/ap/signin" in loc: return False, "Sessão expirada"
    return False, "Autorização falhou"

def run_activation(cookie_content: str, tv_code: str, **_):
    raw = _normalize(cookie_content or "")
    cd = _parse_cookies(raw)
    if not cd: return {"success": False, "error": "Cookie inválido"}
    ok, err = _validate(cd)
    if not ok: return {"success": False, "error": err or "Sessão inválida"}
    ok, dev = _pair(cd, tv_code)
    if ok: return {"success": True, "message": "Smart TV pareada", "device": dev}
    return {"success": False, "error": dev}