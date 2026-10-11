"""اختبارات أساسية للحسابات وعزل البيانات. التشغيل: python -m unittest discover tests -v"""
import os
import sys
import tempfile
import unittest

_tmp = tempfile.mkdtemp()
os.environ["ITIZAN_DB"] = os.path.join(_tmp, "test.db")
os.environ["ITIZAN_SECRET_KEY"] = "test-secret"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app as itizan  # noqa: E402

H = {"X-Requested-With": "itizan"}


class AuthTests(unittest.TestCase):
    def setUp(self):
        itizan._ATTEMPTS.clear()
        self.c = itizan.app.test_client()

    def register(self, client, user="sara_1", name="سارة", pw="correct-horse"):
        return client.post("/api/register", json={"username": user, "display_name": name, "password": pw}, headers=H)

    def test_pages_and_redirects(self):
        self.assertEqual(self.c.get("/").status_code, 200)
        self.assertEqual(self.c.get("/login").status_code, 200)
        self.assertEqual(self.c.get("/register").status_code, 200)
        r = self.c.get("/app")
        self.assertEqual(r.status_code, 302)
        self.assertIn("/login", r.headers["Location"])

    def test_api_requires_login_and_header(self):
        self.assertEqual(self.c.get("/api/today").status_code, 401)
        self.assertEqual(self.c.post("/api/login", json={}).status_code, 403)  # بلا ترويسة الحماية

    def test_register_validation_and_duplicate(self):
        bad = self.c.post("/api/register", json={"username": "a", "display_name": "س", "password": "123"}, headers=H)
        self.assertEqual(bad.status_code, 400)
        ok = self.register(self.c, user="dup_user")
        self.assertEqual(ok.status_code, 201)
        again = self.register(itizan.app.test_client(), user="DUP_user")
        self.assertEqual(again.status_code, 409)

    def test_password_is_hashed(self):
        self.register(self.c, user="hash_user", pw="a-long-password")
        import sqlite3
        row = sqlite3.connect(itizan.DB_PATH).execute(
            "SELECT password_hash FROM users WHERE username='hash_user'").fetchone()
        self.assertNotIn("a-long-password", row[0])
        self.assertTrue(row[0].startswith("pbkdf2:sha256"))

    def test_login_logout_flow(self):
        self.register(self.c, user="flow_user", pw="flow-password")
        self.c.post("/api/logout", headers=H)
        self.assertEqual(self.c.get("/api/me").status_code, 401)
        wrong = self.c.post("/api/login", json={"username": "flow_user", "password": "nope-nope"}, headers=H)
        self.assertEqual(wrong.status_code, 401)
        good = self.c.post("/api/login", json={"username": "FLOW_user", "password": "flow-password"}, headers=H)
        self.assertEqual(good.status_code, 200)
        self.assertEqual(self.c.get("/api/me").get_json()["username"], "flow_user")
        self.assertEqual(self.c.get("/app").status_code, 200)

    def test_login_rate_limit(self):
        self.register(self.c, user="rl_user", pw="rl-password1")
        self.c.post("/api/logout", headers=H)
        codes = [self.c.post("/api/login", json={"username": "rl_user", "password": "bad-pass-x"}, headers=H).status_code
                 for _ in range(9)]
        self.assertEqual(codes[:8], [401] * 8)
        self.assertEqual(codes[8], 429)

    def test_data_is_isolated_per_user(self):
        a, b = itizan.app.test_client(), itizan.app.test_client()
        self.register(a, user="user_a", pw="password-a1")
        self.register(b, user="user_b", pw="password-b1")
        a.post("/api/goals", json={"goal_keys": ["sleep"]}, headers=H)
        a.post("/api/today/complete", headers=H)
        a.post("/api/usage", json={"hours": 3.5}, headers=H)
        pa, pb = a.get("/api/progress").get_json(), b.get("/api/progress").get_json()
        self.assertEqual(pa["total_completed"], 1)
        self.assertEqual(pb["total_completed"], 0)
        self.assertEqual(a.get("/api/goals").get_json()["selected"], ["sleep"])
        self.assertEqual(b.get("/api/goals").get_json()["selected"], ["screen_time"])
        self.assertEqual(pa["usage"]["today"], 3.5)
        self.assertIsNone(pb["usage"]["today"])

    def test_challenge_flow_and_usage_validation(self):
        self.register(self.c, user="ch_user", pw="challenge-pass")
        chs = self.c.get("/api/challenges").get_json()["groups"][0]["challenges"]
        other = next(x for x in chs if not x["is_today"])
        self.assertEqual(self.c.post(f"/api/challenges/{other['id']}/select", headers=H).status_code, 200)
        self.assertEqual(self.c.get("/api/today").get_json()["challenge"]["id"], other["id"])
        self.assertEqual(self.c.post("/api/today/complete", headers=H).get_json()["points"], 10)
        self.assertEqual(self.c.post(f"/api/challenges/{chs[0]['id']}/select", headers=H).status_code, 409)
        self.assertEqual(self.c.post("/api/usage", json={"hours": 30}, headers=H).status_code, 400)
        self.assertEqual(self.c.post("/api/usage", json={"hours": "abc"}, headers=H).status_code, 400)
        self.assertEqual(self.c.post("/api/usage", json={"hours": 2, "quality": "x"}, headers=H).status_code, 400)
        self.assertEqual(self.c.post("/api/usage", json={"hours": 2, "quality": "aimless"}, headers=H).status_code, 200)
        u = self.c.get("/api/progress").get_json()["usage"]
        self.assertEqual((u["today"], u["today_quality"], u["aimless_days"], u["rated_days"]), (2.0, "aimless", 1, 1))
        self.assertEqual(self.c.post("/api/goals", json={"goal_keys": ["zzz"]}, headers=H).status_code, 400)

    def test_delete_account_removes_everything(self):
        self.register(self.c, user="gone_user", pw="delete-me-now")
        self.c.post("/api/today/complete", headers=H)
        self.c.post("/api/usage", json={"hours": 2, "quality": "aimless"}, headers=H)
        import sqlite3 as _s
        uid = _s.connect(itizan.DB_PATH).execute("SELECT id FROM users WHERE username='gone_user'").fetchone()[0]
        self.assertEqual(self.c.post("/api/account/delete", json={"password": "wrong-wrong"}, headers=H).status_code, 401)
        self.assertEqual(self.c.post("/api/account/delete", json={"password": "delete-me-now"}, headers=H).status_code, 200)
        import sqlite3
        db = sqlite3.connect(itizan.DB_PATH)
        self.assertEqual(db.execute("SELECT COUNT(*) FROM users WHERE username='gone_user'").fetchone()[0], 0)
        for table in ("daily_log", "usage_log", "user_goal"):
            self.assertEqual(db.execute(f"SELECT COUNT(*) FROM {table} WHERE user_id = ?", (uid,)).fetchone()[0], 0)
        self.assertEqual(self.c.get("/api/me").status_code, 401)


