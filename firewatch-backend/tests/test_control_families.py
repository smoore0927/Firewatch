"""Tests for the control families (category) endpoint + control family filter."""

from app.models.control import Control, ControlFramework
from app.services.control_seed import seed_control_families


def _make_csf(db) -> ControlFramework:
    """Build a small CSF-shaped framework using real family strings, then seed families."""
    fw = ControlFramework(name="NIST CSF 2.0", version="2.0", description="csf")
    db.add(fw)
    db.flush()
    # Two authored families (seeded) + one unauthored family with no seed row.
    rows = [
        ("GV.OC-01", "Govern: Organizational Context", "Org mission understood"),
        ("GV.OC-02", "Govern: Organizational Context", "Stakeholders understood"),
        ("ID.AM-01", "Identify: Asset Management", "Inventory of hardware"),
        ("XX.YY-01", "Custom Unauthored Family", "A family with no seeded description"),
    ]
    for cid, family, title in rows:
        db.add(Control(framework_id=fw.id, control_id=cid, title=title, family=family))
    db.commit()
    seed_control_families(db)
    db.refresh(fw)
    return fw


def test_families_endpoint_returns_authored_with_counts(client, owner_user, login_as, db):
    fw = _make_csf(db)
    login_as(owner_user)
    resp = client.get(f"/api/frameworks/{fw.id}/families")
    assert resp.status_code == 200, resp.text
    fams = {f["name"]: f for f in resp.json()}

    gv = fams["Govern: Organizational Context"]
    assert gv["control_count"] == 2
    assert gv["description"] is not None
    assert gv["display_label"] == "Govern (GV)"

    idam = fams["Identify: Asset Management"]
    assert idam["control_count"] == 1
    assert idam["description"] is not None


def test_families_endpoint_includes_derived_unauthored(client, owner_user, login_as, db):
    fw = _make_csf(db)
    login_as(owner_user)
    resp = client.get(f"/api/frameworks/{fw.id}/families")
    fams = {f["name"]: f for f in resp.json()}

    derived = fams["Custom Unauthored Family"]
    assert derived["description"] is None
    assert derived["sort_order"] is None
    assert derived["control_count"] == 1


def test_families_ordered_sort_order_then_name(client, owner_user, login_as, db):
    fw = _make_csf(db)
    login_as(owner_user)
    resp = client.get(f"/api/frameworks/{fw.id}/families")
    names = [f["name"] for f in resp.json()]
    # Authored (sort_order set) come before the unauthored (nulls last).
    assert names.index("Govern: Organizational Context") < names.index("Custom Unauthored Family")
    assert names.index("Identify: Asset Management") < names.index("Custom Unauthored Family")


def test_families_missing_framework_404(client, owner_user, login_as):
    login_as(owner_user)
    resp = client.get("/api/frameworks/99999/families")
    assert resp.status_code == 404


def test_controls_family_filter(client, owner_user, login_as, db):
    fw = _make_csf(db)
    login_as(owner_user)
    resp = client.get(
        f"/api/frameworks/{fw.id}/controls",
        params={"family": "Govern: Organizational Context"},
    )
    assert resp.status_code == 200, resp.text
    ids = {c["control_id"] for c in resp.json()}
    assert ids == {"GV.OC-01", "GV.OC-02"}


def test_controls_family_filter_composes_with_search(client, owner_user, login_as, db):
    fw = _make_csf(db)
    login_as(owner_user)
    resp = client.get(
        f"/api/frameworks/{fw.id}/controls",
        params={"family": "Govern: Organizational Context", "q": "GV.OC-01"},
    )
    assert resp.status_code == 200, resp.text
    ids = {c["control_id"] for c in resp.json()}
    assert ids == {"GV.OC-01"}
