# -*- coding: utf-8 -*-
"""Netflix TV activation via cookie (extraído do seu TVBot.py)"""
import re, requests, urllib.parse
from urllib3.exceptions import InsecureRequestWarning
requests.packages.urllib3.disable_warnings(category=InsecureRequestWarning)

TIMEOUT = 20
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

ALL = {"netflixid", "securenetflixid", "nfvdid", "optanonconsent"}
CANON = {n.lower(): n for n in ("NetflixId", "SecureNetflixId", "nfvdid", "OptanonConsent")}

def _canon(n): return CANON.get(str(n or "").strip().lower(), str(n or "").strip())
def _is_nf(d, n): return _canon(n).lower() in ALL or "netflix." in str(d or "").lower()

def _netscape(raw):
    out = []
    for line in raw.splitlines():
        if line.startswith("#HttpOnly_"): line = line[len("#HttpOnly_"):]
        p = line.split("\t")
        if len(p) < 7: p = re.split(r"\s+", line, maxsplit=6)
        if len(p) < 7: continue
        if p[1].upper() not in ("TRUE","FALSE") or p[3].upper() not in ("TRUE","FALSE"): continue
        if not re.match(r"^-?\d+(?:\.\d+)?$", p[4].strip()): continue
        n = _canon(p[5])
        if not _is_nf(p[0], n): continue
        out.append({"name": n, "value": p[6]})
    return out

def _json(content):
    import json
    try: data = json.loads(content)
    except: return []
    if isinstance(data, dict): data = data.get("cookies") or data.get("items") or [data]
    if not isinstance(data, list): return []
    out = []
    for c in data:
        if not isinstance(c, dict): continue
        n = _canon(c.get("name", ""))
        if not _is_nf(c.get("domain", ""), n): continue
        out.append({"name": n, "value": c.get("value", "")})
    return out

def _raw(content):
    pat = re.compile(r"(?:['\"])?(?P<name>" + "|".join(sorted(ALL, key=len, reverse=True)) +
                     r")(?:['\"])?\s*(?:=|:)\s*(?P<value>\"[^\"]*\"|'[^']*'|[^;\s]+)", re.I)
    out = []
    for m in pat.finditer(content):
        n = _canon(m.group("name")); v = m.group("value")
        if len(v) >= 2 and v[0] == v[-1] and v[0] in {"'", '"'}: v = v[1:-1]
        else: v = v.rstrip(",")
        out.append({"name": n, "value": v})
    return out

def extract_cookies(content):
    for fn in (_json, _netscape, _raw):
        e = fn(content)
        if e: break
    else: return None
    d = {}
    for x in e:
        if x["name"] not in d: d[x["name"]] = x["value"]
    return d if "NetflixId" in d else None

def _validate(cd):
    s = requests.Session(); s.cookies.update(cd)
    h = {"User-Agent": UA, "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
         "Accept-Language": "en-US,en;q=0.9"}
    try:
        r = s.get("https://www.netflix.com/account/membership", headers=h, timeout=TIMEOUT, verify=False)
        if r.status_code != 200: return False, None, None
        c = re.search(r'"currentCountry"\s*:\s*"([^"]+)"', r.text) or re.search(r'"countryOfSignup":\s*"([^"]+)"', r.text)
        if not c: return False, None, None
        p = re.search(r'"localizedPlanName"\s*:\s*"([^"]+)"', r.text)
        return True, c.group(1), p.group(1) if p else "Unknown"
    except: return False, None, None

def _extract_auth(html):
    pats = [r'name="authURL"\s+value="([^"]+)"',
            r'authURL["\']?\s*[:=]\s*["\']([^"]+)["\']',
            r'authURL=([^&\s"\']+)',
            r'value="(c1\.[^"]+)"']
    for p in pats:
        m = re.search(p, html)
        if m: return urllib.parse.unquote(m.group(1))
    return None

ERROR_PATS = [r"that code wasn'?t right", r"code (is )?(incorrect|invalid|wrong)",
              r"try again", r"c[oó]digo (es |que ingresaste |no es |incorrecto|inv[aá]lido)",
              r"c[oó]digo (est[aá] |n[aã]o est[aá] |incorreto|inv[aá]lido)", r"tente novamente"]

def _is_err(t):
    tl = t.lower()
    return any(re.search(p, tl) for p in ERROR_PATS)

def _activate(s, code):
    url = "https://www.netflix.com/tv8"
    h = {"User-Agent": UA, "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
         "Accept-Language": "en-US,en;q=0.9"}
    try:
        r = s.get(url, headers=h, timeout=TIMEOUT, verify=False)
        if r.status_code != 200: return False, "Página Netflix TV indisponível"
    except: return False, "Falha de conexão"
    auth = _extract_auth(r.text)
    if not auth:
        fb = re.search(r'c1\.[a-zA-Z0-9%+=/]+', r.text)
        if fb: auth = fb.group(0)
        else: return False, "Não foi possível carregar a página de ativação"
    form = {"flow": "websiteSignUp", "authURL": auth,
            "flowMode": "enterTvLoginRendezvousCode",
            "withFields": "tvLoginRendezvousCode,isTvUrl2",
            "code": code, "tvLoginRendezvousCode": code, "action": "nextAction"}
    ph = {**h, "Content-Type": "application/x-www-form-urlencoded",
          "Referer": "https://www.netflix.com/tv8", "Origin": "https://www.netflix.com"}
    try:
        r = s.post(url, data=form, headers=ph, timeout=TIMEOUT, verify=False, allow_redirects=True)
    except: return False, "Falha na requisição"
    final = getattr(r, "url", url)
    if "/tv/out/success" in final.lower(): return True, None
    import html as hm
    t = r.text
    t = re.sub(r'<script[^>]*>.*?</script>', '', t, flags=re.DOTALL | re.I)
    t = re.sub(r'<style[^>]*>.*?</style>', '', t, flags=re.DOTALL | re.I)
    t = re.sub(r'<[^>]+>', ' ', t)
    t = hm.unescape(t); t = re.sub(r'\s+', ' ', t).strip()
    if _is_err(t): return False, "Código inválido ou expirado"
    return False, "Resposta desconhecida"

def run_activation(cookie_content: str, tv_code: str, **_):
    code = re.sub(r"\D", "", tv_code or "")
    if len(code) != 8:
        return {"success": False, "error": "Código Netflix deve ter 8 dígitos"}
    cd = extract_cookies(cookie_content or "")
    if not cd:
        return {"success": False, "error": "Cookie Netflix inválido (NetflixId não encontrado)"}
    ok, country, plan = _validate(cd)
    if not ok:
        return {"success": False, "error": "Cookie expirado ou inválido"}
    s = requests.Session(); s.cookies.update(cd)
    ok, err = _activate(s, code)
    if ok:
        return {"success": True, "message": "TV Netflix ativada", "code": code,
                "country": country, "plan": plan}
    return {"success": False, "error": err, "country": country, "plan": plan}