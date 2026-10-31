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
                _()
                a.close(); continue
            pg = a.pg
            @test("menu drawer opens, lists sections, closes")
            def _():
                pg.click("#menuBtn"); pg.wait_for_timeout(300)
                assert pg.get_attribute("#menuBtn", "aria-expanded") == "true"
                items = pg.locator("#nav button").all_inner_texts()
                for s in ["My Garage", "Checklist", "All Tasks", "Maintenance Log", "Diagnostics", "Parts", "Specs", "Import / Export"]:
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
            @test("spec offer from note saves structured spec")
            def _():
                pg.click("[data-notes='s2-1']"); pg.fill("#nd-s2-1", "Drain plug torque 27 foot-pounds"); pg.click("[data-post='s2-1']")
                pg.wait_for_selector("#specOffer")
                assert pg.input_value("#of-value") == "27" and pg.input_value("#of-unit") == "ft-lb" and pg.input_value("#of-topic") == "Torque"
                a.shot("notes-phone.png")
                assert pg.evaluate("G.specs.length") == 0, "auto-saved"
                pg.click("#of-save"); pg.wait_for_timeout(150)
                sp = pg.evaluate("G.specs[0]")
                assert sp["value"] == "27" and sp["unit"] == "ft-lb" and sp["topic"] == "Torque" and sp["vehicleId"] == "v1" and sp["taskIds"] == ["s2-1"], sp
            _()
            @test("spec search finds it")
            def _():
                a.nav("Specs"); pg.fill("#specQ", "drain plug torque"); pg.wait_for_timeout(400)
                assert pg.locator(".spec-row").count() == 1 and "27 ft-lb" in pg.inner_text(".spec-row")
                a.shot("specs-phone.png")
                pg.fill("#specQ", "transmission bolt"); pg.wait_for_timeout(400); assert pg.locator(".spec-row").count() == 0
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
                pg.evaluate("set(()=>{G.specs=[];G.vehicles[0].sections.forEach(s=>s.items.forEach(i=>i.noteLog=[]))})")
                pg.evaluate("t=>doImport(t)", exp); pg.wait_for_timeout(200)
                assert pg.evaluate("G.specs.length") == 1 and pg.evaluate("G.vehicles[0].sections.flatMap(s=>s.items).filter(i=>i.noteLog&&i.noteLog.length).length") == 2
                vexp = pg.evaluate("JSON.stringify(exportVehicle())"); assert json.loads(vexp)["specs"]
            _()
            @test("migration: old single-truck data keeps legacy notes")
            def _():
                old = {"sections":[{"title":"Old","items":[{"id":"s1-1","label":"Legacy","checked":True,"notes":"legacy note text","part":"","cost":"5"}]}],"log":[{"date":"2026-10-01","itemId":"s1-1","item":"Legacy","action":"Completed","part":"","cost":5}],"cases":[],"tests":[]}
                pg.evaluate("""o=>new Promise(r=>{const q=indexedDB.open('tracker22re',1);q.onsuccess=()=>{const t=q.result.transaction('kv','readwrite');t.objectStore('kv').put(o,'state');t.oncomplete=r}})""", old)
                a.open(); p2 = a.pg
                assert p2.evaluate("G.vehicles.length") == 2 and p2.evaluate("G.vehicles[0].sections[0].items[0].notes") == "legacy note text"
                assert p2.evaluate("Array.isArray(G.specs)")
                p2.evaluate("""t=>doImport(t)""", json.dumps({"sections": old["sections"], "log": old["log"], "cases": [], "tests": []}))
                assert p2.evaluate("V().sections[0].items[0].notes") == "legacy note text"
            _()
            @test("manifest valid + service worker controls page")
            def _():
                m = a.pg.evaluate("fetch('manifest.json').then(r=>r.json())")
                assert m["display"] == "standalone" and m["start_url"] and m["name"]
                assert {"192x192", "512x512"} <= {i["sizes"] for i in m["icons"]}
                assert a.pg.evaluate("fetch('apple-touch-icon.png').then(r=>r.ok)")
                a.pg.wait_for_function("navigator.serviceWorker.ready.then(()=>true)"); a.open()
                assert a.pg.evaluate("!!navigator.serviceWorker.controller")
            _()
            @test("[phone] no console errors during run")
            def _(): assert not a.errors, a.errors
            _()
            a.close()
    n = len(results); ok = sum(1 for r in results if r[1]); print(f"\n{ok}/{n} passed")
    if srv: srv.shutdown()
    sys.exit(0 if ok == n else 1)

if __name__ == "__main__": main()
