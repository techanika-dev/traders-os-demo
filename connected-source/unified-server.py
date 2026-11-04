"""TRADERS OS connected local demo. Python standard library; binds only to loopback."""
import json
import sqlite3
import threading
import time
import hashlib
import account_access as access
from pathlib import Path
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, unquote

ROOT = Path(__file__).resolve().parent
DATA = ROOT / 'unified-data'
DATA.mkdir(exist_ok=True)
LOCK = threading.Lock()
MISSING = object()

def merge(base, local, remote, path='state'):
    """Three-way merge; concurrent edits to one field conflict instead of being lost."""
    if local == base:
        return remote
    if remote == base or local == remote:
        return local
    if all(isinstance(v, dict) for v in (base, local, remote)):
        out = {}
        for k in base.keys() | local.keys() | remote.keys():
            value = merge(base.get(k, MISSING), local.get(k, MISSING), remote.get(k, MISSING), path+'.'+k)
            if value is not MISSING:
                out[k] = value
        return out
    if all(isinstance(v, list) for v in (base, local, remote)):
        if all(isinstance(x, dict) and 'id' in x for v in (base, local, remote) for x in v):
            maps = [{str(x['id']): x for x in v} for v in (base, local, remote)]
            order = list(dict.fromkeys([str(x['id']) for x in local+remote]))
            result = merge(*maps, path)
            return [result[k] for k in order if k in result]
        if all(isinstance(x, (str, int, float, bool)) for v in (base, local, remote) for x in v):
            removed = {x for x in base if x not in local or x not in remote}
            return list(dict.fromkeys(x for x in local+remote if x not in removed))
    raise ValueError('Concurrent change: '+path)

def connection():
    con = sqlite3.connect(DATA / 'portal.sqlite3')
    access.setup(con)
    con.execute('CREATE TABLE IF NOT EXISTS state (id INTEGER PRIMARY KEY, revision INTEGER NOT NULL, body TEXT NOT NULL)')
    if not con.execute('SELECT 1 FROM state WHERE id=1').fetchone():
        initial = json.loads((ROOT / 'unified-seed.json').read_text(encoding='utf-8'))
        con.execute('INSERT INTO state VALUES(1, 1, ?)', (json.dumps(initial),))
        con.commit()
    return con

class Handler(BaseHTTPRequestHandler):
    def reply(self, code, obj):
        payload = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Length', str(len(payload)))
        origin = self.headers.get('Origin')
        if origin in ('null', 'http://127.0.0.1:8766', 'http://localhost:8766'):
            self.send_header('Access-Control-Allow-Origin', origin)
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization')
        self.end_headers()
        self.wfile.write(payload)

    def do_OPTIONS(self):
        self.reply(200, {'ok': True})

    def identity(self, con):
        header=self.headers.get('Authorization','')
        return access.identify(con,header[7:] if header.startswith('Bearer ') else '')

    def do_GET(self):
        path = urlparse(self.path).path
        if path == '/api/state':
            with LOCK, connection() as con:
                revision, body = con.execute('SELECT revision, body FROM state WHERE id=1').fetchone()
                user=self.identity(con)
                if self.headers.get('Authorization') and not user:return self.reply(401, {'error':'Session expired. Sign in again.'})
                visible=access.project(json.loads(body),user)
            return self.reply(200, {'revision': revision, 'state': visible})
        if path == '/api/me':
            with LOCK, connection() as con:user=self.identity(con)
            return self.reply(200 if user else 401, {'user':user})
        if path == '/api/health':
            return self.reply(200, {'status': 'ok', 'storage': 'SQLite', 'time': time.time()})
        name = unquote(path).lstrip('/') or 'traders-os-unified.html'
        file = (ROOT / name).resolve()
        if file.parent != ROOT or file.suffix not in ('.html', '.png', '.md') or not file.is_file():
            return self.reply(404, {'error': 'Not found'})
        content = file.read_bytes()
        self.send_response(200)
        self.send_header('Content-Type', {'.html':'text/html; charset=utf-8','.png':'image/png','.md':'text/plain; charset=utf-8'}[file.suffix])
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Length',str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def do_POST(self):
        if self.headers.get('Origin') not in (None,'http://127.0.0.1:8766','http://localhost:8766'):
            return self.reply(403, {'error':'Only local app origins are permitted'})
        try:
            size=int(self.headers.get('Content-Length','0'))
            if not 1<=size<=12_000_000:return self.reply(413, {'error':'Request exceeds limit'})
            v=json.loads(self.rfile.read(size));path=urlparse(self.path).path
            with LOCK, connection() as con:
                user=self.identity(con)
                revision,body=con.execute('SELECT revision,body FROM state WHERE id=1').fetchone()
                current=json.loads(body)
                result={}
                if path=='/api/register':result=access.register(con,current,v)
                elif path=='/api/login':
                    result=access.login(con,v);con.commit();return self.reply(200,result)
                elif path=='/api/logout':
                    token=self.headers.get('Authorization','')[7:]
                    con.execute('DELETE FROM sessions WHERE token_hash=?',(hashlib.sha256(token.encode()).hexdigest(),));con.commit();return self.reply(200,{'ok':True})
                elif path=='/api/checkout':access.checkout(current,user,v)
                elif path=='/api/enquiry':
                    name=str(v.get('name','')).strip();email=str(v.get('email','')).strip();course=next((c for c in current[access.ORG]['courses'] if c['id']==v.get('course') and c['status']=='Published'),None)
                    if not name or '@' not in email or not course:raise ValueError('Enter your name, email and a published course.')
                    current[access.ORG]['leads'].insert(0,{'id':'LE-'+access.secrets.token_hex(8),'name':name[:100],'email':email[:254],'course':course['id'],'value':course['price'],'notes':str(v.get('notes',''))[:4000],'source':'Public discovery','stage':'New','owner':'Admissions','followup':time.strftime('%Y-%m-%d')})
                elif path=='/api/state':
                    if not user:raise PermissionError('Sign in to update records.')
                    if not isinstance(v.get('base'),dict) or not isinstance(v.get('next'),dict):raise ValueError('base and next records required')
                    if user['role']=='Student':access.student_update(current,user,v['base'],v['next'],merge)
                    else:
                        if user['role']!='Super Admin' and (set(v['base'])!={user['org']} or set(v['next'])!={user['org']}):raise PermissionError('Academy scope mismatch.')
                        for org in v['next']:current[org]=merge(v['base'][org],v['next'][org],current[org])
                else:return self.reply(404,{'error':'Not found'})
                con.execute('UPDATE state SET revision=?,body=? WHERE id=1',(revision+1,json.dumps(current)));con.commit()
                result.update({'revision':revision+1,'state':access.project(current,result.get('user',user))})
            self.reply(200,result)
        except PermissionError as exc:self.reply(403,{'error':str(exc)})
        except ValueError as exc:self.reply(409 if 'Concurrent' in str(exc) else 400,{'error':str(exc)})
        except Exception:self.reply(500,{'error':'Could not save. Existing records are intact.'})

    def log_message(self, fmt, *args):
        pass

if __name__ == '__main__':
    connection().close()
    print('TRADERS OS connected demo: http://127.0.0.1:8766', flush=True)
    ThreadingHTTPServer(('127.0.0.1',8766), Handler).serve_forever()
