"""
ARDINI Paylasim Servisi (FastAPI)
- /generate : urun bilgisinden Instagram aciklamasi + hashtag uretir (Claude)
- /publish  : foto URL + aciklama alir, Instagram'a yayinlar
Sirlar ortam degiskenlerinde tutulur.
"""

import os
import json
import time
import requests
from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

IG_USER_ID   = os.environ.get("IG_USER_ID", "")
ACCESS_TOKEN = os.environ.get("IG_ACCESS_TOKEN", "")
APP_SECRET   = os.environ.get("IG_APP_SECRET", "")
API_KEY      = os.environ.get("SERVICE_API_KEY", "")
ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

GRAPH = "https://graph.instagram.com/v23.0"

app = FastAPI(title="ARDINI Paylasim Servisi")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


class PublishIn(BaseModel):
    image_url: str
    caption: str = ""


class GenerateIn(BaseModel):
    ad: str
    kategori: str = ""
    renk: str = ""
    fiyat: int = 0


def _check_key(key):
    if API_KEY and key != API_KEY:
        raise HTTPException(status_code=401, detail="Gecersiz API anahtari")


@app.get("/")
def root():
    return {"servis": "ARDINI Paylasim", "durum": "ayakta"}


@app.get("/health")
def health():
    if not (IG_USER_ID and ACCESS_TOKEN):
        return {"ok": False, "neden": "token/ID eksik"}
    r = requests.get(f"{GRAPH}/{IG_USER_ID}",
                     params={"fields": "id,username", "access_token": ACCESS_TOKEN},
                     timeout=20).json()
    if "id" in r:
        return {"ok": True, "hesap": r.get("username")}
    return {"ok": False, "hata": r.get("error", {}).get("message", "bilinmeyen")}


@app.post("/generate")
def generate(body: GenerateIn, x_api_key: str | None = Header(default=None)):
    _check_key(x_api_key)
    if not ANTHROPIC_KEY:
        raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY eksik")
    prompt = f"""Sen ARDINI markasinin (lazer kesim banyo-mutfak aksesuarlari) sosyal medya icerik ureticisisin. Bu urun icin Instagram gonderisi yaz:
URUN: {body.ad}
KATEGORI: {body.kategori}
RENK: {body.renk}
FIYAT: {body.fiyat} TL
Strateji: Musteriler pazaryerinden aliyor ama biz kendi sitemize (nalburdan.com) trafik cekmek istiyoruz. Urunler montaji kolay (cogu kendinden yapiskanli).
SADECE gecerli JSON dondur, baska hicbir sey yazma:
{{"caption":"...","hashtags":["#..."],"besttime":"...","tip":"..."}}
- caption: 3-5 kisa cumle Turkce, faydayi vurgula, sonda yumusak cagri (siteden siparis), 1-2 emoji.
- hashtags: 12-15 Turkce sektorel.
- besttime: ideal paylasim gunu+saati.
- tip: tek cumle cekim onerisi."""
    r = requests.post("https://api.anthropic.com/v1/messages",
                      headers={"x-api-key": ANTHROPIC_KEY,
                               "anthropic-version": "2023-06-01",
                               "content-type": "application/json"},
                      json={"model": "claude-sonnet-4-20250514", "max_tokens": 1000,
                            "messages": [{"role": "user", "content": prompt}]},
                      timeout=60).json()
    try:
        txt = "".join(b.get("text", "") for b in r["content"] if b.get("type") == "text")
        txt = txt.replace("```json", "").replace("```", "").strip()
        return json.loads(txt)
    except Exception:
        raise HTTPException(status_code=502, detail=f"Uretim hatasi: {r}")


@app.post("/publish")
def publish(body: PublishIn, x_api_key: str | None = Header(default=None)):
    _check_key(x_api_key)
    if not (IG_USER_ID and ACCESS_TOKEN):
        raise HTTPException(status_code=500, detail="Servis yapilandirilmamis")
    c = requests.post(f"{GRAPH}/{IG_USER_ID}/media", data={
        "image_url": body.image_url, "caption": body.caption, "access_token": ACCESS_TOKEN,
    }, timeout=30).json()
    if "id" not in c:
        raise HTTPException(status_code=400, detail=f"Container hatasi: {c.get('error', c)}")
    creation_id = c["id"]
    for _ in range(15):
        s = requests.get(f"{GRAPH}/{creation_id}",
                         params={"fields": "status_code", "access_token": ACCESS_TOKEN},
                         timeout=20).json()
        st = s.get("status_code")
        if st == "FINISHED":
            break
        if st == "ERROR":
            raise HTTPException(status_code=400, detail=f"Container ERROR: {s}")
        time.sleep(2)
    else:
        raise HTTPException(status_code=408, detail="Container zamaninda hazir olmadi")
    p = requests.post(f"{GRAPH}/{IG_USER_ID}/media_publish", data={
        "creation_id": creation_id, "access_token": ACCESS_TOKEN,
    }, timeout=30).json()
    if "id" not in p:
        raise HTTPException(status_code=400, detail=f"Yayin hatasi: {p.get('error', p)}")
    return {"ok": True, "media_id": p["id"]}


@app.post("/token/refresh")
def refresh_token(x_api_key: str | None = Header(default=None)):
    _check_key(x_api_key)
    r = requests.get(f"{GRAPH}/refresh_access_token", params={
        "grant_type": "ig_refresh_token", "access_token": ACCESS_TOKEN,
    }, timeout=20).json()
    if "access_token" not in r:
        raise HTTPException(status_code=400, detail=f"Yenilenemedi: {r}")
    return {"ok": True, "yeni_token": r["access_token"], "saniye": r.get("expires_in")}
