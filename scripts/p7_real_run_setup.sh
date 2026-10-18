#!/usr/bin/env bash
# Real-run setup (P7-int): anchors, baseline, one edit, scan. Run from knewat/ with the slot-93 MCP server on :8793.
set -e
UV=~/AppData/Roaming/Python/Python311/Scripts/uv.exe
S=C:/Users/ACER/AppData/Local/hermes/cache/scratch
CLONE=$S/physio-clone/pv-core-api
export UV_PROJECT_ENVIRONMENT=.venv-p7int FALKORDB_PORT=6393
$UV run python - <<PY
from knewat.graph.client import GraphClient
from knewat.graph.tenancy import graph_name
from knewat.embed import get_embedder
from knewat.engram import Engram
from knewat.staleness import Staleness
from knewat.codescan.paths import canonical_path
c = GraphClient(); g = graph_name('physio_test')
st = Staleness(c, g, engram=Engram(c, g, get_embedder()))
path = canonical_path('$CLONE/app/services/payments/gateway.py')
FACT = '79e31583-b485-4db3-93f0-18578bc6f01b'
print(st.anchor_fact(FACT, path, 'normalize_method')['anchor_id'])
readme = c.ro(g, 'staleness/source_by_uri', {'uri': 'C:/Change_folder_after_HDD/physiotherapy/pv-core-api/README.md'})[0]['id']
print(st.describe_code(readme, path, 'normalize_method')['anchor_id'])
PY
$UV run knewat code baseline --repo $CLONE --tenant physio_test --url http://127.0.0.1:8793
python - <<PY
p = '$CLONE/app/services/payments/gateway.py'
b = open(p, 'rb').read()
old = b'    m = (method or "").strip().lower()\r\n    return _METHOD_ALIASES.get(m, m)\r\n'
assert old in b
new = b'    m = (method or "").strip().lower()\r\n    # imepay is no longer aliased to khalti: it is rejected as an unknown method\r\n    return m\r\n'
open(p, 'wb').write(b.replace(old, new))
PY
$UV run knewat code scan --repo $CLONE --tenant physio_test --url http://127.0.0.1:8793 --paths app/services/payments/gateway.py
