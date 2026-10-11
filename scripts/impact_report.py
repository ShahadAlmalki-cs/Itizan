"""
تقرير مؤشرات الأثر المجمّعة من قاعدة البيانات (للقراءة فقط).
لا يطبع أي اسم أو اسم مستخدم: أرقام مجمّعة فقط، لتوثيق «الأثر المتحقق» في ملف المشاركة.
التشغيل:  python scripts/impact_report.py
"""
import os
import sqlite3
import sys
from datetime import date, timedelta

DB = os.environ.get("ITIZAN_DB", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "instance", "itizan.db"))
if not os.path.exists(DB):
    sys.exit(f"لا توجد قاعدة بيانات في: {DB}")

db = sqlite3.connect(DB)
one = lambda q, *a: db.execute(q, a).fetchone()[0]
today = date.today()
since = (today - timedelta(days=6)).isoformat()

users = one("SELECT COUNT(*) FROM users")
active = one("SELECT COUNT(DISTINCT user_id) FROM daily_picks WHERE day >= ?", since)
done = one("SELECT COUNT(*) FROM daily_picks WHERE completed = 1")
started = one("SELECT COUNT(*) FROM daily_picks")
print("مؤشرات اتزان المجمّعة")
print("-" * 32)
print(f"عدد الحسابات: {users}")
print(f"حسابات نشطة خلال آخر 7 أيام: {active}")
print(f"المهام المكتملة: {done} من {started} مهمة اختارها المستخدمون"
      + (f" ({round(done / started * 100)}%)" if started else ""))

# تغيّر متوسط ساعات الاستخدام: أول أسبوع تسجيل مقابل آخر أسبوع، لمن سجّل في الفترتين
rows = db.execute("SELECT user_id, MIN(day), MAX(day) FROM usage_log GROUP BY user_id HAVING COUNT(*) >= 4").fetchall()
changes = []
for uid, first, last in rows:
    f = date.fromisoformat(first)
    l = date.fromisoformat(last)
    if (l - f).days < 7:
        continue
    a = one("SELECT AVG(hours) FROM usage_log WHERE user_id=? AND day BETWEEN ? AND ?", uid, first, (f + timedelta(days=6)).isoformat())
    b = one("SELECT AVG(hours) FROM usage_log WHERE user_id=? AND day BETWEEN ? AND ?", uid, (l - timedelta(days=6)).isoformat(), last)
    if a is not None and b is not None:
        changes.append(b - a)
if changes:
    print(f"مستخدمون سجّلوا ساعاتهم في أسبوعين مختلفين: {len(changes)}")
    print(f"متوسط التغيّر في ساعات الاستخدام اليومية: {sum(changes) / len(changes):+.1f} ساعة")
    print(f"عدد من انخفض استخدامهم: {sum(1 for c in changes if c < 0)}")
else:
    print("لا توجد بيانات كافية لقياس تغيّر ساعات الاستخدام بعد (يلزم تسجيل أسبوعين على الأقل).")

q = dict(db.execute("SELECT quality, COUNT(*) FROM usage_log WHERE quality IS NOT NULL GROUP BY quality").fetchall())
if q:
    tot = sum(q.values())
    names = {"purposeful": "هادف ومفيد", "balanced": "متوازن", "aimless": "تصفّح بلا هدف"}
    print("توزيع جودة الاستخدام المسجّلة:")
    for k, v in q.items():
        print(f"  {names.get(k, k)}: {v} ({round(v / tot * 100)}%)")
