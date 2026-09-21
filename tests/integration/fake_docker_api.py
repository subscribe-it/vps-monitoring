"""Atrapa Docker API na gnieździe unix — realistyczne dane w formacie Swarma."""
import http.server, json, os, socketserver, urllib.parse

SOCK = "/tmp/fake-docker.sock"

SERVICES = [
  {"ID":"s1","Version":{"Index":1},"UpdatedAt":"2026-09-21T22:00:00Z",
   "Spec":{"Name":"ventiplan-prod_api","Labels":{
       "traefik.enable":"true",
       "traefik.http.routers.vp-api.rule":"Host(`api.ventiplan.pl`)",
       "traefik.http.services.vp-api.loadbalancer.server.port":"3000"},
     "TaskTemplate":{"ContainerSpec":{"Image":"ghcr.io/subscribe-it/stropio-api:prod"}},
     "Mode":{"Replicated":{"Replicas":1}}}},
  {"ID":"s2","Version":{"Index":2},"UpdatedAt":"2026-09-21T22:10:00Z",
   "Spec":{"Name":"star-sign_frontend","Labels":{
       "traefik.enable":"true",
       "traefik.http.routers.ss.rule":"Host(`star-sign.pl`) && PathPrefix(`/app`)"},
     "TaskTemplate":{"ContainerSpec":{"Image":"ghcr.io/subscribe-it/star-sign-frontend:main"}},
     "Mode":{"Replicated":{"Replicas":2}}}},
  {"ID":"s3","Version":{"Index":3},"UpdatedAt":"2026-09-21T22:20:00Z",
   "Spec":{"Name":"kosmetix-staging_worker","Labels":{},
     "TaskTemplate":{"ContainerSpec":{"Image":"ghcr.io/subscribe-it/kosmetix-shop/medusa:staging"}},
     "Mode":{"Replicated":{"Replicas":1}}}},
  {"ID":"s4","Version":{"Index":4},"UpdatedAt":"2026-09-21T22:30:00Z",
   "Spec":{"Name":"monitoring_self","Labels":{"monitoring.io/skip":"true"},
     "TaskTemplate":{"ContainerSpec":{"Image":"x"}},"Mode":{"Replicated":{"Replicas":1}}}},
  {"ID":"s5","Version":{"Index":5},"UpdatedAt":"2026-09-21T22:40:00Z",
   "Spec":{"Name":"portainer_agent","Labels":{},
     "TaskTemplate":{"ContainerSpec":{"Image":"portainer/agent:2.33.3"}},"Mode":{"Global":{}}}},
]
TASKS = [
  {"ID":"t1","ServiceID":"s1","DesiredState":"running","Status":{"State":"running","ContainerStatus":{"ContainerID":"c1"}},"CreatedAt":"2026-09-21T22:00:00Z"},
  {"ID":"t2","ServiceID":"s2","DesiredState":"running","Status":{"State":"running","ContainerStatus":{"ContainerID":"c2"}},"CreatedAt":"2026-09-21T22:10:00Z"},
  {"ID":"t3","ServiceID":"s2","DesiredState":"running","Status":{"State":"failed","Err":"task: non-zero exit (137)"},"CreatedAt":"2026-09-21T22:11:00Z"},
  {"ID":"t4","ServiceID":"s3","DesiredState":"running","Status":{"State":"running","ContainerStatus":{"ContainerID":"c3"}},"CreatedAt":"2026-09-21T22:20:00Z"},
  {"ID":"t5","ServiceID":"s5","DesiredState":"running","Status":{"State":"running","ContainerStatus":{"ContainerID":"c5"}},"CreatedAt":"2026-09-21T22:40:00Z"},
]
CONTAINERS = [
  {"Id":"c1","Names":["/ventiplan-prod_api.1.abc"],"State":"running","Labels":{
     "com.docker.swarm.service.name":"ventiplan-prod_api","com.docker.swarm.service.id":"s1",
     "com.docker.swarm.stack.namespace":"ventiplan-prod"}},
  {"Id":"c2","Names":["/star-sign_frontend.1.def"],"State":"running","Labels":{
     "com.docker.swarm.service.name":"star-sign_frontend","com.docker.swarm.service.id":"s2",
     "com.docker.swarm.stack.namespace":"star-sign"}},
  {"Id":"c3","Names":["/kosmetix-staging_worker.1.ghi"],"State":"running","Labels":{
     "com.docker.swarm.service.name":"kosmetix-staging_worker","com.docker.swarm.service.id":"s3",
     "com.docker.swarm.stack.namespace":"kosmetix-staging"}},
  {"Id":"c5","Names":["/portainer_agent.xyz"],"State":"running","Labels":{
     "com.docker.swarm.service.name":"portainer_agent","com.docker.swarm.service.id":"s5",
     "com.docker.swarm.stack.namespace":"portainer"}},
]
HEALTH = {"c3":{"Status":"unhealthy","FailingStreak":5,"Log":[{"ExitCode":1}]}}
STATS = {"cpu_stats":{"cpu_usage":{"total_usage":200000000},"system_cpu_usage":20000000000,"online_cpus":4},
         "precpu_stats":{"cpu_usage":{"total_usage":100000000},"system_cpu_usage":10000000000},
         "memory_stats":{"usage":134217728,"limit":536870912}}

def body_for(path):
    p = urllib.parse.urlparse(path).path
    if p == "/services": return SERVICES
    if p == "/tasks": return TASKS
    if p.startswith("/containers/json"): return CONTAINERS
    if p.startswith("/containers/") and p.endswith("/json"):
        cid = p.split("/")[2]
        return {"Id":cid,"State":{"Status":"running","Health":HEALTH.get(cid,{"Status":"healthy"})},
                "Config":{"Labels":next((c["Labels"] for c in CONTAINERS if c["Id"]==cid),{})}}
    if p.startswith("/containers/") and p.endswith("/stats"):
        return STATS
    if p == "/system/df":
        return {"LayersSize":1000,"Images":[{"Size":100,"Containers":1}],
                "Volumes":[{"UsageData":{"Size":500,"RefCount":1}},{"UsageData":{"Size":0,"RefCount":0}}],
                "BuildCache":[],"Containers":[{"SizeRw":10},{"SizeRw":20}]}
    if p == "/info": return {"Swarm":{"LocalNodeState":"active","ControlAvailable":True}}
    if p == "/version": return {"Version":"29.2.1","ApiVersion":"1.51"}
    return None

class H(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    def do_GET(self):
        dane = body_for(self.path)
        if dane is None:
            self.send_response(404); self.send_header("Content-Length","0"); self.end_headers(); return
        tresc = json.dumps(dane).encode()
        self.send_response(200); self.send_header("Content-Type","application/json")
        self.send_header("Content-Length",str(len(tresc))); self.end_headers(); self.wfile.write(tresc)
    def log_message(self,*a): pass

class UnixServer(socketserver.ThreadingUnixStreamServer):
    allow_reuse_address = True

if os.path.exists(SOCK): os.unlink(SOCK)
srv = UnixServer(SOCK, H)
os.chmod(SOCK, 0o666)
print("atrapa Docker API nasłuchuje na", SOCK, flush=True)
srv.serve_forever()