class TreeTests(unittest.TestCase):
    def setUp(self):
        itizan._ATTEMPTS.clear()
        self.c = itizan.app.test_client()

    def signup(self, client, user, pw="tree-password1"):
        r = client.post("/api/register", json={"username": user, "display_name": "مستخدم", "password": pw}, headers=H)
        self.assertEqual(r.status_code, 201)

    def uid(self, user):
        import sqlite3
        return sqlite3.connect(itizan.DB_PATH).execute("SELECT id FROM users WHERE username=?", (user,)).fetchone()[0]

    def add_done_days(self, user, days_ago):
        import sqlite3
        from datetime import date, timedelta
        db = sqlite3.connect(itizan.DB_PATH)
        for n in days_ago:
            db.execute(
                "INSERT OR REPLACE INTO daily_log(user_id, day, goal_key, challenge_id, completed, completed_at, points) "
                "VALUES (?, ?, 'screen_time', 1, 1, CURRENT_TIMESTAMP, 10)",
                (self.uid(user), (date.today() - timedelta(days=n)).isoformat()),
            )
        db.commit()
        db.close()

    def test_requires_login(self):
        self.assertEqual(self.c.get("/api/tree").status_code, 401)

    def test_new_user_starts_as_seed(self):
        self.signup(self.c, "tree_new")
        t = self.c.get("/api/tree").get_json()
        self.assertEqual((t["stage"], t["stage_name"], t["status"], t["completed_days"]), (0, "بذرة", "new", 0))
        self.assertEqual(t["remaining_days"], 1)
        self.assertEqual(len(t["stages"]), 6)

    def test_tree_grows_with_completions(self):
        self.signup(self.c, "tree_grow")
        r = self.c.post("/api/today/complete", headers=H).get_json()
        self.assertTrue(r["tree_grew"])
        self.assertEqual(r["tree"]["stage_name"], "نبتة")
        again = self.c.post("/api/today/complete", headers=H).get_json()  # تكرار الضغط لا يضيف نمواً
        self.assertFalse(again["tree_grew"])
        self.add_done_days("tree_grow", [2, 3])
        self.assertEqual(self.c.get("/api/tree").get_json()["stage_name"], "شتلة")

    def test_undo_never_lowers_highest_stage(self):
        self.signup(self.c, "tree_keep")
        self.add_done_days("tree_keep", [2, 3])
        self.c.post("/api/today/complete", headers=H)
        self.assertEqual(self.c.get("/api/tree").get_json()["stage"], 2)
        undo = self.c.post("/api/today/undo", headers=H).get_json()
        self.assertEqual(undo["tree"]["stage"], 2)
        self.assertEqual(undo["tree"]["completed_days"], 2)
        self.assertTrue(undo["tree"]["kept_stage"])
        # ويبقى محفوظاً في القاعدة بعد إعادة الطلب
        self.assertEqual(self.c.get("/api/tree").get_json()["stage"], 2)

    def test_long_absence_rests_but_never_dies_or_shrinks(self):
        self.signup(self.c, "tree_rest")
        self.add_done_days("tree_rest", range(10, 17))  # 7 أيام إنجاز قبل 10 أيام فأكثر
        t = self.c.get("/api/tree").get_json()
        self.assertEqual(t["stage_name"], "شجيرة")
        self.assertEqual(t["status"], "resting")
        self.assertEqual(t["days_since_last"], 10)
        self.assertIn("لن تفقد", t["status_text"])

    def test_recent_completion_is_thriving_and_final_stage(self):
        self.signup(self.c, "tree_top")
        self.add_done_days("tree_top", range(0, 30))
        t = self.c.get("/api/tree").get_json()
        self.assertEqual((t["stage"], t["status"]), (5, "thriving"))
        self.assertIsNone(t["remaining_days"])
        self.assertEqual(t["progress_percent"], 100)

    def test_trees_are_isolated_and_deleted_with_account(self):
        a, b = itizan.app.test_client(), itizan.app.test_client()
        self.signup(a, "tree_a")
        self.signup(b, "tree_b")
        a.post("/api/today/complete", headers=H)
        self.assertEqual(a.get("/api/tree").get_json()["stage"], 1)
        self.assertEqual(b.get("/api/tree").get_json()["stage"], 0)
        uid = self.uid("tree_a")
        a.post("/api/account/delete", json={"password": "tree-password1"}, headers=H)
        import sqlite3
        self.assertEqual(sqlite3.connect(itizan.DB_PATH).execute(
            "SELECT COUNT(*) FROM tree_state WHERE user_id=?", (uid,)).fetchone()[0], 0)



