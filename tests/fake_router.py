"""A fake home router built like modern ZTE/Huawei pages: JavaScript login form,
<span> menus with no links, settings inside an iframe, and a Save button that uses fetch().
Used by tests/test_web_gui.py."""
from flask import Flask, request, jsonify
app = Flask(__name__)
STATE = {"ssid": "Orange-1234", "wifi_password": "wifi-pass-123", "logged_in": False}

@app.get("/")
def index():
    return """<html><body><div id=app></div><script>
function showLogin(){ document.getElementById('app').innerHTML =
 '<div class=box><div>Welcome, please login.</div><table><tr><td>Username</td><td><input id=Frm_Username></td></tr>'+
 '<tr><td>Password</td><td><input id=Frm_Password type=password></td></tr></table>'+
 '<div id=LoginId style="cursor:pointer;background:orange">Login</div></div>';
 document.getElementById('LoginId').addEventListener('click', async () => {
   const r = await fetch('/login', {method:'POST', headers:{'Content-Type':'application/json'},
     body: JSON.stringify({u: Frm_Username.value, p: Frm_Password.value})});
   if ((await r.json()).ok) showMain(); else alert('wrong password'); }); }
function showMain(){ document.getElementById('app').innerHTML =
 '<div class=menu><span class=m style="cursor:pointer" id=mHome>Home</span> '+
 '<span class=m style="cursor:pointer" id=mInternet>Internet</span> '+
 '<span class=m style="cursor:pointer" id=mLocal>Local Network</span> '+
 '<span class=m style="cursor:pointer" id=mMgmt>Management &amp; Diagnosis</span></div><div id=sub></div>'+
 '<iframe id=content style="width:600px;height:300px" src="/page/home"></iframe>';
 mLocal.addEventListener('click', () => { sub.innerHTML =
   '<span style="cursor:pointer" id=sWlan>WLAN</span> <span style="cursor:pointer" id=sLan>LAN</span>';
   sWlan.addEventListener('click', () => content.src = '/page/wlan');
   sLan.addEventListener('click', () => content.src = '/page/lan'); });
 mHome.addEventListener('click', () => content.src = '/page/home'); }
showLogin();
</script></body></html>"""

@app.post("/login")
def login():
    ok = request.json == {"u": "admin", "p": "S3cret!"}
    STATE["logged_in"] = ok
    return jsonify(ok=ok)

@app.get("/page/<name>")
def page(name):
    if not STATE["logged_in"]: return "not logged in", 403
    if name == "wlan":
        return f"""<html><body><h3>WLAN SSID Settings</h3><table>
<tr><td>SSID Name</td><td><input id=ESSID value="{STATE['ssid']}"></td></tr>
<tr><td>WPA Passphrase</td><td><input type=password id=KeyPassphrase value="{STATE['wifi_password']}"></td></tr>
<tr><td>Hide SSID</td><td><input type=checkbox id=hide></td></tr></table>
<input type=button id=Btn_apply value="Apply"> <input type=button value="Cancel">
<script>Btn_apply.onclick = async () => {{ await fetch('/save', {{method:'POST',
 headers:{{'Content-Type':'application/json'}}, body: JSON.stringify({{ssid: ESSID.value, key: KeyPassphrase.value}})}});
 document.body.insertAdjacentHTML('beforeend','<p>Saved successfully</p>'); }};</script></body></html>"""
    return f"<html><body><h3>{name.upper()} page</h3><p>Status: OK</p></body></html>"

@app.post("/save")
def save():
    STATE["ssid"] = request.json["ssid"]
    STATE["wifi_password"] = request.json["key"]
    return jsonify(ok=True)
