"""P7-int slice 1: the View API shows staleness and forgetting state (fields, endpoints, inventory counts)."""

from __future__ import annotations

import json
import math

import pytest

from knewat.activation import Activation
from knewat.api import models as M
from knewat.embed import HashEmbedder
from knewat.engram import Engram
from knewat.graph.tenancy import graph_name
from knewat.staleness import Staleness

CODE = "C:/repo/app/payments.py"
DOC = "C:/repo/docs/payments.md"
OPEN = 9_999_999_999_999


@pytest.fixture
def svc(client, seeded):
    """(graph, Staleness, Activation) bound to the seeded tenant."""
    g = graph_name(seeded["tenant"])
    eng = Engram(client, g, HashEmbedder())
    return g, Staleness(client, g, engram=eng), Activation(client, g)


def fact_nodes(api, tenant, **params):
    body = M.GraphResponse(**api.get(f"/api/{tenant}/graph", params=params).json())
    return {n.id: n for n in body.nodes if n.label == "Fact"}, body


def make_suspect(svc, fact_id):
    _, st, _ = svc
    st.anchor_fact(fact_id, CODE, hash="h0")
    st.mark_changed([{"path": CODE, "new_hash": "h1"}], commit="abc123", at=5_000)


def test_fact_nodes_carry_staleness_and_forgetting_fields(api, seeded):
    facts, _ = fact_nodes(api, seeded["tenant"])
    f1, f2 = facts[seeded["f1"]], facts[seeded["f2"]]
    for f in (f1, f2):  # old data has none of the P7 properties: the API reports the defaults
        assert f.props["verify_state"] == "verified" and f.props["suspect_since"] == 0
        assert 0.0 <= f.props["surprise"] <= 1.0 and f.props["pinned"] is False  # K sets surprise at write
        assert isinstance(f.props["activation"], float) and math.isfinite(f.props["activation"])
        assert isinstance(f.props["protected"], bool)
    assert f1.props["status"] == "superseded" and f2.props["status"] == "active"
    assert f2.props["protected"] is True  # a Decision rests on it (record_decision in the seed)
    assert f1.props["protected"] is False  # the superseded side is not protected, only the superseding fact
    # the other node types do not get fact-only fields
    _, body = fact_nodes(api, seeded["tenant"])
    assert all("activation" not in n.props for n in body.nodes if n.label != "Fact")


def test_a_suspect_fact_and_its_code_nodes_show_in_the_graph(api, seeded, svc):
    make_suspect(svc, seeded["f2"])
    facts, body = fact_nodes(api, seeded["tenant"])
    f2 = facts[seeded["f2"]]
    assert f2.props["verify_state"] == "suspect" and f2.props["suspect_since"] == 5_000
    labels = {n.label for n in body.nodes}
    assert {"CodeAnchor", "Change"} <= labels
    anchor = next(n for n in body.nodes if n.label == "CodeAnchor")
    assert anchor.props["path"] == CODE
    change = next(n for n in body.nodes if n.label == "Change")
    assert change.props["commit"] == "abc123"
    types = {e.type for e in body.edges}
    assert {"ANCHORED_TO", "SUSPECTED", "TOUCHED"} <= types
    only = M.GraphResponse(**api.get(f"/api/{seeded['tenant']}/graph", params={"labels": "Change"}).json())
    assert {n.label for n in only.nodes} == {"Change"}


def test_pinned_and_dormant_show_as_stored(api, seeded, svc):
    g, _, act = svc
    assert act.pin(seeded["f1"], True)
    facts, _ = fact_nodes(api, seeded["tenant"])
    assert facts[seeded["f1"]].props["pinned"] is True
    # a dormant fact (what memory_sweep writes) is a normal Fact node with status 'dormant'
    svc_client = act.client
    svc_client.graph(g).query("MATCH (f:Fact {id: $id}) SET f.status = 'dormant'", {"id": seeded["f2"]})
    facts, _ = fact_nodes(api, seeded["tenant"])
    assert facts[seeded["f2"]].props["status"] == "dormant"


