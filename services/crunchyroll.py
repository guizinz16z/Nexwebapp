# -*- coding: utf-8 -*-
import cloudscraper, json, uuid, re

scraper = cloudscraper.create_scraper(browser={'browser':'chrome','platform':'android','mobile':True})

def _ua():
    return ("Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/137.0.0.0 Mobile Safari/537.36")
def _gen_uuid(): return str(uuid.uuid4())
def _canon(n): return n.strip().lower()
def _is_cr(d, n): return _canon(n) in {"etp_rt","etp_jwt","device_id"} or "crunchyroll" in str(d).lower()

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
        if not _is_cr(p[0], n): continue
        out.append({"name": n, "value": p[6]})
    return out

def _json(content):
    try: data = json.loads(content)
    except: return []
    if isinstance(data, dict): data = data.get("cookies") or data.get("items") or [data]
    if not isinstance(data, list): return []
    out = []
    for c in data:
        if not isinstance(c, dict): continue
        n = _canon(c.get("name",""))
        if not _is_cr(c.get("domain",""), n): continue
        out.append({"name": n, "value": c.get("value","")})
    return out

def _raw(content):
    pat = re.compile(r'(?:["\'])?(?P<name>etp_rt|etp_jwt|device_id)(?:["\'])?\s*[:=]\s*(?P<value>"[^"]*"|\'[^\']*\'|[^;\s]+)', re.I)
    out = []
    for m in pat.finditer(content):
        n = _canon(m.group("name")); v = m.group("value")
        if len(v) >= 2 and v[0] == v[-1] and v[0] in {"'",'"'}: v = v[1:-1]
        else: v = v.rstrip(",")
        out.append({"name": n, "value": v})
    return out

def extract_cookies(content):
    for fn in (_netscape, _json, _raw):
        e = fn(content)
        if e: break
    else: return None
    d = {}
    for x in e: d[x["name"]] = x["value"]
    return d if ("etp_rt" in d or "etp_jwt" in d) else None

def _validate(cookies):
    if "etp_jwt" in cookies:
        h = {"User-Agent": _ua(), "Authorization": f"Bearer {cookies['etp_jwt']}"}
        try:
            r = scraper.get("https://beta-api.crunchyroll.com/accounts/v1/me", headers=h, timeout=15)
            if r.status_code == 200 and r.json().get("external_id"):
                return True, cookies["etp_jwt"], r.json()
        except: pass
        if "etp_rt" not in cookies:
            return False, None, "JWT inválido e sem refresh token"
    if "etp_rt" not in cookies: return False, None, "Sem etp_rt"
    did = _gen_uuid()
    h = {"User-Agent": _ua(),
         "Accept": "application/json, text/plain, */*",
         "Content-Type": "application/x-www-form-urlencoded",
         "Authorization": "Basic bm9haWhkZXZtXzZpeWcwYThsMHE6",
         "Origin": "https://www.crunchyroll.com",
         "Referer": "https://www.crunchyroll.com/activate",
         "ETP-Anonymous-Id": did}
    data = f"device_id={did}&device_type=Chrome%20on%20Android&grant_type=etp_rt_cookie"
    try:
        r = scraper.post("https://www.crunchyroll.com/auth/v1/token", headers=h, data=data,
                         cookies={"etp_rt": cookies["etp_rt"]}, timeout=15)
        if r.status_code != 200: return False, None, "Falha ao obter access_token"
        j = r.json()
        return True, j.get("access_token"), None
    except Exception as e:
        return False, None, str(e)

def _activate(access_token, user_code):
    h = {"User-Agent": _ua(),
         "Accept": "application/json, text/plain, */*",
         "Authorization": f"Bearer {access_token}",
         "Content-Type": "application/json",
         "Origin": "https://www.crunchyroll.com",
         "Referer": "https://www.crunchyroll.com/activate",
         "ETP-Anonymous-Id": _gen_uuid()}
    try:
        r = scraper.post("https://www.crunchyroll.com/auth/v1/device",
                         headers=h, json={"user_code": user_code}, timeout=15)
        if r.status_code == 200: return True, None
        return False, r.json() if r.headers.get("content-type","").startswith("application/json") else {"raw": r.text[:200]}
    except Exception as e:
        return False, {"error": str(e)}

def run_activation(cookie_content: str, tv_code: str, **_):
    cookies = extract_cookies(cookie_content or "")
    if not cookies:
        return {"success": False, "error": "Não foi possível extrair tokens (etp_rt/etp_jwt)"}
    ok, token, info = _validate(cookies)
    if not ok:
        return {"success": False, "error": info or "Cookie inválido"}
    if not token:
        return {"success": False, "error": "Access token não obtido"}
    code = tv_code.strip().upper()
    ok, err = _activate(token, code)
    if ok:
        return {"success": True, "message": "TV Crunchyroll ativada", "code": code}
    return {"success": False, "error": f"Código rejeitado: {err}"}