class MultiGoalTests(unittest.TestCase):
    def setUp(self):
        itizan._ATTEMPTS.clear()
        self.c = itizan.app.test_client()
        self.n = getattr(MultiGoalTests, "_n", 0) + 1
        MultiGoalTests._n = self.n
        self.user = f"multi_{self.n}"
        r = self.c.post("/api/register", json={"username": self.user, "display_name": "مستخدم", "password": "multi-password1"}, headers=H)
        self.assertEqual(r.status_code, 201)

    def set_goals(self, keys):
        return self.c.post("/api/goals", json={"goal_keys": keys}, headers=H)

    def test_default_single_goal(self):
        g = self.c.get("/api/goals").get_json()
        self.assertEqual((g["selected"], g["current"], g["max"]), (["screen_time"], "screen_time", 3))

    def test_goal_limits_and_validation(self):
        self.assertEqual(self.set_goals([]).status_code, 400)
        self.assertEqual(self.set_goals(["sleep", "study", "hobbies", "family"]).status_code, 400)
        self.assertEqual(self.set_goals(["nope"]).status_code, 400)
        self.assertEqual(self.c.post("/api/goals", json={"goal_keys": "sleep"}, headers=H).status_code, 400)
        self.assertEqual(self.set_goals(["sleep", "sleep", "study"]).get_json()["selected"], ["sleep", "study"])
        self.assertEqual(self.c.get("/api/goals").get_json()["selected"], ["sleep", "study"])

    def test_one_challenge_per_goal_each_day(self):
        self.set_goals(["sleep", "study", "family"])
        t = self.c.get("/api/today").get_json()
        self.assertEqual(t["total"], 3)
        self.assertEqual([i["goal"]["key"] for i in t["items"]], ["sleep", "study", "family"])
        self.assertEqual(len({i["challenge"]["id"] for i in t["items"]}), 3)

    def test_complete_needs_goal_when_several_and_counts_the_day_once(self):
        self.set_goals(["sleep", "study"])
        self.assertEqual(self.c.post("/api/today/complete", headers=H).status_code, 400)
        self.assertEqual(self.c.post("/api/today/complete", json={"goal_key": "family"}, headers=H).status_code, 400)
        a = self.c.post("/api/today/complete", json={"goal_key": "sleep"}, headers=H).get_json()
        self.assertTrue(a["tree_grew"])
        b = self.c.post("/api/today/complete", json={"goal_key": "study"}, headers=H).get_json()
        self.assertFalse(b["tree_grew"])               # اليوم نفسه لا يضيف نمواً إضافياً
        self.assertEqual(b["tree"]["completed_days"], 1)
        t = self.c.get("/api/today").get_json()
        self.assertEqual((t["completed_count"], t["completed"]), (2, True))
        p = self.c.get("/api/progress").get_json()
        self.assertEqual((p["total_completed"], p["points"], p["week_done"]), (2, 20, 1))
        self.assertEqual(len(p["history"]), 2)

    def test_undo_one_goal_keeps_the_day_until_all_are_undone(self):
        self.set_goals(["sleep", "study"])
        for k in ("sleep", "study"):
            self.c.post("/api/today/complete", json={"goal_key": k}, headers=H)
        self.c.post("/api/today/undo", json={"goal_key": "sleep"}, headers=H)
        self.assertEqual(self.c.get("/api/progress").get_json()["week_done"], 1)
        self.assertEqual(self.c.get("/api/today").get_json()["completed_count"], 1)
        r = self.c.post("/api/today/undo", headers=H).get_json()      # كل الأهداف
        self.assertEqual(self.c.get("/api/progress").get_json()["week_done"], 0)
        self.assertEqual(r["tree"]["stage"], 1)                          # أعلى مرحلة محفوظة

    def test_select_challenge_is_per_goal(self):
        self.set_goals(["sleep", "study"])
        groups = self.c.get("/api/challenges").get_json()["groups"]
        self.assertEqual([g["goal"]["key"] for g in groups], ["sleep", "study"])
        other = next(x for x in groups[0]["challenges"] if not x["is_today"])
        study_today = next(x for x in groups[1]["challenges"] if x["is_today"])
        self.assertEqual(self.c.post(f"/api/challenges/{other['id']}/select", headers=H).status_code, 200)
        items = {i["goal"]["key"]: i["challenge"]["id"] for i in self.c.get("/api/today").get_json()["items"]}
        self.assertEqual(items["sleep"], other["id"])
        self.assertEqual(items["study"], study_today["id"])             # الهدف الآخر لم يتأثر
        foreign = itizan_first_challenge("family")
        self.assertEqual(self.c.post(f"/api/challenges/{foreign}/select", headers=H).status_code, 400)
        self.c.post("/api/today/complete", json={"goal_key": "sleep"}, headers=H)
        self.assertEqual(self.c.post(f"/api/challenges/{other['id']}/select", headers=H).status_code, 409)

    def test_removing_a_goal_drops_only_its_unfinished_challenge(self):
        self.set_goals(["sleep", "study"])
        self.c.post("/api/today/complete", json={"goal_key": "sleep"}, headers=H)
        self.c.post(f"/api/challenges/{itizan_first_challenge('study')}/select", headers=H)
        self.set_goals(["study"])
        t = self.c.get("/api/today").get_json()
        self.assertEqual(t["total"], 1)
        self.assertEqual(self.c.get("/api/progress").get_json()["total_completed"], 1)   # إنجاز النوم محفوظ

    def test_impact_report_counts_unfinished_tasks_too(self):
        import subprocess
        import sys
        self.set_goals(["sleep", "study"])
        self.c.post(f"/api/challenges/{itizan_first_challenge('study')}/select", headers=H)
        self.c.post("/api/today/complete", json={"goal_key": "sleep"}, headers=H)
        script = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts", "impact_report.py")
        out = subprocess.run([sys.executable, script], capture_output=True, text=True, encoding="utf-8",
                             env={**os.environ, "ITIZAN_DB": itizan.DB_PATH}).stdout
        self.assertIn("المهام المكتملة", out)
        self.assertNotIn("(100%)", out.split("المهام المكتملة")[1].splitlines()[0])


