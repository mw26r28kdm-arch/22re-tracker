"""Garage Tracker browser test suite.
Run:  python tests/smoke.py                 # serves this folder locally
      BASE_URL=https://.../22re-tracker/ python tests/smoke.py   # against live
Needs: pip install playwright && python -m playwright install chromium
       (or set CHROME_PATH to an installed Chrome/Chromium)
Screenshots: set SCREENS=/some/dir to save them."""
import os, sys, json, shutil, tempfile, threading, http.server, functools, traceback
from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = os.environ.get("BASE_URL")
SCREENS = os.environ.get("SCREENS")
CHROME = os.environ.get("CHROME_PATH")
results = []

def serve():
    class Q(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a): pass
    h = functools.partial(Q, directory=ROOT)
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), h)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{srv.server_port}/", srv

def test(name):
    def deco(fn):
        def run(*a):
            try: fn(*a); results.append((name, True, "")); print("PASS", name)
            except Exception as e: results.append((name, False, str(e))); print("FAIL", name, "-", e); traceback.print_exc(limit=1)
        return run
    return deco

class App:
    def __init__(self, p, url, w, h):
        self.dir = tempfile.mkdtemp(prefix="gt-")
        kw = dict(headless=True, viewport={"width": w, "height": h})
        if CHROME: kw["executable_path"] = CHROME
        self.ctx = p.chromium.launch_persistent_context(self.dir, **kw)
        self.url = url; self.errors = []; self.pg = None; self.open()
    def open(self):
        if self.pg: self.pg.close()
        pg = self.ctx.new_page(); self.pg = pg
        pg.on("pageerror", lambda e: self.errors.append(str(e)))
        pg.on("console", lambda m: m.type == "error" and self.errors.append(m.text))
        pg.on("dialog", lambda d: d.accept())
        pg.goto(self.url + "index.html"); pg.wait_for_function("document.getElementById('app').children.length>0", timeout=15000)
        return pg
    def nav(self, label):
        pg = self.pg; pg.click("#menuBtn"); pg.wait_for_timeout(250)
        pg.click(f"#nav button:text-is('{label}')" if False else f"#nav button:has-text('{label}')"); pg.wait_for_timeout(150)
        assert pg.inner_text("#viewTitle") == label, pg.inner_text("#viewTitle")
    def shot(self, name):
        if SCREENS: os.makedirs(SCREENS, exist_ok=True); self.pg.screenshot(path=os.path.join(SCREENS, name), full_page=False)
    def close(self): self.ctx.close(); shutil.rmtree(self.dir, ignore_errors=True)

