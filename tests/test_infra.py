"""Infrastructure files: Kubernetes, Terraform, nginx and SQL migrations are checked by the program, line by line, without a YAML or HCL library."""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from luna.dev import infra as I
ok = lambda n, c: print(('PASS ' if c else 'FAIL ') + n)

def whats(path, text):
    return ' | '.join(w for _, _, w in I.lint(path, text))

ok('kinds', I.kind_of('a.tf', '') == 'terraform' and I.kind_of('m.sql', '') == 'sql' and I.kind_of('n.conf', 'server {\n}') == 'nginx'
   and I.kind_of('d.yaml', 'apiVersion: v1\nkind: Pod\n') == 'k8s' and I.kind_of('c.yml', 'name: ci\non: push\n') == '' and I.kind_of('x.conf', 'a=1\n') == '')
ok('an unknown file gives nothing', I.lint('x.py', 'import os') == [] and I.summary('x.py', 'import os') == '')

K8S = '''apiVersion: apps/v1
kind: Deployment
metadata:
  name: web
  namespace: default
spec:
  replicas: 1
  template:
    spec:
      hostNetwork: true
      containers:
        - name: app
          image: nginx:latest
          securityContext:
            privileged: true
            allowPrivilegeEscalation: true
          volumeMounts:
            - name: h
              mountPath: /h
      volumes:
        - name: h
          hostPath:
            path: /var
---
apiVersion: v1
kind: Secret
metadata:
  name: db
stringData:
  password: hunter2hunter2
---
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: site
spec:
  rules: []
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: x
roleRef:
  kind: ClusterRole
  name: cluster-admin
'''
w = whats('d.yaml', K8S)
ok('k8s: floating image tag', 'образ без фиксированной версии (nginx:latest)' in w)
ok('k8s: no limits, no probes, root', 'не заданы resources.limits' in w and 'нет readiness/liveness' in w and 'runAsNonRoot' in w)
ok('k8s: privileged, hostNetwork, escalation, hostPath', 'привилегированный' in w and 'hostNetwork' in w and 'allowPrivilegeEscalation' in w and 'hostPath' in w)
ok('k8s: one replica and default namespace', 'одна реплика' in w and 'namespace default' in w)
ok('k8s: secret in the repo, ingress without tls, cluster-admin', 'Secret db' in w and 'Ingress site: Ingress без tls' in w and 'cluster-admin' in w)
ok('k8s: the secret value never appears', 'hunter2' not in w and 'hunter2' not in I.summary('d.yaml', K8S))
sec = [f for f in I.lint('d.yaml', K8S) if 'Secret db' in f[2]]
ok('k8s: lines point into the right document', sec and sec[0][1] == 25)

GOOD = '''apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
  namespace: shop
spec:
  replicas: 3
  template:
    spec:
      containers:
        - name: api
          image: registry.local/api:1.4.2
          resources:
            limits:
              memory: 256Mi
          readinessProbe:
            httpGet: {path: /ok, port: 80}
          securityContext:
            runAsNonRoot: true
'''
ok('k8s: a careful manifest is clean', I.lint('ok.yaml', GOOD) == [])
ok('k8s: a digest-pinned image is fine', not any('образ' in f[2] for f in I.lint('p.yaml', GOOD.replace('registry.local/api:1.4.2', 'reg/api@sha256:abc'))))
ok('k8s: a registry with a port and no tag is still floating', any('образ' in f[2] for f in I.lint('p.yaml', GOOD.replace('registry.local/api:1.4.2', 'localhost:5000/api'))))
ok('k8s: a wildcard role', 'слишком широкие права' in whats('r.yaml', 'apiVersion: rbac.authorization.k8s.io/v1\nkind: Role\nmetadata:\n  name: r\nrules:\n- resources: ["*"]\n  verbs: ["*"]\n'))

TF = '''provider "aws" {
  region = "eu-west-1"
}
resource "aws_security_group" "s" {
  ingress {
    from_port   = 22
    to_port     = 22
    cidr_blocks = ["0.0.0.0/0"]
  }
  ingress {
    from_port   = 443
    to_port     = 443
    cidr_blocks = ["0.0.0.0/0"]
  }
}
resource "aws_s3_bucket" "b" {
  acl = "public-read"
}
resource "aws_db_instance" "d" {
  publicly_accessible = true
  storage_encrypted   = false
  skip_final_snapshot = true
  password            = "supersecret123"
}
data "aws_iam_policy_document" "p" {
  statement {
    actions   = ["*"]
    resources = ["*"]
  }
}
'''
t = I.lint('main.tf', TF)
tw = whats('main.tf', TF)
ok('tf: ssh open to the world is high, https open is only medium', [s for s, ln, _ in t if ln == 8] == ['high'] and [s for s, ln, _ in t if ln == 13] == ['medium'])
ok('tf: public bucket, public database, no encryption', 'бакет открыт' in tw and 'доступна из интернета' in tw and 'шифрование' in tw)
ok('tf: snapshot, iam wildcard, hardcoded secret', 'без финального снимка' in tw and 'IAM-политика' in tw and 'секрет прямо в коде' in tw)
ok('tf: providers not pinned', 'версии провайдеров' in tw)
ok('tf: variables are not secrets', 'секрет' not in whats('v.tf', 'resource "x" "y" {\n  password = var.db_password\n  token = "${var.t}"\n}\n'))
ok('tf: the secret value never appears', 'supersecret' not in tw and 'supersecret' not in I.summary('main.tf', TF))

