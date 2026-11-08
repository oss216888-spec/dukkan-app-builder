#!/usr/bin/env python3
"""Build a per-store Android app (WebView wrapper + FCM). Usage: build.py <slug> <name>"""
import base64, os, re, shutil, subprocess, sys, urllib.request
from pathlib import Path

slug, name = sys.argv[1], sys.argv[2]
ROOT = Path(__file__).resolve().parent.parent
WORK = ROOT / "work"
PROJ = WORK / "dukkan_store_app"
APP_ID = "art.dukaan.s" + re.sub(r"[^a-zA-Z0-9]", "", slug)


def run(cmd, cwd=None):
    print(">>", " ".join(cmd), flush=True)
    r = subprocess.run(cmd, cwd=cwd)
    if r.returncode != 0:
        sys.exit("FAILED: " + " ".join(cmd[:3]))


def rd(p):
    return Path(p).read_text(encoding="utf-8")


def wr(p, s):
    Path(p).parent.mkdir(parents=True, exist_ok=True)
    Path(p).write_text(s, encoding="utf-8", newline="\n")


def xml_esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


shutil.rmtree(WORK, ignore_errors=True)
WORK.mkdir(parents=True)
run(["flutter", "create", "--org", "art.dukaan", "--project-name", "dukkan_store_app", "--platforms", "android", "dukkan_store_app"], cwd=WORK)
run(["flutter", "pub", "add", "webview_flutter", "webview_flutter_android", "url_launcher",
     "permission_handler:^11.3.1", "firebase_core:^3.15.2", "firebase_messaging:^15.2.10"], cwd=PROJ)

shutil.copy(ROOT / "app" / "main.dart", PROJ / "lib" / "main.dart")

AND = PROJ / "android"
APPD = AND / "app"
MAIN = APPD / "src" / "main"

# ---- Firebase config (package rewritten per store) ----
gs = os.environ["GOOGLE_SERVICES_JSON"].replace("art.dukaan.sdukkan", APP_ID)
wr(APPD / "google-services.json", gs)

# ---- sound + channel ----
shutil.copy(ROOT / "app" / "dukkan_offer.ogg", MAIN / "res" / "raw" / "dukkan_offer.ogg") if (MAIN / "res" / "raw").exists() else (
    (MAIN / "res" / "raw").mkdir(parents=True, exist_ok=True), shutil.copy(ROOT / "app" / "dukkan_offer.ogg", MAIN / "res" / "raw" / "dukkan_offer.ogg"))
wr(MAIN / "res" / "raw" / "keep.xml",
   '<?xml version="1.0" encoding="utf-8"?>\n<resources xmlns:tools="http://schemas.android.com/tools" tools:keep="@raw/dukkan_offer" />\n')
kt = next((MAIN / "kotlin").rglob("MainActivity.kt"))
pk = re.search(r"package\s+([\w.]+)", rd(kt)).group(1)
wr(kt, f'''package {pk}

import android.app.NotificationChannel
import android.app.NotificationManager
import android.media.AudioAttributes
import android.net.Uri
import android.os.Build
import android.os.Bundle
import io.flutter.embedding.android.FlutterActivity

class MainActivity : FlutterActivity() {{
    override fun onCreate(savedInstanceState: Bundle?) {{
        super.onCreate(savedInstanceState)
        if (Build.VERSION.SDK_INT >= 26) {{
            val nm = getSystemService(NotificationManager::class.java)
            val uri = Uri.parse("android.resource://" + packageName + "/raw/dukkan_offer")
            val attrs = AudioAttributes.Builder()
                .setUsage(AudioAttributes.USAGE_NOTIFICATION)
                .setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION)
                .build()
            val ch = NotificationChannel("dukkan_offers_v1", "Offers", NotificationManager.IMPORTANCE_HIGH)
            ch.setSound(uri, attrs)
            ch.enableVibration(true)
            nm.createNotificationChannel(ch)
        }}
    }}
}}
''')

