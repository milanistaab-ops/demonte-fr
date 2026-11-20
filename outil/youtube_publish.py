#!/usr/bin/env python3
"""Publication YouTube (Shorts) pour DÉMONTÉ, sans dépendance externe.

Lit les identifiants dans les variables d'environnement :
  YT_CLIENT_ID, YT_CLIENT_SECRET, YT_REFRESH_TOKEN

Usage :
  python3 youtube_publish.py check
      Vérifie les identifiants et affiche la chaîne connectée (n'envoie rien).
  python3 youtube_publish.py upload VIDEO.mp4 --title "..." [--description "..."]
      [--tags a,b,c] [--privacy private|unlisted|public] [--publish-at 2026-11-22T11:30:00Z]
      Envoie la vidéo. Par défaut : privée. --publish-at programme la sortie
      (la vidéo reste privée jusqu'à l'heure indiquée, en UTC).

Tant que le projet Google n'a pas passé l'audit YouTube API, toute vidéo
envoyée par l'API est bloquée en privé par YouTube, quel que soit --privacy.
"""
import argparse, json, os, sys, urllib.parse, urllib.request, urllib.error

TOKEN_URL = "https://oauth2.googleapis.com/token"
API = "https://www.googleapis.com/youtube/v3"
UPLOAD = "https://www.googleapis.com/upload/youtube/v3/videos"
CHUNK = 8 * 1024 * 1024


def env(name):
    v = os.environ.get(name, "").strip()
    if not v:
        sys.exit(f"Variable d'environnement manquante : {name}")
    return v


def access_token():
    data = urllib.parse.urlencode({
        "client_id": env("YT_CLIENT_ID"),
        "client_secret": env("YT_CLIENT_SECRET"),
        "refresh_token": env("YT_REFRESH_TOKEN"),
        "grant_type": "refresh_token",
    }).encode()
    try:
        with urllib.request.urlopen(urllib.request.Request(TOKEN_URL, data=data)) as r:
            return json.load(r)["access_token"]
    except urllib.error.HTTPError as e:
        sys.exit(f"Échec du rafraîchissement du jeton ({e.code}) : {e.read().decode()[:500]}")


def call(req):
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read()


def check():
    tok = access_token()
    req = urllib.request.Request(f"{API}/channels?part=snippet,statistics&mine=true",
                                 headers={"Authorization": f"Bearer {tok}"})
    code, _, body = call(req)
    if code != 200:
        sys.exit(f"Erreur API ({code}) : {body.decode()[:500]}")
    items = json.loads(body).get("items", [])
    if not items:
        sys.exit("Jeton valide, mais aucune chaîne YouTube sur ce compte.")
    ch = items[0]
    print(json.dumps({"ok": True, "chaine": ch["snippet"]["title"], "id": ch["id"],
                      "abonnes": ch["statistics"].get("subscriberCount"),
                      "videos": ch["statistics"].get("videoCount")}, ensure_ascii=False))


def upload(a):
    size = os.path.getsize(a.video)
    status = {"privacyStatus": a.privacy, "selfDeclaredMadeForKids": False}
    if a.publish_at:
        status["privacyStatus"] = "private"
        status["publishAt"] = a.publish_at
    meta = {"snippet": {"title": a.title[:100], "description": a.description,
                        "tags": [t.strip() for t in a.tags.split(",") if t.strip()],
                        "categoryId": "27", "defaultLanguage": "fr",
                        "defaultAudioLanguage": "fr"},
            "status": status}
    tok = access_token()
    req = urllib.request.Request(
        f"{UPLOAD}?uploadType=resumable&part=snippet,status&notifySubscribers=true",
        data=json.dumps(meta).encode(), method="POST",
        headers={"Authorization": f"Bearer {tok}",
                 "Content-Type": "application/json; charset=UTF-8",
                 "X-Upload-Content-Type": "video/mp4",
                 "X-Upload-Content-Length": str(size)})
    code, headers, body = call(req)
    loc = headers.get("Location") or headers.get("location")
    if code != 200 or not loc:
        sys.exit(f"Impossible d'ouvrir l'envoi ({code}) : {body.decode()[:500]}")
    with open(a.video, "rb") as f:
        start = 0
        while start < size:
            chunk = f.read(CHUNK)
            end = start + len(chunk) - 1
            req = urllib.request.Request(loc, data=chunk, method="PUT", headers={
                "Authorization": f"Bearer {tok}",
                "Content-Length": str(len(chunk)),
                "Content-Range": f"bytes {start}-{end}/{size}"})
            code, headers, body = call(req)
            if code in (200, 201):
                v = json.loads(body)
                print(json.dumps({"ok": True, "id": v["id"],
                                  "url": f"https://youtube.com/shorts/{v['id']}",
                                  "statut": v["status"].get("privacyStatus"),
                                  "publishAt": v["status"].get("publishAt")}, ensure_ascii=False))
                return
            if code != 308:
                sys.exit(f"Erreur pendant l'envoi ({code}) : {body.decode()[:500]}")
            rng = headers.get("Range") or headers.get("range")
            start = int(rng.split("-")[1]) + 1 if rng else 0
            f.seek(start)
            print(f"  {start * 100 // size} %", file=sys.stderr)


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check")
    u = sub.add_parser("upload")
    u.add_argument("video")
    u.add_argument("--title", required=True)
    u.add_argument("--description", default="")
    u.add_argument("--tags", default="")
    u.add_argument("--privacy", default="private", choices=["private", "unlisted", "public"])
    u.add_argument("--publish-at", default=None)
    a = p.parse_args()
    check() if a.cmd == "check" else upload(a)


if __name__ == "__main__":
    main()
