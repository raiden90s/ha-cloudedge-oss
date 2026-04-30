import asyncio
import base64
import gzip
import hashlib
import hmac
import http.client
import json
import random
import ssl
import time
import urllib.parse
import urllib.request

from homeassistant.components.camera import Camera

CA_KEY_LOGIN = "bc29be30292a4309877807e101afbd51"
ENCRYPTED_PASS = "GEdGUoGhvl3NqnNRw6RpbA=="
ENCRYPTED_USER = "hsTIgWlQcMqZ5YWaG7INjhReMF2aRwQ1YnSNogjX+jc="
CTX = ssl.create_default_context()
API_HOST = "apis-eu-frankfurt.cloudedge360.com"
OSS_HOST = "oss-eu-central-1.aliyuncs.com"
BUCKET = "meari-eu"

class CloudEdgeCamera(Camera):
    def __init__(self, hass, user_id, device_id):
        super().__init__()
        self.hass = hass
        self._user_id = str(user_id)
        self._device_id = str(device_id)
        self._image = None
        self._attr_unique_id = f"cloudedge_oss_{self._device_id}"
        self._attr_name = "Campanello CloudEdge"

    # --- FUNZIONI API (Come le abbiamo scritte noi) ---
    def _make_jwt(self, token):
        h = "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzEifQ=="
        ts = str(int(time.time() * 1000))
        p = base64.b64encode(json.dumps({"userToken": token, "phoneType": "a", "t": ts, "sourceApp": "8", "countryCode": "IT", "appVer": "6.1.9", "lngType": "it", "phoneCode": "39", "userID": self._user_id, "appVerCode": "621"}, separators=(',', ':')).encode()).decode()
        return f'{h}.{p}.{base64.b64encode(hmac.new(token.encode(), f"{h}.{p}".encode(), hashlib.sha1).digest()).decode()}'

    def _sign_md5(self, p, k):
        qs = '&'.join(f'{i}={j}' for i, j in sorted(p.items()) if i not in ('signature', 'sign'))
        return base64.b64encode(hmac.new(k.encode(), qs.encode(), hashlib.sha1).digest()).decode()

    def _sign_xca(self, m, path, q, ts, n, k):
        ct = 'application/x-www-form-urlencoded\n' if m == 'POST' else '\n'
        f = f'{path}?{q}' if q else path
        return base64.b64encode(hmac.new(k.encode(), f'{m}\n\n\n{ct}X-Ca-Key:{k}\nX-Ca-Nonce:{n}\nX-Ca-Timestamp:{ts}\n{f}'.encode(), hashlib.sha1).digest()).decode()

    def _base_p(self, t):
        ts = str(int(time.time() * 1000))
        return {'phoneType': 'a', 'sourceApp': '8', 'appVer': '6.1.9', 'appVerCode': '621', 'signatureMethod': 'HMAC-SHA1', 'signatureVersion': '1.0', 'signatureNonce': ts, 't': ts, 'lngType': 'it', 'countryCode': 'IT', 'phoneCode': '39', 'userID': self._user_id, 'timestamp': time.strftime('%Y-%m-%dT%H:%M:%S.') + ts[-3:] + 'Z'}

    def _req(self, m, path, p, t, jwt=False):
        ts, n = str(int(time.time() * 1000)), str(random.randint(100000, 999999))
        bp = self._base_p(t); bp.update(p); bp['signature'] = self._sign_md5(bp, t)
        h = {'User-Agent': 'Dalvik/2.1.0', 'Accept-Encoding': 'gzip', 'x-ca-key': t, 'x-ca-timestamp': ts, 'x-ca-nonce': n, 'x-ca-sign': self._sign_xca(m, path, '' if m=='POST' else urllib.parse.urlencode(bp), ts, n, t)}
        if jwt: h.update({'phonetype': 'a', 'jwt': self._make_jwt(t)})
        b = urllib.parse.urlencode(bp).encode() if m == 'POST' else None
        if m == 'POST': h['Content-Type'] = 'application/x-www-form-urlencoded'; f = path
        else: f = f'{path}?{urllib.parse.urlencode(bp)}'
        try:
            c = http.client.HTTPSConnection(API_HOST, context=CTX, timeout=10); c.request(m, f, b, h); r = c.getresponse(); raw = r.read()
            try: raw = gzip.decompress(raw)
            except: pass
            return json.loads(raw.decode('utf-8', errors='replace'))
        finally: c.close()

    def _sync_fetch(self):
        """Esegue il download bloccante (viene runnato in un thread)."""
        try:
            # 1. Login
            ts, n = str(int(time.time() * 1000)), str(random.randint(100000, 999999))
            lp = {'phoneType': 'a', 'sourceApp': '8', 'appVer': '6.1.9', 'iotType': '4', 'equipmentNo': ' ', 'appVerCode': '621', 'localTime': ts, 'password': ENCRYPTED_PASS, 't': ts, 'lngType': 'it', 'countryCode': 'IT', 'userAccount': ENCRYPTED_USER, 'encryStatus': '1', 'phoneCode': '39'}
            path = '/meari/app/login'
            h = {'Content-Type': 'application/x-www-form-urlencoded', 'User-Agent': 'Dalvik/2.1.0', 'Accept-Encoding': 'gzip', 'x-ca-key': CA_KEY_LOGIN, 'x-ca-timestamp': ts, 'x-ca-nonce': n, 'x-ca-sign': self._sign_xca('POST', path, '', ts, n, CA_KEY_LOGIN)}
            try:
                c = http.client.HTTPSConnection(API_HOST, context=CTX, timeout=10); c.request('POST', path, urllib.parse.urlencode(lp).encode(), h); raw = c.getresponse().read()
                try: raw = gzip.decompress(raw)
                except: pass
                token = json.loads(raw.decode('utf-8', errors='replace')).get('result', {}).get('userToken', '')
            finally: c.close()
            if not token: return

            # 2. Push/Token
            ts_p, n_p = str(int(time.time() * 1000)), str(random.randint(100000, 999999))
            pp = {'phoneType': 'a', 'sourceApp': '8', 'appVer': '6.1.9', 'appVerCode': '621', 'signatureMethod': 'HMAC-SHA1', 'signatureVersion': '1.0', 'signatureNonce': ts_p, 't': ts_p, 'lngType': 'it', 'countryCode': 'IT', 'phoneCode': '39', 'userID': self._user_id, 'type': '1', 'pushToken': 'fWdBkb8IR4GJTRVZnDe-95:APA91bFBn132u4HeF4WTiNtErjpXS0Hg1wAN_e9QGfhrZxlkgzOwKFvtOTDaJH96VX62DtXO3XbZd3_5L7WAHun2zNgwmio79VhI9yipf-sc-NAlN_xvuPg', 'timestamp': time.strftime('%Y-%m-%dT%H:%M:%S.') + ts_p[-3:] + 'Z'}
            pp['signature'] = base64.b64encode(hmac.new(token.encode(), '&'.join(f'{k}={v}' for k,v in sorted(pp.items())).encode(), hashlib.sha1).digest()).decode()
            path = '/push/token/put'
            h = {'Content-Type': 'application/x-www-form-urlencoded', 'User-Agent': 'Dalvik/2.1.0', 'Accept-Encoding': 'gzip', 'phonetype': 'a', 'jwt': self._make_jwt(token), 'x-ca-key': token, 'x-ca-timestamp': ts_p, 'x-ca-nonce': n_p, 'x-ca-sign': self._sign_xca('POST', path, '', ts_p, n_p, token)}
            try:
                c = http.client.HTTPSConnection(API_HOST, context=CTX, timeout=8); c.request('POST', path, urllib.parse.urlencode(pp).encode(), h); c.getresponse().read()
            finally: c.close()

            # 3. Alert
            lt = ((self._req('POST', '/v1/app/msg/alert/latest/list', {}, token, True).get('device') or [{}])[0].get('devLocalTime', ''))[:8]
            day = lt if len(lt)==8 else time.strftime('%Y%m%d')
            alerts = self._req('POST', '/v1/app/msg/alert/list', {'deviceID': self._device_id, 'day': day}, token).get('alertMsg', [])
            if not alerts: return

            ring_alert = next((a for a in alerts if a.get('imageAlertType', 1) != 2 and 'cloudedge360.com/' in a.get('imgUrl', '')), None)
            if not ring_alert: return
            obj_key = ring_alert['imgUrl'].split('cloudedge360.com/')[1]

            # 4. OSS
            oss = self._req('GET', '/cloud/app/alert-img/oss-down-token', {'deviceID': self._device_id, 't': str(int(time.time()*1000))}, token, True).get('result', {})
            if not oss: return
            ak, sk, st = oss['ak'].strip(), oss['sk'].strip(), oss['token'].strip()

            exp = str(int(time.time()) + 1800)
            sig = base64.b64encode(hmac.new(sk.encode(), f'GET\n\n\n{exp}\n/{BUCKET}/{obj_key}?security-token={st}'.encode(), hashlib.sha1).digest()).decode()
            url = f'https://{BUCKET}.{OSS_HOST}/{obj_key}?OSSAccessKeyId={urllib.parse.quote(ak, safe="")}&Expires={exp}&Signature={urllib.parse.quote(sig, safe="")}&security-token={urllib.parse.quote(st, safe="")}'
            
            req = urllib.request.Request(url, headers={'User-Agent': 'Dalvik/2.1.0'})
            with urllib.request.urlopen(req, context=CTX, timeout=15) as r:
                data = r.read()
                
            if data[:2] == b'\xff\xd8':
                self._image = data
        except:
            pass

    # --- METODI STANDARD CAMERA HA ---
    async def async_camera_image(self, width=None, height=None):
        return self._image

    async def async_update(self):
        """Chiamato da Home Assistant in background."""
        await asyncio.to_thread(self._sync_fetch)
