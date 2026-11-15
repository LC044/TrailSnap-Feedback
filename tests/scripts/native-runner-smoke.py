import json, os, pathlib, subprocess, sys, threading, time, urllib.request, urllib.error, uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

GEN='a'*40+'-'+'b'*16
TOKEN='isolated-smoke-only-not-production'

def gateway():
    requests=[]
    command="""python - <<'PY'
import os, pathlib, socket, subprocess
assert os.getuid() != 0
assert not pathlib.Path('/app/data/requirements.db').exists()
assert not pathlib.Path('/var/run/docker.sock').exists()
assert not any(os.environ.get(k) for k in ('RP_DSH_RUNNER_TOKEN','RP_JWT_SECRET','RP_SMTP_PASSWORD','RP_AI_API_KEY'))
try:
 pathlib.Path('/knowledge/forbidden.txt').write_text('bad')
 raise AssertionError('writable public mount')
except OSError: pass
try:
 pathlib.Path('/app/forbidden.txt').write_text('bad')
 raise AssertionError('writable root')
except OSError: pass
try:
 pathlib.Path('/proc/1/environ').read_bytes()
 raise AssertionError('root environment readable')
except PermissionError: pass
try:
 socket.create_connection(('1.1.1.1',443),timeout=1)
 raise AssertionError('external network reachable')
except OSError: pass
pathlib.Path('analysis.txt').write_text('local-only')
subprocess.Popen(['python','-c','import time;time.sleep(100)'],start_new_session=True,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
print('isolation-checks-ok')
PY"""
    actions=[('read',{'file_path':'source/provider.rs'}),('grep',{'pattern':'CUDA','path':'source'}),('bash',{'command':command})]
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*_): pass
        def do_POST(self):
            assert self.headers.get('x-api-key')=='one-run-only'
            body=json.loads(self.rfile.read(int(self.headers['Content-Length'])));requests.append(body)
            self.send_response(200);self.send_header('Content-Type','text/event-stream');self.end_headers()
            events=[('message_start',{'type':'message_start','message':{'id':'test','type':'message','role':'assistant','model':'test','content':[],'usage':{'input_tokens':10,'output_tokens':0}}})]
            if len(requests)<=len(actions):
                name,args=actions[len(requests)-1]
                events += [('content_block_start',{'type':'content_block_start','index':0,'content_block':{'type':'tool_use','id':'t'+str(len(requests)),'name':name,'input':{}}}),('content_block_delta',{'type':'content_block_delta','index':0,'delta':{'type':'input_json_delta','partial_json':json.dumps(args)}})]
                reason='tool_use'
            else:
                events += [('content_block_start',{'type':'content_block_start','index':0,'content_block':{'type':'text','text':''}}),('content_block_delta',{'type':'content_block_delta','index':0,'delta':{'type':'text_delta','text':'native-isolation-passed'}})]
                reason='end_turn'
            events += [('content_block_stop',{'type':'content_block_stop','index':0}),('message_delta',{'type':'message_delta','delta':{'stop_reason':reason},'usage':{'output_tokens':10}}),('message_stop',{'type':'message_stop'})]
            for kind,data in events:self.wfile.write(('event: '+kind+'\ndata: '+json.dumps(data)+'\n\n').encode())
    server=ThreadingHTTPServer(('0.0.0.0',18000),Handler);threading.Thread(target=server.serve_forever,daemon=True).start()
    for _ in range(30):
        try: urllib.request.urlopen('http://runner:8013/health',timeout=1);break
        except Exception: time.sleep(1)
    payload={'generation':GEN,'gateway_url':'http://api:18000','gateway_token':'one-run-only','system':'Use the supplied tools.','model':'test','reasoning_effort':'none','max_tokens':1024,'timeout':35,'prompt':'{}'}
    try:
        urllib.request.urlopen(urllib.request.Request('http://runner:8013/run',data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'}))
        raise AssertionError('missing auth allowed')
    except urllib.error.HTTPError as e:assert e.code==403
    req=urllib.request.Request('http://runner:8013/run',data=json.dumps(payload).encode(),headers={'Content-Type':'application/json','Authorization':'Bearer '+TOKEN})
    with urllib.request.urlopen(req,timeout=45) as response: result=json.load(response)
    assert result['reply']=='native-isolation-passed',result
    history=json.dumps(requests[-1]);assert 'isolation-checks-ok' in history and 'CUDA CoreML' in history,history
    assert not any(b.get('is_error') for m in requests[-1]['messages'] for b in m.get('content',[]) if isinstance(b,dict) and b.get('type')=='tool_result'),history
    print(json.dumps({'native_requests':len(requests),'read_search_shell':True,'readonly_and_credential_isolation':True,'external_network_blocked':True,'auth_required':True}))
    server.shutdown()

def host():
    suffix=uuid.uuid4().hex[:8]; network='native-test-'+suffix; volume=network+'-public'; runner=network+'-runner'; image=os.environ.get('NATIVE_RUNNER_IMAGE','trailsnap-feedback-native:test')
    def run(args,**kw):return subprocess.run(args,check=True,text=True,capture_output=True,**kw).stdout
    run(['docker','network','create','--internal',network]);run(['docker','volume','create',volume])
    try:
        seed="import pathlib,json; r=pathlib.Path('/knowledge')/'"+GEN+"';(r/'source').mkdir(parents=True);(r/'docs').mkdir();(r/'source/provider.rs').write_text('CUDA CoreML CPU');(r/'manifest.json').write_text('{}')"
        run(['docker','run','--rm','--user','0','--entrypoint','/app/.venv/bin/python','-v',volume+':/knowledge',image,'-c',seed])
        args=['docker','run','-d','--name',runner,'--init','--user','0','--network',network,'--network-alias','runner','--read-only','--tmpfs','/tmp:size=268435456,mode=1777,exec','--cap-drop','ALL','--security-opt','no-new-privileges:true','--pids-limit','128','--memory','768m','--cpus','1','-v',volume+':/knowledge:ro','-e','RP_DSH_RUNNER_TOKEN='+TOKEN,'--entrypoint','/app/.venv/bin/python']
        for cap in ('SETUID','SETGID','CHOWN','DAC_OVERRIDE','FOWNER','KILL'):args+=['--cap-add',cap]
        run(args+[image,'-m','requirement_platform.native_runner'])
        result=run(['docker','run','--rm','--network',network,'--network-alias','api','-v',str(pathlib.Path(__file__).resolve()).replace('\\','/')+':/test.py:ro','--entrypoint','/app/.venv/bin/python',image,'/test.py','--gateway']);print(result.strip())
        check="import pathlib; procs=[p for p in pathlib.Path('/proc').iterdir() if p.name.isdigit()]; assert all(p.stat().st_uid<20000 for p in procs); assert not list(pathlib.Path('/tmp').glob('analysis-*')); print('background-process-and-workspace-cleanup-ok')"
        print(run(['docker','exec','--user','0',runner,'/app/.venv/bin/python','-c',check]).strip())
    except subprocess.CalledProcessError as exc:
        print(exc.stdout);print(exc.stderr);print(subprocess.run(['docker','logs',runner],capture_output=True,text=True).stderr);raise
    finally:
        subprocess.run(['docker','rm','-f',runner],capture_output=True)
        subprocess.run(['docker','volume','rm',volume],capture_output=True)
        subprocess.run(['docker','network','rm',network],capture_output=True)

if __name__=='__main__':gateway() if '--gateway' in sys.argv else host()