# ---- icons from the store logo (optional) ----
have_stat = False
try:
    from PIL import Image
    ico = ROOT / "work" / "icons"
    ico.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request("https://dukaan.art/api/icon?s=" + slug, headers={"User-Agent": "DukkanAppBuilder/1.0"})
    raw = ico / "logo.raw"
    raw.write_bytes(urllib.request.urlopen(req, timeout=60).read())
    im = Image.open(raw).convert("RGBA")

    def compose(frac, white, path, size=1024):
        c = Image.new("RGBA", (size, size), (255, 255, 255, 255) if white else (0, 0, 0, 0))
        box = int(size * frac)
        r = min(box / im.width, box / im.height)
        nw, nh = max(1, int(im.width * r)), max(1, int(im.height * r))
        c.alpha_composite(im.resize((nw, nh), Image.LANCZOS), ((size - nw) // 2, (size - nh) // 2))
        c.save(path)
        return c

    compose(0.82, True, ico / "icon.png")
    compose(0.60, False, ico / "fg.png")
    t = compose(0.84, False, ico / "tmp.png", 96)
    sil = Image.new("RGBA", (96, 96), (255, 255, 255, 0))
    px, sp = t.load(), sil.load()
    for y in range(96):
        for x in range(96):
            r_, g_, b_, a_ = px[x, y]
            if a_ < 250:
                al = a_
            else:
                lum = 0.299 * r_ + 0.587 * g_ + 0.114 * b_
                al = int(max(0, min(255, (255 - lum) * 1.4)))
            sp[x, y] = (255, 255, 255, al)
    (MAIN / "res" / "drawable").mkdir(parents=True, exist_ok=True)
    sil.save(MAIN / "res" / "drawable" / "ic_stat_notify.png")
    have_stat = True
    run(["flutter", "pub", "add", "--dev", "flutter_launcher_icons"], cwd=PROJ)
    pp = PROJ / "pubspec.yaml"
    py = re.sub(r"(?ms)^flutter_launcher_icons:\r?\n(?:[ \t]+.*\r?\n?)*", "", rd(pp)).rstrip()
    py += f'''

flutter_launcher_icons:
  android: true
  ios: false
  image_path: "{(ico / "icon.png").as_posix()}"
  adaptive_icon_background: "#FFFFFF"
  adaptive_icon_foreground: "{(ico / "fg.png").as_posix()}"
  min_sdk_android: 24
'''
    wr(pp, py)
    run(["dart", "run", "flutter_launcher_icons"], cwd=PROJ)
    print("Icon: store logo applied")
except SystemExit:
    raise
except Exception as e:
    print("WARNING: icon step skipped:", e)

# ---- manifest ----
man = MAIN / "AndroidManifest.xml"
t = rd(man)
t = re.sub(r'android:label="[^"]*"', 'android:label="' + xml_esc(name) + '"', t, count=1)
for perm in ["INTERNET", "ACCESS_FINE_LOCATION", "ACCESS_COARSE_LOCATION", "CAMERA", "POST_NOTIFICATIONS"]:
    if f'android.permission.{perm}"' not in t:
        t = re.sub(r"(<manifest[^>]*>)", r'\1\n    <uses-permission android:name="android.permission.' + perm + '"/>', t, count=1)
meta = '\n        <meta-data android:name="com.google.firebase.messaging.default_notification_channel_id" android:value="dukkan_offers_v1"/>'
if have_stat:
    meta += '\n        <meta-data android:name="com.google.firebase.messaging.default_notification_icon" android:resource="@drawable/ic_stat_notify"/>'
t = re.sub(r"(<application[^>]*>)", lambda m: m.group(1) + meta, t, count=1)
wr(man, t)

# ---- gradle ----
sg = AND / "settings.gradle.kts"
s = rd(sg)
if "com.google.gms.google-services" not in s:
    s = re.sub(r'(id\("com\.android\.application"\)\s+version\s+"[^"]+"\s+apply\s+false)',
               r'\1\n    id("com.google.gms.google-services") version "4.4.2" apply false', s, count=1)
    wr(sg, s)

bg = APPD / "build.gradle.kts"
g = rd(bg)
if "com.google.gms.google-services" not in g:
    g = re.sub(r'(id\("com\.android\.application"\))', r'\1\n    id("com.google.gms.google-services")', g, count=1)
g = re.sub(r"minSdk\s*=\s*flutter\.minSdkVersion", "minSdk = 24", g)
g = re.sub(r'(applicationId\s*=?\s*)"[^"]*"', lambda m: m.group(1) + '"' + APP_ID + '"', g, count=1)
ks = os.environ.get("KEYSTORE_B64", "").strip()
if ks:
    (APPD / "release.keystore").write_bytes(base64.b64decode(ks))
    sign = '''signingConfigs {
        getByName("debug") {
            storeFile = file("release.keystore")
            storePassword = "android"
            keyAlias = "androiddebugkey"
            keyPassword = "android"
        }
    }
    buildTypes {'''
    g = g.replace("buildTypes {", sign, 1)
wr(bg, g)

# ---- build ----
run(["flutter", "build", "apk", "--release", "--dart-define=SLUG=" + slug], cwd=PROJ)
out = ROOT / "out"
out.mkdir(exist_ok=True)
shutil.copy(PROJ / "build" / "app" / "outputs" / "flutter-apk" / "app-release.apk", out / f"{slug}.apk")
print("Done:", out / f"{slug}.apk")