def test_activation_is_absent_when_forgetting_is_off(api, seeded, monkeypatch):
    monkeypatch.setenv("KNEWAT_FORGETTING", "off")
    facts, _ = fact_nodes(api, seeded["tenant"])
    f2 = facts[seeded["f2"]]
    assert "activation" not in f2.props and "protected" not in f2.props
    assert f2.props["verify_state"] == "verified" and f2.props["pinned"] is False


def test_activation_is_computed_in_batches_of_at_most_200(api, seeded, client, monkeypatch):
    g = graph_name(seeded["tenant"])
    client.graph(g).query(
        "UNWIND range(1, 450) AS i CREATE (:Fact {id: 'bulk-' + toString(i), created_at: i, "
        "status: 'active', "
        "predicate: 'p', value: toString(i), valid_to: 9999999999999})"
    )
    seen: list[int] = []
    orig = Activation.compute

    def spy(self, fact_ids, now=None):
        ids = list(fact_ids)
        seen.append(len(ids))
        return orig(self, ids, now)

    monkeypatch.setattr(Activation, "compute", spy)
    facts, body = fact_nodes(api, seeded["tenant"], limit=1000)
    assert len(facts) == 452 and all("activation" in f.props for f in facts.values())
    # one compute() call per graph request, which itself queries 200 ids at a time
    assert seen == [452]
    from knewat.activation.service import MAX_IDS

    assert MAX_IDS == 200


def test_why_and_node_info_carry_the_same_fields(api, seeded, svc):
    make_suspect(svc, seeded["f2"])
    body = M.WhyResponse(**api.get(f"/api/{seeded['tenant']}/why/{seeded['decision']}").json())
    node = next(n for n in body.result.nodes if n.id == seeded["f2"])
    assert node.props["verify_state"] == "suspect" and node.props["suspect_since"] == 5_000
    assert node.props["pinned"] is False and 0.0 <= node.props["surprise"] <= 1.0
    assert node.props["protected"] is True and isinstance(node.props["activation"], float)


# -- endpoints -----------------------------------------------------------------------------------------
def test_verify_queue_lists_suspect_facts_with_activation(api, seeded, svc):
    t = seeded["tenant"]
    assert M.VerifyQueueResponse(**api.get(f"/api/{t}/verify-queue").json()).rows == []
    make_suspect(svc, seeded["f2"])
    body = M.VerifyQueueResponse(**api.get(f"/api/{t}/verify-queue").json())
    (row,) = body.rows
    assert row.fact_id == seeded["f2"] and row.verify_state == "suspect"
    assert row.reason == "changed in abc123 (C:/repo/app/payments.py)"
    assert row.decisions_count == 1 and row.anchors == [CODE]
    assert row.change is not None and row.change.commit == "abc123" and row.change.paths == [CODE]
    assert row.activation is not None and math.isfinite(row.activation) and row.protected is True
    assert (row.entity, row.predicate, row.value) == ("API", "version", "v2")


def test_verify_queue_limit_scope_and_off(api, seeded, svc, monkeypatch):
    t = seeded["tenant"]
    make_suspect(svc, seeded["f2"])
    assert api.get(f"/api/{t}/verify-queue", params={"limit": 0}).status_code == 422
    assert api.get(f"/api/{t}/verify-queue", params={"limit": 201}).status_code == 422
    assert api.get(f"/api/{t}/verify-queue", params={"scope_id": "nope"}).json()["rows"] == []
    monkeypatch.setenv("KNEWAT_FORGETTING", "off")
    (row,) = M.VerifyQueueResponse(**api.get(f"/api/{t}/verify-queue").json()).rows
    assert row.activation is None and row.protected is None  # absent when forgetting is off


