# -*- coding: utf-8 -*-
import re, json, base64, uuid, requests

TIMEOUT = 30
ENDPOINTS = {
    "amer":  {"validate":"https://default.any-amer.prd.api.hbomax.com/authentication/linkDevice/validate",
              "connect": "https://default.any-amer.prd.api.hbomax.com/authentication/linkDevice/connect"},
    "emea":  {"validate":"https://default.any-emea.prd.api.hbomax.com/authentication/linkDevice/validate",
              "connect": "https://default.any-emea.prd.api.hbomax.com/authentication/linkDevice/connect"},
    "latam": {"validate":"https://default.any-latam.prd.api.hbomax.com/authentication/linkDevice/validate",
              "connect": "https://default.any-latam.prd.api.hbomax.com/authentication/linkDevice/connect"},
    "apac":  {"validate":"https://default.any-apac.prd.api.hbomax.com/authentication/linkDevice/validate",
              "connect": "https://default.any-apac.prd.api.hbomax.com/authentication/linkDevice/connect"},
}

def _decode_jwt(tok):
    try:
        p = tok.split(".")[1]; p += "=" * (4 - len(p) % 4)
        return json.loads(base64.b64decode(p))
    except: return None

def extract_st(content):
    m = re.search(r'^st:\s*(eyJ[A-Za-z0-9_\-\.]+)', content, re.MULTILINE)
    if m: return m.group(1)
    m = re.search(r'st=([^;\s]+)', content)
    if m and len(m.group(1).split(".")) == 3: return m.group(1)
    m = re.search(r'(eyJ[A-Za-z0-9_\-\.]+)', content)
    if m and len(m.group(1).split(".")) == 3: return m.group(1)
    return None

def _region(tok):
    d = _decode_jwt(tok)
    if d:
        s = d.get("subdivision","")
        for r in ("amer","emea","latam","apac"):
            if r in s: return r
    return "amer"

def _user_info(st, region):
    url = f"https://default.beam-{region}.prd.api.hbomax.com/users/me"
    h = {"accept":"*/*","content-type":"application/json","cookie":f"st={st}",
         "origin":"https://play.hbomax.com","referer":"https://play.hbomax.com/",
         "user-agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
         "x-disco-client":"WEB:10:hbomax:7.4.0",
         "x-disco-params":"realm=bolt,bid=beam,features=ar",
         "x-device-info":"hbomax/7.4.0 (desktop/desktop; Windows/10; test/test)"}
    try:
        r = requests.get(url, headers=h, timeout=TIMEOUT)
        return r.json() if r.status_code == 200 else None
    except: return None

def _validate(st, region):
    d = _user_info(st, region)
    if not d: return False, None
    a = (d.get("data") or {}).get("attributes") or {}
    email = a.get("username","Unknown")
    if email and "@" not in email: email = f"{email}@hbomax.com"
    return True, {"email": email, "country": a.get("verifiedHomeTerritory","Unknown")}

def _device_info():
    info = {"deviceId": str(uuid.uuid4()), "deviceName":"Chrome","deviceModel":"Windows",
            "deviceType":"BROWSER","osVersion":"10.0.0","appVersion":"7.4.0",
            "manufacturer":"Google","screenWidth":1920,"screenHeight":1080,
            "language":"en-US","timezone":"America/New_York"}
    return base64.b64encode(json.dumps(info).encode()).decode()

def _activate(st, code, region):
    cid = f"web_{uuid.uuid4().hex[:16]}"
    h = {"accept":"*/*","content-type":"application/json","cookie":f"st={st}",
         "origin":"https://auth.hbomax.com","referer":"https://auth.hbomax.com/",
         "user-agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
         "x-disco-client":"WEB:10:hbomax:7.4.0",
         "x-disco-params":f"realm=bolt,bid=beam,features=ar,clientId={cid}",
         "x-disco-device-info": _device_info(),
         "x-device-info":"hbomax/7.4.0 (desktop/desktop; Windows/10; test/test)",
         "sec-ch-ua":'"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
         "sec-ch-ua-mobile":"?0","sec-ch-ua-platform":'"Windows"',
         "sec-fetch-dest":"empty","sec-fetch-mode":"cors","sec-fetch-site":"same-site"}
    try:
        r1 = requests.post(ENDPOINTS[region]["validate"], headers=h, json={"linkingCode": code}, timeout=TIMEOUT)
        if r1.status_code not in (200,204):
            return False, "invalid_code" if r1.status_code == 400 else "unknown_error"
        r2 = requests.post(ENDPOINTS[region]["connect"], headers=h, json={"linkingCode": code}, timeout=TIMEOUT)
        if r2.status_code in (200,204): return True, "success"
        return False, "activation_failed"
    except Exception as e:
        return False, f"exception: {e}"

def run_activation(cookie_content: str, tv_code: str, **_):
    st = extract_st(cookie_content or "")
    if not st: return {"success": False, "error": "Token 'st' não encontrado"}
    region = _region(st)
    ok, info = _validate(st, region)
    if not ok: return {"success": False, "error": "Cookie expirado ou inválido"}
    ok, status = _activate(st, tv_code.strip(), region)
    if ok:
        return {"success": True, "message": "TV HBO Max ativada",
                "account": info.get("email"), "country": info.get("country"), "region": region.upper()}
    msg = {"invalid_code":"Código inválido","expired_code":"Código expirado",
           "activation_failed":"Falha ao conectar","unknown_error":"Erro desconhecido"}
    return {"success": False, "error": msg.get(status, status)}