def itizan_first_challenge(goal_key):
    import sqlite3
    return sqlite3.connect(itizan.DB_PATH).execute("SELECT MIN(id) FROM challenges WHERE goal_key=?", (goal_key,)).fetchone()[0]


class MigrationTests(unittest.TestCase):
    def test_old_single_goal_data_is_migrated_without_loss(self):
        import sqlite3
        import tempfile
        from datetime import date, timedelta
        old_path = itizan.DB_PATH
        legacy = os.path.join(tempfile.mkdtemp(), "legacy.db")
        db = sqlite3.connect(legacy)
        db.executescript("""
            CREATE TABLE users (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT NOT NULL UNIQUE, display_name TEXT NOT NULL,
                                password_hash TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
            CREATE TABLE goals (key TEXT PRIMARY KEY, title TEXT NOT NULL, icon TEXT NOT NULL);
            CREATE TABLE challenges (id INTEGER PRIMARY KEY AUTOINCREMENT, slug TEXT NOT NULL UNIQUE, goal_key TEXT NOT NULL,
                                     title TEXT NOT NULL, description TEXT NOT NULL, minutes INTEGER NOT NULL DEFAULT 0, icon TEXT NOT NULL);
            CREATE TABLE user_goal (user_id INTEGER PRIMARY KEY, goal_key TEXT NOT NULL, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
            CREATE TABLE daily_log (user_id INTEGER NOT NULL, day TEXT NOT NULL, goal_key TEXT NOT NULL, challenge_id INTEGER NOT NULL,
                                    completed INTEGER NOT NULL DEFAULT 0, completed_at TEXT, points INTEGER NOT NULL DEFAULT 0,
                                    PRIMARY KEY (user_id, day));
        """)
        db.execute("INSERT INTO users(username, display_name, password_hash) VALUES ('old_user', 'قديم', 'x')")
        db.execute("INSERT INTO user_goal(user_id, goal_key) VALUES (1, 'sleep')")
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        db.execute("INSERT INTO daily_log VALUES (1, ?, 'sleep', 1, 1, CURRENT_TIMESTAMP, 10)", (yesterday,))
        db.execute("INSERT INTO daily_log VALUES (1, ?, 'sleep', 1, 0, NULL, 0)", (date.today().isoformat(),))
        db.commit(); db.close()
        try:
            itizan.DB_PATH = legacy
            itizan.init_db()
            itizan.init_db()  # التشغيل المتكرر لا يكرر شيئاً ولا يعيد أهدافاً محذوفة
            db = sqlite3.connect(legacy)
            self.assertEqual(db.execute("SELECT goal_key FROM user_goals WHERE user_id=1").fetchall(), [("sleep",)])
            self.assertEqual(db.execute("SELECT day, completed FROM daily_picks WHERE user_id=1").fetchall(), [(yesterday, 1)])
            self.assertEqual(db.execute("SELECT COUNT(*) FROM daily_log WHERE completed=0").fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM daily_log WHERE completed=1").fetchone()[0], 1)
            db.execute("DELETE FROM user_goals WHERE user_id=1"); db.execute("INSERT INTO user_goals VALUES (1, 'study')"); db.commit(); db.close()
            itizan.init_db()
            db = sqlite3.connect(legacy)
            self.assertEqual(db.execute("SELECT goal_key FROM user_goals WHERE user_id=1").fetchall(), [("study",)])
            db.close()
        finally:
            itizan.DB_PATH = old_path


if __name__ == "__main__":
    unittest.main()
