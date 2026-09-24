"""Static and route checks for Maruska Control Center."""
import pathlib, re, shutil, subprocess, tempfile
ROOT=pathlib.Path(__file__).parent
ADMIN=ROOT/'webapp'/'static'/'admin.html'
APP=ROOT/'webapp'/'static'/'admin'/'js'/'app.js'
SERVER=ROOT/'webapp'/'server.py'
API=ROOT/'webapp'/'admin.py'

def main():
    failures=[]; checks=0
    html=ADMIN.read_text(encoding='utf-8'); js=APP.read_text(encoding='utf-8')
    checks+=1
    if '/static/admin/js/app.js' not in html: failures.append('[html] app.js missing')
    checks+=1
    if '/static/admin/css/theme.css' not in html: failures.append('[html] theme.css missing')
    node=shutil.which('node')
    if node:
        checks+=1
        with tempfile.NamedTemporaryFile('w',suffix='.js',delete=False) as f:
            f.write(js); path=f.name
        r=subprocess.run([node,'--check',path],capture_output=True,text=True)
        if r.returncode: failures.append('[js] syntax error: '+r.stderr[:300])
    for marker in ['Command Center','Модерация','Люди','Telegram Gifts','Журнал','/api/admin/gifts','/api/admin/audit','/api/admin/roles']:
        checks+=1
        if marker not in js: failures.append(f'[ui] missing {marker}')
    routes=API.read_text(encoding='utf-8')+SERVER.read_text(encoding='utf-8')
    for path in ['/api/admin/attention','/api/admin/audit','/api/admin/roles','/api/admin/rules','/api/admin/action_override','/api/admin/gifts','/api/admin/analytics','/api/admin/broadcast_history']:
        checks+=1
        if path not in routes: failures.append('[api] missing '+path)
    if failures:
        print('FAIL'); print('\n'.join(failures)); return 1
    print(f'OK: {checks} webapp checks')
    return 0
if __name__=='__main__': raise SystemExit(main())