NG = '''server {
    listen 443 ssl;
    ssl_protocols TLSv1 TLSv1.2;
    server_tokens on;
    add_header Access-Control-Allow-Origin *;
    location /static {
        alias /data/static/;
        autoindex on;
    }
    location /api/ {
        if ($x) { return 403; }
    }
}
'''
nw = whats('site.conf', NG)
ok('nginx: old tls', 'устаревшие протоколы' in nw)
ok('nginx: autoindex, cors, tokens, if', 'autoindex' in nw and 'CORS' in nw and 'server_tokens' in nw and 'if внутри location' in nw)
ok('nginx: alias slash mismatch', 'alias со слешем' in nw)
ok('nginx: a matching alias is fine', 'alias со слешем' not in whats('s.conf', NG.replace('location /static {', 'location /static/ {')))
ok('nginx: modern tls only is clean', 'протоколы' not in whats('s.conf', 'server {\n  ssl_protocols TLSv1.2 TLSv1.3;\n}\n'))
ok('nginx: comments are ignored', whats('s.conf', 'server {\n  # autoindex on;\n}\n') == '')

SQL = '''-- migration 42
ALTER TABLE users ADD COLUMN age int NOT NULL;
ALTER TABLE users ADD COLUMN ok int NOT NULL DEFAULT 0;
DROP TABLE old_users;
DELETE FROM sessions;
DELETE FROM sessions WHERE id = 1;
UPDATE users SET x = 1;
CREATE INDEX idx_u ON users(email);
CREATE INDEX CONCURRENTLY idx_v ON users(name);
ALTER TABLE users ALTER COLUMN id TYPE bigint;
ALTER TABLE users RENAME COLUMN a TO b;
GRANT ALL ON db TO app;
-- DROP TABLE commented;
/* TRUNCATE hidden; */
'''
sq = I.lint('m.sql', SQL)
sw = ' | '.join(w for _, _, w in sq)
ok('sql: not null without default (only the one without)', sw.count('NOT NULL без DEFAULT') == 1)
ok('sql: drop and delete without where', 'удаляет данные безвозвратно (DROP TABLE old_users)' in sw and sw.count('без WHERE') == 2)
ok('sql: index, type change, rename, grant', 'CONCURRENTLY' in sw and 'смена типа' in sw and 'переименование' in sw and 'GRANT ALL' in sw)
ok('sql: concurrent index is not flagged', sw.count('индекс строится') == 1)
ok('sql: commented statements are ignored', 'commented' not in sw and 'hidden' not in sw and 'TRUNCATE' not in sw)
lines = {w[:30]: ln for _, ln, w in sq}
ok('sql: line numbers survive comment stripping', any(ln == 4 and 'DROP' in w for _, ln, w in sq) and any(ln == 5 and 'без WHERE' in w for _, ln, w in sq) and any(ln == 7 and 'без WHERE' in w for _, ln, w in sq))

s = I.summary('m.sql', SQL, limit=3)
ok('summary is capped and severity-ordered', 'ПРОВЕРКА ПРОГРАММЫ' in s and s.count('\n- ') == 4 and 'и ещё' in s and s.index('[high]') < s.index('[medium]') if '[medium]' in s else 'и ещё' in s)

# ---- wiring: the project audit and the file she is shown ----
import tempfile, pathlib, time
from luna.dev import devtools, codescan
root = pathlib.Path(tempfile.mkdtemp()) / 'infra_proj'; (root / 'k8s').mkdir(parents=True)
(root / 'k8s' / 'd.yaml').write_text(K8S, encoding='utf-8')
(root / 'main.tf').write_text(TF, encoding='utf-8')
(root / 'nginx.conf').write_text(NG, encoding='utf-8')
(root / 'm.sql').write_text(SQL, encoding='utf-8')
rep = codescan.scan(str(root))
ok('audit: infrastructure findings reach the report', 'privileged' in rep.lower() or 'привилегирован' in rep)
ok('audit: all four kinds are seen', all(k in rep for k in ('k8s/d.yaml', 'main.tf', 'nginx.conf', 'm.sql')))
ok('audit: no secret value leaks', 'hunter2' not in rep and 'supersecret' not in rep)
f = root / 'm.sql'
devtools.FOUND['tk'] = {'path': str(f), 'label': 'm.sql', 't': time.time()}
got = devtools.read_code('tk')
ok('read_code: the file comes with the program check', got['text'].startswith('-- migration 42') and 'ПРОВЕРКА ПРОГРАММЫ' in got['text'])
(root / 'plain.sql').write_text('SELECT 1;\n', encoding='utf-8')
devtools.FOUND['t2'] = {'path': str(root / 'plain.sql'), 'label': 'plain.sql', 't': time.time()}
ok('read_code: a clean file comes as it is', devtools.read_code('t2')['text'] == 'SELECT 1;\n')
devtools.GRANTED.clear()