def test_docs_to_update_lists_docs_describing_changed_code(api, seeded, svc, client):
    g, st, _ = svc
    t = seeded["tenant"]
    assert M.DocsToUpdateResponse(**api.get(f"/api/{t}/docs-to-update").json()).docs == []
    from knewat.lineage import Lineage

    sid = Lineage(client, g).create_source(DOC, "doc", title="Payments guide")
    st.describe_code(sid, CODE, hash="h0")
    st.mark_changed([{"path": CODE, "new_hash": "h1"}], commit="abc123", at=5_000)
    body = M.DocsToUpdateResponse(**api.get(f"/api/{t}/docs-to-update").json())
    (doc,) = body.docs
    assert doc.source_id == sid and doc.uri == DOC and doc.title == "Payments guide"
    assert doc.changes[0].commit == "abc123" and doc.changes[0].paths == [CODE]
    assert api.get(f"/api/{t}/docs-to-update", params={"since": 6_000}).json()["docs"] == []


def test_memory_strength_endpoint(api, seeded):
    t = seeded["tenant"]
    r = api.get(f"/api/{t}/memory-strength/{seeded['f2']}")
    assert r.status_code == 200, r.text
    body = M.MemoryStrengthResponse(**r.json())
    assert body.fact_id == seeded["f2"] and body.protected is True and body.status == "active"
    assert body.activation is not None and body.multiplier >= body.floor
    assert any(x.startswith("decision:") for x in body.protect_reasons)
    assert "activation" in body.explanation
    assert api.get(f"/api/{t}/memory-strength/nope").status_code == 404
    assert api.get("/api/not-a-tenant!/memory-strength/x").status_code == 404


def test_memory_strength_does_not_count_as_a_use(api, seeded, client):
    t = seeded["tenant"]
    g = graph_name(t)
    n = client.graph(g).ro_query("MATCH ()-[r:READ]->() RETURN count(r)").result_set[0][0]
    api.get(f"/api/{t}/memory-strength/{seeded['f2']}")
    api.get(f"/api/{t}/verify-queue")
    assert client.graph(g).ro_query("MATCH ()-[r:READ]->() RETURN count(r)").result_set[0][0] == n


def test_unknown_tenant_on_new_endpoints(api):
    for path in ("verify-queue", "docs-to-update", "memory-strength/x"):
        assert api.get(f"/api/nosuchtenant/{path}").status_code == 404, path


# -- inventory -----------------------------------------------------------------------------------------
def counts(inv):
    return (inv.suspect_facts, inv.dormant_facts, inv.pinned_facts, inv.changes, inv.code_anchors)


def test_inventory_counts_suspect_dormant_pinned_changes_anchors(api, seeded, svc, client):
    t = seeded["tenant"]
    inv = M.InventoryResponse(**api.get(f"/api/{t}/inventory").json())
    assert counts(inv) == (0, 0, 0, 0, 0)
    make_suspect(svc, seeded["f2"])
    svc[2].pin(seeded["f1"], True)
    g = graph_name(t)
    client.graph(g).query(
        "CREATE (:Fact {id: 'd1', status: 'dormant', created_at: 1, valid_to: 9999999999999}), "
        "(:Fact {id: 'due', status: 'active', verify_after: 1000, created_at: 1, valid_to: 9999999999999})"
    )
    inv = M.InventoryResponse(**api.get(f"/api/{t}/inventory").json())
    # f2 is suspect by mark_changed, 'due' by a passed review date; the dormant fact is not counted as suspect
    assert counts(inv) == (2, 1, 1, 1, 1)
    labels = {x.label: x.count for x in inv.labels}
    assert labels["Change"] == 1 and labels["CodeAnchor"] == 1
    assert {"ANCHORED_TO", "SUSPECTED", "TOUCHED"} <= {e.type for e in inv.edge_types}
    assert inv.nodes_total == sum(labels.values())


def test_responses_are_json_serialisable_numbers(api, seeded):
    raw = api.get(f"/api/{seeded['tenant']}/graph").text
    assert "Infinity" not in raw and "NaN" not in raw
    json.loads(raw)