def main():
    url, srv = (BASE.rstrip("/") + "/", None) if BASE else serve()
    print("Testing", url)
    with sync_playwright() as p:
        for w, h, tag in [(390, 844, "phone"), (1440, 900, "laptop")]:
            a = App(p, url, w, h)
            @test(f"[{tag}] loads, both vehicles, no console errors")
            def _():
                a.pg.wait_for_selector(".veh")
                names = [x.split("\n")[0] for x in a.pg.locator(".veh").all_inner_texts()]
                assert "1993 Toyota Pickup" in names and "2019 Audi Q5" in names, names
                a.pg.wait_for_timeout(500); assert not a.errors, a.errors
            _()
            if tag == "laptop":
                @test("[laptop] notes + specs screenshots")
                def _():
                    a.nav("Checklist"); a.pg.click("[data-notes='s2-1']"); a.pg.fill("#nd-s2-1", "Drain plug torque 27 foot-pounds"); a.pg.click("[data-post='s2-1']")
                    a.pg.wait_for_selector("#specOffer"); a.pg.locator("#specOffer").scroll_into_view_if_needed(); a.shot("notes-laptop.png")
                    a.pg.click("#of-save"); a.nav("Specs"); a.shot("specs-laptop.png")
                    a.pg.evaluate("set(()=>{const v=G.vehicles[0];v.mileageLog=[{date:'2026-05-01',miles:110000},{date:'2026-10-01',miles:119000}];v.log.push({id:'a',date:'2026-06-02',item:'Oil',action:'x',cost:45},{id:'b',date:'2026-08-15',item:'Plugs',action:'x',cost:62},{id:'c',date:'2026-10-02',item:'Brakes',action:'x',cost:180});v.info.mileage='119000';const iv=G.intervals[0];iv.lastDoneMiles=112000;iv.lastDoneDate='2026-01-01';G.inventory.push({id:'i1',vehicleId:'v1',name:'Oil filter',partNumber:'90915-YZZD1',qtyOnHand:1,reorderAt:1,taskIds:[]})})")
                    a.nav("My Garage"); a.shot("due-laptop.png"); a.nav("Inventory"); a.shot("inventory-laptop.png"); a.nav("Cost per Mile"); a.shot("costs-laptop.png")
                _()
                a.close(); continue
            pg = a.pg
            @test("menu drawer opens, lists sections, closes")
            def _():
                pg.click("#menuBtn"); pg.wait_for_timeout(300)
                assert pg.get_attribute("#menuBtn", "aria-expanded") == "true"
                items = pg.locator("#nav button").all_inner_texts()
                for s in ["My Garage", "Checklist", "All Tasks", "Maintenance Log", "Diagnostics", "Parts", "Specs", "Import / Export", "Service Due", "Inventory", "Cost per Mile"]:
                    assert any(s in i for i in items), s
                pg.keyboard.press("Escape"); pg.wait_for_timeout(250)
                assert pg.get_attribute("#menuBtn", "aria-expanded") == "false"
            _()
            @test("truck checklist: 53 items in 10 sections")
            def _():
                a.nav("Checklist")
                assert pg.locator(".item .check").count() == 53
                assert pg.locator("main section.card:has(.item)").count() == 10
            _()
            @test("All Tasks filters change rows")
            def _():
                a.nav("Checklist"); pg.locator(".item .check").first.check(); pg.wait_for_timeout(150)
                a.nav("All Tasks"); exp = {("all","all"):72,("all","open"):71,("all","complete"):1,("v1","all"):53,("v1","complete"):1,("v2","all"):19,("v2","complete"):0}
                for (v, s), n in exp.items():
                    pg.select_option("#fVeh", v); pg.select_option("#fStatus", s); pg.wait_for_timeout(80)
                    assert pg.locator(".task-row").count() == n, (v, s, pg.locator(".task-row").count())
                pg.select_option("#fVeh", "all"); pg.select_option("#fStatus", "all")
            _()
            @test("notes: post, edit, delete with dates")
            def _():
                a.nav("Checklist"); pg.click("[data-notes='s2-2']")
                for t in ["First note", "Second note", "Third note"]:
                    pg.fill("#nd-s2-2", t); pg.click("[data-post='s2-2']"); pg.wait_for_timeout(100)
                assert pg.locator(".notes-panel [data-note]").count() == 3
                assert "Posted" in pg.locator(".notes-panel [data-note]").first.inner_text()
                assert "(3)" in pg.inner_text("[data-notes='s2-2']")
                pg.locator(".notes-panel [data-note]").nth(1).locator("button:has-text('Edit')").click()
                pg.locator(".notes-panel textarea[id^=ne-]").fill("Second note edited"); pg.click(".notes-panel button:has-text('Save')"); pg.wait_for_timeout(100)
                assert "edited" in pg.locator(".notes-panel [data-note]").nth(1).inner_text() and "Second note edited" in pg.inner_text(".notes-panel")
                pg.locator(".notes-panel [data-note]").nth(2).locator("button:has-text('Delete')").click(); pg.wait_for_timeout(100)
                assert pg.locator(".notes-panel [data-note]").count() == 2
            _()
            @test("notes persist after closing and reopening")
            def _():
                a.open(); a.nav("Checklist")
                assert "(2)" in a.pg.inner_text("[data-notes='s2-2']")
                a.pg.click("[data-notes='s2-2']"); assert "Second note edited" in a.pg.inner_text(".notes-panel")
            _()
            pg = a.pg
            @test("71 verified 22RE specs seeded, badges, idempotent")
            def _():
                assert pg.evaluate("G.specs.filter(x=>x.seeded).length") == 71
                assert pg.evaluate("seedSpecs()") == 0 and pg.evaluate("G.specs.filter(x=>x.seeded).length") == 71
                pg.evaluate("set(()=>{const x=G.specs.find(y=>y.name==='Oil pan drain plug');x.notes='mine';x.edited=true})")
                a.open(); assert a.pg.evaluate("G.specs.filter(x=>x.seeded).length") == 71 and a.pg.evaluate("G.specs.find(y=>y.name==='Oil pan drain plug').notes") == "mine"
                a.pg.evaluate("set(()=>{G.specs=G.specs.filter(y=>y.name!=='Radiator cap relief pressure')})"); a.open()
                assert a.pg.evaluate("G.specs.filter(x=>x.seeded).length") == 70, "deleted seed came back"
                a.nav("Specs"); a.pg.fill("#specQ", "drain plug torque"); a.pg.wait_for_timeout(400)
                row = a.pg.locator(".spec-row", has_text="Oil pan drain plug"); assert row.count() == 1
                t = row.inner_text(); assert "25 N·m" in t and "18 ft-lbf" in t and "Factory manual" in t, t
                assert a.pg.locator(".spec-row [data-conf]").count() >= 1
                a.pg.fill("#specQ", ""); a.pg.wait_for_timeout(300)
                assert "s2-1" in a.pg.evaluate("G.specs.find(y=>y.name==='Oil pan drain plug').taskIds")
                a.nav("Checklist")
            _()
            pg = a.pg
            @test("spec offer from note saves structured spec")
            def _():
                pg.click("[data-notes='s2-1']"); pg.fill("#nd-s2-1", "Drain plug torque 27 foot-pounds"); pg.click("[data-post='s2-1']")
                pg.wait_for_selector("#specOffer")
                assert pg.input_value("#of-value") == "27" and pg.input_value("#of-unit") == "ft-lb" and pg.input_value("#of-topic") == "Torque"
                a.shot("notes-phone.png")
                n0 = pg.evaluate("G.specs.length")
                pg.wait_for_timeout(200); assert pg.evaluate("G.specs.length") == n0, "auto-saved"
                pg.click("#of-save"); pg.wait_for_timeout(150)
                assert pg.evaluate("G.specs.length") == n0 + 1
                sp = pg.evaluate("G.specs[G.specs.length-1]")
                assert sp["value"] == "27" and sp["unit"] == "ft-lb" and sp["topic"] == "Torque" and sp["vehicleId"] == "v1" and sp["taskIds"] == ["s2-1"], sp
            _()
            @test("spec search finds it")
            def _():
                a.nav("Specs"); pg.fill("#specQ", "drain plug torque"); pg.wait_for_timeout(400)
                txt = pg.inner_text("main"); assert "27 ft-lb" in txt and "25 N·m" in txt and "18 ft-lbf" in txt, txt[:300]
                a.shot("specs-phone.png")
                pg.fill("#specQ", "zzqx nothing"); pg.wait_for_timeout(400); assert pg.locator(".spec-row").count() == 0
                pg.fill("#specQ", ""); pg.wait_for_timeout(300)
            _()
            @test("checking linked item surfaces spec")
            def _():
                a.nav("Checklist"); pg.locator("[data-id='s2-1'].check").check(); pg.wait_for_timeout(200)
                assert pg.is_visible("#sheet") and "27" in pg.inner_text("#sheet")
                pg.click("#sheet button:has-text('Close')")
            _()
            @test("export has notes+specs; import round-trips")
            def _():
                exp = pg.evaluate("JSON.stringify(exportGarage())"); d = json.loads(exp)
                assert d["specs"] and any(i.get("noteLog") for s in d["vehicles"][0]["sections"] for i in s["items"])
                ns = len(d["specs"])
                pg.evaluate("set(()=>{G.specs=[];G.vehicles[0].sections.forEach(s=>s.items.forEach(i=>i.noteLog=[]))})")
                pg.evaluate("t=>doImport(t)", exp); pg.wait_for_timeout(200)
                assert pg.evaluate("G.specs.length") == ns and pg.evaluate("G.vehicles[0].sections.flatMap(s=>s.items).filter(i=>i.noteLog&&i.noteLog.length).length") == 2
                vexp = pg.evaluate("JSON.stringify(exportVehicle())"); assert json.loads(vexp)["specs"]
            _()
            @test("migration: old single-truck data keeps legacy notes")
            def _():
                snap = pg.evaluate("JSON.stringify(exportGarage())")
                old = {"sections":[{"title":"Old","items":[{"id":"s1-1","label":"Legacy","checked":True,"notes":"legacy note text","part":"","cost":"5"}]}],"log":[{"date":"2026-10-01","itemId":"s1-1","item":"Legacy","action":"Completed","part":"","cost":5}],"cases":[],"tests":[]}
                pg.evaluate("""o=>new Promise(r=>{const q=indexedDB.open('tracker22re');q.onsuccess=()=>{const t=q.result.transaction('kv','readwrite');t.objectStore('kv').put(o,'state');t.oncomplete=r}})""", old)
                a.open(); p2 = a.pg
                assert p2.evaluate("G.vehicles.length") == 2 and p2.evaluate("G.vehicles[0].sections[0].items[0].notes") == "legacy note text"
                assert p2.evaluate("Array.isArray(G.specs)")
                p2.evaluate("""t=>doImport(t)""", json.dumps({"sections": old["sections"], "log": old["log"], "cases": [], "tests": []}))
                assert p2.evaluate("V().sections[0].items[0].notes") == "legacy note text"
                p2.evaluate("t=>doImport(t)", snap); p2.wait_for_timeout(200)
                assert p2.evaluate("G.vehicles[0].sections.length") == 10 and p2.evaluate("G.specs.filter(x=>x.seeded).length") == 70
            _()
            pg = a.pg
            @test("manifest valid + service worker controls page")
            def _():
                m = a.pg.evaluate("fetch('manifest.json').then(r=>r.json())")
                assert m["display"] == "standalone" and m["start_url"] and m["name"]
                assert {"192x192", "512x512"} <= {i["sizes"] for i in m["icons"]}
                assert a.pg.evaluate("fetch('apple-touch-icon.png').then(r=>r.ok)")
                a.pg.wait_for_function("navigator.serviceWorker.ready.then(()=>true)"); a.open()
                assert a.pg.evaluate("!!navigator.serviceWorker.controller")
            _()

            # ================= build 2 =================
            pg = a.pg
            @test("interval due logic at mileage/date boundaries")
            def _():
                f = lambda iv, mi, t: pg.evaluate("([iv,mi,t])=>intervalStatus(iv,mi,t).status", [iv, mi, t])
                m = {"everyMiles": 7500, "everyMonths": "", "lastDoneMiles": 100000, "lastDoneDate": ""}
                assert [f(m, x, "2026-01-01") for x in [106999, 107000, 107499, 107500, 107501]] == ["ok", "soon", "soon", "due", "overdue"]
                d = {"everyMiles": "", "everyMonths": 12, "lastDoneMiles": "", "lastDoneDate": "2026-01-31"}
                assert [f(d, None, t) for t in ["2026-12-31", "2027-01-01", "2027-01-31", "2027-02-01"]] == ["ok", "soon", "due", "overdue"]
                both = {"everyMiles": 7500, "everyMonths": 12, "lastDoneMiles": 100000, "lastDoneDate": "2026-01-31"}
                assert f(both, 101000, "2027-02-01") == "overdue" and f(both, 107600, "2026-06-01") == "overdue" and f(both, 101000, "2026-06-01") == "ok"
                assert f({"everyMiles": "", "everyMonths": ""}, 1, "2026-01-01") == "unknown"
            _()
            @test("seeded 22RE intervals come from checklist values only")
            def _():
                ivs = pg.evaluate("G.intervals.filter(x=>x.vehicleId==='v1').map(x=>[x.name,x.everyMiles,x.everyMonths,x.lastDoneDate])")
                d = {n: (m, mo, ld) for n, m, mo, ld in ivs}
                assert d["Engine oil and filter"][:2] == (7500, 12) and d["Spark plugs"][:2] == (30000, 36) and d["Timing chain / guide inspection"][:2] == ("", "")
                assert all(x[2] == "" for x in d.values())
            _()
            @test("Upcoming/Due panel + check-off updates last done")
            def _():
                a.nav("My Garage"); pg.fill("#mi-v1", "120000"); pg.click("[onclick=\"updMileage('v1')\"]"); pg.wait_for_timeout(150)
                pg.evaluate("set(()=>{const iv=G.intervals.find(x=>x.name==='Engine oil and filter');iv.lastDoneMiles=112000;iv.lastDoneDate='2026-01-01'})")
                assert pg.is_visible("#upcoming"), "no #upcoming"; assert pg.locator("#upcoming .due-row[data-status='overdue']").count() >= 1, "no overdue row"
                pg.click("#menuBtn"); pg.wait_for_timeout(250); nb = pg.locator("#drawer [data-badge='due']").count(); pg.keyboard.press("Escape"); pg.wait_for_timeout(250); assert nb == 1, f"due badge {nb}"
                a.nav("Service Due"); a.shot("due-phone.png")
                a.nav("Checklist"); pg.locator("[data-id='s2-1'].check").uncheck(); pg.wait_for_timeout(100); pg.locator("[data-id='s2-1'].check").check(); pg.wait_for_timeout(200)
                assert pg.locator("[data-ivoffer]").count() == 1, "no interval offer"
                assert pg.evaluate("G.intervals.find(x=>x.name==='Engine oil and filter').lastDoneMiles") == 112000, "auto-updated"
                pg.click("[data-ivoffer]"); pg.wait_for_timeout(150)
                iv = pg.evaluate("G.intervals.find(x=>x.name==='Engine oil and filter')")
                assert iv["lastDoneMiles"] == 120000 and iv["lastDoneDate"] == pg.evaluate("today()")
                pg.click("#sheet button:has-text('Close')")
            _()
            @test("inventory +/- , reorder alert, offered decrement")
            def _():
                a.nav("Inventory"); pg.click("#addInv"); pg.select_option("#invveh", ""); pg.fill("#invname", "Oil filter"); pg.click("#invsave")
                assert "vehicle" in pg.inner_text("#inverr")
                pg.select_option("#invveh", "v1"); pg.fill("#invpn", "90915-YZZD1"); pg.fill("#invqty", "3"); pg.fill("#invre", "1"); pg.select_option("#invtask", "s2-1"); pg.click("#invsave"); pg.wait_for_timeout(150)
                iid = pg.evaluate("G.inventory[0].id"); assert pg.locator("#drawer [data-badge='low']").count() == 0
                pg.click(f"[data-dec='{iid}']"); pg.click(f"[data-incr='{iid}']"); pg.click(f"[data-dec='{iid}']"); pg.wait_for_timeout(100)
                assert pg.evaluate("G.inventory[0].qtyOnHand") == 2
                a.nav("Checklist"); pg.locator("[data-id='s2-1'].check").uncheck(); pg.locator("[data-id='s2-1'].check").check(); pg.wait_for_timeout(200)
                assert pg.evaluate("G.inventory[0].qtyOnHand") == 2, "auto-decremented"
                pg.click("[data-invoffer]"); pg.wait_for_timeout(100); assert pg.evaluate("G.inventory[0].qtyOnHand") == 1
                pg.click("#sheet button:has-text('Close')")
                a.nav("My Garage"); assert pg.is_visible("#lowstock")
                pg.click("#menuBtn"); pg.wait_for_timeout(250); nb = pg.locator("#drawer [data-badge='low']").count(); pg.keyboard.press("Escape"); pg.wait_for_timeout(250); assert nb == 1, f"low badge {nb}"
                a.nav("Inventory"); a.shot("inventory-phone.png")
            _()
            @test("cost-per-mile math on known data")
            def _():
                c = pg.evaluate("""costStats({log:[{date:'2026-01-05',cost:100},{date:'2026-03-10',cost:50},{date:'2026-02-01',cost:0,odometer:100400}],mileageLog:[{date:'2026-01-01',miles:100000},{date:'2026-03-31',miles:101000}]})""")
                assert c["total"] == 150 and c["milesSpan"] == 1000 and c["costPerMile"] == 0.15 and c["costPer1000"] == 150 and c["perMonth"] == 50 and c["readings"] == 3, c
                z = pg.evaluate("costStats({log:[{date:'2026-01-05',cost:20}],mileageLog:[]})"); assert z["costPerMile"] is None and z["total"] == 20
                pg.evaluate("set(()=>{const v=G.vehicles[0];v.log.push({id:'t1',date:'2026-09-02',item:'Oil',action:'x',cost:40,odometer:118000},{id:'t2',date:'2026-10-02',item:'Plugs',action:'x',cost:60,odometer:119000})})")
                a.nav("Cost per Mile"); pg.select_option("#costVeh", "v1"); pg.wait_for_timeout(100)
                assert pg.locator(".cost-card svg.chart").count() == 1; a.shot("costs-phone.png")
            _()
            @test("photo attach, persist, lightbox, delete")
            def _():
                b64 = pg.evaluate("(()=>{const c=document.createElement('canvas');c.width=2400;c.height=1800;const x=c.getContext('2d');x.fillStyle='#c33';x.fillRect(0,0,2400,1800);return c.toDataURL('image/png').split(',')[1]})()")
                import base64; png = base64.b64decode(b64)
                a.nav("Checklist"); pg.set_input_files("input[id='ph-item_s2_1__']", files=[{"name": "a.png", "mimeType": "image/png", "buffer": png}])
                pg.wait_for_function("PH.length===1"); pg.wait_for_timeout(200)
                w = pg.evaluate("PH[0].w"); assert w == 1600 and pg.evaluate("PH[0].blob.type") == "image/jpeg", w
                assert pg.locator("[data-photos='item|s2-1||'] img.thumb").count() == 1
                a.open(); a.nav("Checklist"); p2 = a.pg; assert p2.locator("[data-photos='item|s2-1||'] img.thumb").count() == 1, "not persisted"
                a.nav("Maintenance Log"); assert p2.locator("img.thumb").count() >= 1, "not in log"
                p2.locator("img.thumb").first.click(); p2.wait_for_timeout(150); assert p2.is_visible("#lightbox img"); a.shot("photos-phone.png")
                p2.click("#lbClose"); a.nav("Checklist")
            _()
            pg = a.pg
            @test("export (with/without photos) + import round-trip incl. intervals/inventory/photos")
            def _():
                full = pg.evaluate("exportFull('garage',true).then(JSON.stringify)"); d = json.loads(full)
                assert d["intervals"] and d["inventory"] and len(d["photos"]) == 1 and d["photos"][0]["data"].startswith("data:image/jpeg") and d["costSnapshot"]
                lite = json.loads(pg.evaluate("exportFull('garage',false).then(JSON.stringify)")); assert "photos" not in lite
                pg.evaluate("delPhoto(PH[0].id)"); pg.wait_for_function("PH.length===0")
                pg.evaluate("set(()=>{G.inventory=[];G.intervals=[]})")
                pg.evaluate("t=>doImport(t)", full); pg.wait_for_function("PH.length===1", timeout=5000); pg.wait_for_timeout(200)
                assert pg.evaluate("G.inventory.length") == 1 and pg.evaluate("G.intervals.length") >= 7
                old = {k: v for k, v in d.items() if k in ("version", "activeVehicleId", "vehicles", "specs")}; old["version"] = 3
                pg.evaluate("t=>doImport(t)", json.dumps(old)); pg.wait_for_timeout(200); assert pg.evaluate("G.vehicles.length") == 2
                pg.locator("img.thumb").first.click(); pg.click("#lbDel"); pg.wait_for_function("PH.length===0"); a.open(); assert a.pg.evaluate("PH.length") == 0
            _()
            @test("[phone] no console errors during run")
            def _(): assert not a.errors, a.errors
            _()
            a.close()
    n = len(results); ok = sum(1 for r in results if r[1]); print(f"\n{ok}/{n} passed")
    if srv: srv.shutdown()
    sys.exit(0 if ok == n else 1)

if __name__ == "__main__": main()
