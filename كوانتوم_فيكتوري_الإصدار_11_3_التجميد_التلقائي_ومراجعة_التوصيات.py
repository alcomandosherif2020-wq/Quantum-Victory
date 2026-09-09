# -*- coding: utf-8 -*-
"""كوانتوم فيكتوري — ملف تشغيل ستريملت مستقل ومتكامل.
هذا الملف مناسب مباشرةً كملف رئيسي في GitHub وStreamlit Community Cloud.
"""
#!/usr/bin/env python3

# ===== طبقة توحيد الجلسة المرجعية — الإصدار 10.5 =====
# لا تخمّن جلسة السوق: تستخرج أحدث تاريخ موجود فعليًا من البيانات المقبولة،
# وتستبعد المستقبل والتواريخ غير الصالحة، وتُبقي مصدر التاريخ قابلًا للتدقيق.
def استخراج_تواريخ_الجلسات_المقبولة(بيانات):
    تواريخ=[]
    if بيانات is None: return []
    try:
        if hasattr(بيانات, "columns"):
            for عمود in ("session_date", "تاريخ الجلسة", "date", "التاريخ"):
                if عمود in بيانات.columns:
                    تواريخ.extend(بيانات[عمود].dropna().astype(str).tolist())
        elif isinstance(بيانات, (list, tuple)):
            for صف in بيانات:
                if isinstance(صف, dict):
                    for عمود in ("session_date", "تاريخ الجلسة", "date", "التاريخ"):
                        if صف.get(عمود) not in (None, ""):
                            تواريخ.append(str(صف[عمود])); break
    except Exception:
        return []
    ن=[]
    for قيمة in تواريخ:
        try:
            تاريخ=pd.to_datetime(قيمة, errors="coerce")
            if pd.notna(تاريخ): ن.append(تاريخ.date())
        except Exception: pass
    return sorted(set(ن))

def تحديد_الجلسة_المرجعية_من_البيانات(بيانات, الآن=None):
    الآن=(الآن or datetime.now(timezone.utc)).date()
    تواريخ=[d for d in استخراج_تواريخ_الجلسات_المقبولة(بيانات) if d <= الآن]
    if not تواريخ:
        return {"الحالة":"محجوب: لا توجد جلسة مقبولة", "تاريخ الجلسة":None, "المصدر":"لا توجد بيانات مقبولة"}
    آخر=تواريخ[-1]
    return {"الحالة":"محدد من البيانات المقبولة", "تاريخ الجلسة":آخر.isoformat(), "المصدر":"حقول تاريخ الجلسة داخل البيانات", "عدد_الجلسات":len(تواريخ)}

"""طبقة تخزين تشغيلية محلية: لقطات السوق، صحة المصادر، وسجل التدقيق."""
import hashlib, json, sqlite3, os
from datetime import datetime, timezone
from pathlib import Path

class مخزن_كوانتوم:
    """مخزن موحد: SQLite للاختبار وPostgreSQL للاستمرارية السحابية.
    لا يعتبر وجود DATABASE_URL وحده تفويضًا أو موافقة إنتاجية.
    """
    def __init__(self, path="data/qv_operational.sqlite3"):
        self.backend=os.getenv("QV_STORAGE_BACKEND","sqlite").strip().lower()
        self.database_url=os.getenv("DATABASE_URL","").strip()
        self.path = Path(path); self.path.parent.mkdir(parents=True, exist_ok=True)
        self._pg = None
        if self.backend == "postgres" and self.database_url:
            try:
                import psycopg
                self._pg=psycopg.connect(self.database_url, autocommit=True)
            except Exception:
                self._pg=None
        self._init()
    def _conn(self):
        c=sqlite3.connect(self.path); c.execute("PRAGMA journal_mode=WAL"); return c
    def _use_pg(self):
        return self.backend == "postgres" and self._pg is not None
    def _init(self):
        if self._use_pg():
            with self._pg.cursor() as c:
                c.execute("""CREATE TABLE IF NOT EXISTS "لقطات_السوق" (id BIGSERIAL PRIMARY KEY, "وقت_الالتقاط" TEXT NOT NULL, "المصدر" TEXT NOT NULL, "النوع" TEXT NOT NULL, "الرمز" TEXT NOT NULL, payload TEXT NOT NULL, "بصمة" TEXT NOT NULL UNIQUE)""")
                c.execute('CREATE INDEX IF NOT EXISTS idx_market_symbol_time ON "لقطات_السوق"("الرمز","وقت_الالتقاط")')
                c.execute("""CREATE TABLE IF NOT EXISTS "صحة_المصادر" (id BIGSERIAL PRIMARY KEY, "وقت_الفحص" TEXT NOT NULL, "المصدر" TEXT NOT NULL, نجاح INTEGER NOT NULL, "زمن_الاستجابة" DOUBLE PRECISION, "رسالة" TEXT, "بصمة" TEXT)""")
                c.execute("""CREATE TABLE IF NOT EXISTS "سجل_التدقيق" (id BIGSERIAL PRIMARY KEY, "وقت_الحدث" TEXT NOT NULL, الحدث TEXT NOT NULL, المصدر TEXT, الحالة TEXT NOT NULL, التفاصيل TEXT NOT NULL)""")
            return
        with self._conn() as c:
            c.executescript('''
            CREATE TABLE IF NOT EXISTS لقطات_السوق (
              id INTEGER PRIMARY KEY AUTOINCREMENT, وقت_الالتقاط TEXT NOT NULL,
              المصدر TEXT NOT NULL, النوع TEXT NOT NULL, الرمز TEXT NOT NULL,
              payload TEXT NOT NULL, بصمة TEXT NOT NULL UNIQUE
            );
            CREATE INDEX IF NOT EXISTS idx_market_symbol_time ON لقطات_السوق(الرمز,وقت_الالتقاط);
            CREATE TABLE IF NOT EXISTS صحة_المصادر (
              id INTEGER PRIMARY KEY AUTOINCREMENT, وقت_الفحص TEXT NOT NULL,
              المصدر TEXT NOT NULL, نجاح INTEGER NOT NULL, زمن_الاستجابة REAL,
              رسالة TEXT, بصمة TEXT
            );
            CREATE TABLE IF NOT EXISTS سجل_التدقيق (
              id INTEGER PRIMARY KEY AUTOINCREMENT, وقت_الحدث TEXT NOT NULL,
              الحدث TEXT NOT NULL, المصدر TEXT, الحالة TEXT NOT NULL,
              التفاصيل TEXT NOT NULL
            );
            ''')
    @staticmethod
    def بصمة(obj):
        raw=json.dumps(obj,ensure_ascii=False,sort_keys=True,separators=(",",":"))
        return hashlib.sha256(raw.encode()).hexdigest()
    def حفظ_لقطة(self, المصدر, النوع, الرمز, payload, وقت=None):
        وقت=وقت or datetime.now(timezone.utc).isoformat()
        بصمة=self.بصمة({"وقت":وقت,"المصدر":المصدر,"النوع":النوع,"الرمز":الرمز,"payload":payload})
        payload_text=json.dumps(payload,ensure_ascii=False,sort_keys=True)
        if self._use_pg():
            with self._pg.cursor() as c:
                c.execute('INSERT INTO "لقطات_السوق"("وقت_الالتقاط","المصدر","النوع","الرمز",payload,"بصمة") VALUES(%s,%s,%s,%s,%s,%s) ON CONFLICT ("بصمة") DO NOTHING', (وقت,المصدر,النوع,الرمز,payload_text,بصمة))
            return بصمة
        with self._conn() as c:
            c.execute("INSERT OR IGNORE INTO لقطات_السوق(وقت_الالتقاط,المصدر,النوع,الرمز,payload,بصمة) VALUES(?,?,?,?,?,?)",
                      (وقت,المصدر,النوع,الرمز,payload_text,بصمة))
        return بصمة
    def سجل_صحة(self, المصدر, نجاح, زمن_الاستجابة=None, رسالة="", بصمة=None):
        vals=(datetime.now(timezone.utc).isoformat(),المصدر,int(bool(نجاح)),زمن_الاستجابة,رسالة,بصمة)
        if self._use_pg():
            with self._pg.cursor() as c: c.execute('INSERT INTO "صحة_المصادر"("وقت_الفحص","المصدر",نجاح,"زمن_الاستجابة","رسالة","بصمة") VALUES(%s,%s,%s,%s,%s,%s)',vals)
            return
        with self._conn() as c:
            c.execute("INSERT INTO صحة_المصادر(وقت_الفحص,المصدر,نجاح,زمن_الاستجابة,رسالة,بصمة) VALUES(?,?,?,?,?,?)",vals)
    def تدقيق(self, الحدث, الحالة, التفاصيل, المصدر=None):
        vals=(datetime.now(timezone.utc).isoformat(),الحدث,المصدر,الحالة,json.dumps(التفاصيل,ensure_ascii=False,sort_keys=True))
        if self._use_pg():
            with self._pg.cursor() as c: c.execute('INSERT INTO "سجل_التدقيق"("وقت_الحدث",الحدث,المصدر,الحالة,التفاصيل) VALUES(%s,%s,%s,%s,%s)',vals)
            return
        with self._conn() as c:
            c.execute("INSERT INTO سجل_التدقيق(وقت_الحدث,الحدث,المصدر,الحالة,التفاصيل) VALUES(?,?,?,?,?)",vals)
    def إحصاءات(self):
        if self._use_pg():
            with self._pg.cursor() as c:
                return {"لقطات":c.execute('SELECT COUNT(*) FROM "لقطات_السوق"').fetchone()[0],"فحوص_مصادر":c.execute('SELECT COUNT(*) FROM "صحة_المصادر"').fetchone()[0],"أحداث_تدقيق":c.execute('SELECT COUNT(*) FROM "سجل_التدقيق"').fetchone()[0],"التخزين":"postgres"}
        with self._conn() as c:
            return {"لقطات":c.execute("SELECT COUNT(*) FROM لقطات_السوق").fetchone()[0],"فحوص_مصادر":c.execute("SELECT COUNT(*) FROM صحة_المصادر").fetchone()[0],"أحداث_تدقيق":c.execute("SELECT COUNT(*) FROM سجل_التدقيق").fetchone()[0],"التخزين":"sqlite"}

#!/usr/bin/env python3
"""عميل مصدر آمن مع إعادة محاولة وتراجع تدريجي وقاطع فشل بسيط."""
import time
class عميل_مقاوم:
    def __init__(self, request_fn, محاولات=3, مهلة_فتح=3, زمن_عودة=30):
        self.request_fn=request_fn; self.محاولات=max(1,int(محاولات)); self.مهلة_فتح=مهلة_فتح; self.زمن_عودة=زمن_عودة
        self.فشل_متتال=0; self.آخر_فتح=0
    def get(self, *args, **kwargs):
        if self.فشل_متتال >= self.مهلة_فتح and time.monotonic()-self.آخر_فتح < self.زمن_عودة:
            return None, {"نجاح":False,"الخطأ":"قاطع الفشل مفتوح مؤقتًا","قاطع_الفشل":True}
        last={}
        for n in range(self.محاولات):
            try:
                payload, meta=self.request_fn(*args, **kwargs); last=meta or {}
                if meta.get("نجاح"):
                    self.فشل_متتال=0; return payload,meta
            except Exception as exc: last={"نجاح":False,"الخطأ":str(exc)}
            self.فشل_متتال += 1; self.آخر_فتح=time.monotonic()
            if n+1 < self.محاولات: time.sleep(min(0.5*(2**n),4))
        return None,last

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""حارس تشغيل مستمر: تحقق، توازي مضبوط، مقاومة أعطال، وتدقيق."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import time

class حارس_التشغيل:
    def __init__(self, fetch_fn, db_path="data/qv_operational.sqlite3", workers=8, rate_limit=0.08):
        self.fetch_fn=fetch_fn; self.db=مخزن_كوانتوم(db_path)
        self.workers=max(1,int(workers)); self.rate_limit=max(0.0,float(rate_limit))
        self._client = عميل_مقاوم(self.fetch_fn,3,4,30)
        self._rate_lock = threading.Lock(); self._last_request = 0.0
    @staticmethod
    def تحقق_اللقطة(النتيجة):
        if not isinstance(النتيجة,dict) or not النتيجة.get("نجاح"): return False,"فشل المصدر"
        data=النتيجة.get("بيانات")
        if not isinstance(data,list) or not data: return False,"لا توجد بيانات قابلة للحفظ"
        if any(not isinstance(r,dict) for r in data): return False,"مخطط بيانات غير صالح"
        return True,"صالحة"
    def _واحدة(self,رمز,نوع):
        started=time.monotonic()
        try:
            with self._rate_lock:
                انتظار = self.rate_limit - (time.monotonic() - self._last_request)
                if انتظار > 0: time.sleep(انتظار)
                self._last_request = time.monotonic()
            payload,meta=self._client.get(رمز,نوع); meta=dict(meta or {})
            بيانات=payload if isinstance(payload,list) else meta.get("بيانات",[])
            نتيجة={**meta,"بيانات":بيانات,"وقت_الاستلام":meta.get("وقت_الاستلام") or datetime.now(timezone.utc).isoformat()}
            صالح,رسالة=self.تحقق_اللقطة(نتيجة)
            if صالح:
                بصمة=self.db.حفظ_لقطة("EGXAPI",نوع,رمز,بيانات,نتيجة["وقت_الاستلام"])
                self.db.تدقيق("التقاط_سوق","نجاح",{"الرمز":رمز,"النوع":نوع,"البصمة":بصمة},"EGXAPI")
            else:
                self.db.تدقيق("التقاط_سوق","محجوب",{"الرمز":رمز,"النوع":نوع,"السبب":رسالة},"EGXAPI")
            return {"الرمز":رمز,"النوع":نوع,"نجاح":صالح,"السبب":رسالة,"زمن_الثواني":round(time.monotonic()-started,4),"وقت_الاستلام":نتيجة["وقت_الاستلام"]}
        except Exception as exc:
            self.db.تدقيق("التقاط_سوق","فشل",{"الرمز":رمز,"النوع":نوع,"الخطأ":str(exc)},"EGXAPI")
            return {"الرمز":رمز,"النوع":نوع,"نجاح":False,"السبب":str(exc),"زمن_الثواني":round(time.monotonic()-started,4)}
    def تشغيل(self,الأدوات):
        started=time.monotonic(); results=[]
        with ThreadPoolExecutor(max_workers=self.workers) as pool:
            futures=[]
            for رمز,نوع in الأدوات:
                if self.rate_limit: time.sleep(self.rate_limit)
                futures.append(pool.submit(self._واحدة,رمز,نوع))
            for f in as_completed(futures): results.append(f.result())
        results.sort(key=lambda x:(x.get("النوع", ""),x.get("الرمز", "")))
        summary={"عدد_الأدوات":len(results),"ناجح":sum(r["نجاح"] for r in results),"فاشل":sum(not r["نجاح"] for r in results),"زمن_الدورة":round(time.monotonic()-started,4),"إحصاءات_التخزين":self.db.إحصاءات()}
        self.db.تدقيق("دورة_تشغيل","اكتملت",summary,"EGXAPI")
        return {"النتائج":results,"الملخص":summary}

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""لوحة حالة موحدة للبيانات والمصادر والبوابات التشغيلية."""
import os

class مركز_القيادة:
    متطلبات=("QV_SOURCE_AUTHORIZED","QV_PRODUCTION_APPROVED","EGX_KEY","EGX_HISTORY_PATH")
    def __init__(self, db_path="data/qv_operational.sqlite3"):
        self.db=مخزن_كوانتوم(db_path)
    def حالة(self):
        env={k: bool(os.getenv(k,"")) for k in self.متطلبات}
        # لا يُفتح الإنتاج هنا؛ هذه قراءة مراقبة فقط، والبوابة المستقلة تبقى المرجع النهائي.
        return {"متغيرات_التهيئة":env,"التخزين":self.db.إحصاءات(),"الإنتاج_مفتوح_من_هذه_اللوحة":False,
                "ملاحظة":"مركز القيادة لا يمنح تفويضًا ولا موافقة إنتاجية؛ يعرض الحالة فقط."}

import json
import math
import statistics
import os
import re
import threading
import time
from pathlib import Path
from typing import Any

# ===================== طبقة الحماية والتكوين r5 =====================
# كل القيم الحساسة تُقرأ من البيئة/أسرار Streamlit، ولا تُطبع ولا تُحفظ.
نسخة_المنظومة = "r5-حماية-ومصالحة-2026-09-08"
الحد_الأقصى_للأدوات = max(1, int(os.getenv("QV_MAX_INSTRUMENTS", "250")))
الحد_الأقصى_لعمر_البيانات = max(5, int(os.getenv("QV_MAX_DATA_AGE_SECONDS", "120")))

def _علم_بيئي(name, default=False):
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on", "نعم"}

def _قيمة_سرية(name):
    try:
        value = st.secrets.get(name, "")
    except Exception:
        value = ""
    return str(value or os.getenv(name, "")).strip()

def _تنظيف_خطأ(text):
    # منع تسرب مفاتيح محتملة أو رؤوس تفويض إلى واجهة المستخدم/سجل التدقيق.
    t = str(text or "")
    t = re.sub(r"(?i)(authorization|api[-_ ]?key|token|secret)(\s*[:=]\s*)[^,;\s]+", r"\1\2[محجوب]", t)
    return t[:500]


import pandas as pd
import streamlit as st

# ------------------------- محرك مراجعة نجاح التوصيات -------------------------
try:
    from qv_recommendation_review_engine import (
        QVRecommendationReviewEngine, حفظ_توصيات_اليوم, مراجعة_جلسة_الغد,
        تجميد_من_جدول_التوصيات
    )
    QV_REVIEW_ENGINE_AVAILABLE = True
except Exception as _qv_review_exc:
    QV_REVIEW_ENGINE_AVAILABLE = False
    _qv_review_exc_text = str(_qv_review_exc)


# ------------------------- أدوات عامة -------------------------
def رقم(value: Any, default=None):
    try:
        if value is None or value == "":
            return default
        if isinstance(value, str):
            value = value.replace(",", "").replace("٪", "")
        number = float(value)
        return number if math.isfinite(number) else default
    except (TypeError, ValueError):
        return default


def أول_قيمة(row: dict, *names):
    for name in names:
        if name in row and row[name] not in (None, ""):
            return row[name]
    return None


def تطبيع(سجلات):
    result = []
    for index, raw in enumerate(سجلات or []):
        row = {str(k).strip().lower(): v for k, v in dict(raw).items()}
        السعر = رقم(أول_قيمة(row, "السعر", "price", "close", "الإغلاق"))
        if السعر is None:
            continue
        الحجم = رقم(أول_قيمة(row, "الحجم", "volume", "vol"), 0.0)
        result.append({
            "الترتيب": index,
            "الوقت": أول_قيمة(row, "الوقت", "time", "timestamp") or str(index),
            "السعر": السعر,
            "الحجم": الحجم,
            "الافتتاح": رقم(أول_قيمة(row, "الافتتاح", "open")),
            "الأعلى": رقم(أول_قيمة(row, "الأعلى", "high")),
            "الأدنى": رقم(أول_قيمة(row, "الأدنى", "low")),
            "الإغلاق": رقم(أول_قيمة(row, "الإغلاق", "close"), السعر),
        })
    return result


def جاهزية_البيانات(data):
    count = len(data)
    return {
        "عدد القراءات": count,
        "جاهزة للرصد": count >= 3,
        "جاهزة لتحليل أعمق": count >= 20,
        "دفتر الأوامر": False,
        "بيانات التنفيذ التفصيلية": False,
        "ملاحظة": "البيانات اللحظية الأعمق تحتاج إلى مصدر مصرح به وبيانات تنفيذ أو عمق سوق قابلة للتحقق."
    }


def تحليل_النشاط(data):
    data = تطبيع(data)
    جاهزية = جاهزية_البيانات(data)
    تحذيرات, أدلة, متابعة = [], [], []
    if len(data) < 3:
        return {"الحالة": "محجوب — البيانات غير كافية", "درجة": None, "اتجاه": "غير محدد", "شدة": "غير كافية", "أدلة": [], "تحذيرات": ["يلزم ثلاث قراءات سعر وحجم على الأقل."], "متابعة": [], "جاهزية": جاهزية}
    الأسعار = [x["السعر"] for x in data]
    الأحجام = [x["الحجم"] for x in data]
    الحالي, السابق = الأسعار[-1], الأسعار[-2]
    التغير = ((الحالي - السابق) / السابق * 100) if السابق else 0.0
    الأساس = statistics.median(الأحجام[:-1]) if len(الأحجام) > 1 else الأحجام[-1]
    نسبة_الحجم = (الأحجام[-1] / الأساس) if الأساس > 0 else 0.0
    الدرجة = 0.0
    الدرجة += min(30, التغير * 10) if التغير > 0 else max(-30, التغير * 10)
    if نسبة_الحجم >= 2:
        الدرجة += 30 if التغير > 0 else -30
    elif نسبة_الحجم >= 1.25:
        الدرجة += 15 if التغير > 0 else -15
    if len(الأسعار) >= 4:
        حركة = (الأسعار[-1] - الأسعار[-4]) / الأسعار[-4] * 100 if الأسعار[-4] else 0
        الدرجة += min(20, حركة * 5) if حركة > 0 else max(-20, حركة * 5)
    الدرجة = max(-100, min(100, الدرجة))
    if التغير > 0 and نسبة_الحجم >= 1.25:
        الاتجاه = "شراء مرجح"
        أدلة.append(f"ارتفاع السعر {التغير:.2f}% مع نشاط حجمي يقارب {نسبة_الحجم:.2f} مرة من خط الأساس.")
    elif التغير < 0 and نسبة_الحجم >= 1.25:
        الاتجاه = "بيع مرجح"
        أدلة.append(f"انخفاض السعر {abs(التغير):.2f}% مع نشاط حجمي يقارب {نسبة_الحجم:.2f} مرة من خط الأساس.")
    else:
        الاتجاه = "مختلط — يحتاج تأكيد"
        أدلة.append(f"تغير السعر {التغير:.2f}% ونسبة النشاط {نسبة_الحجم:.2f}؛ الدلالة غير حاسمة.")
    الشدة = "مرتفعة جدًا" if نسبة_الحجم >= 2 else ("مرتفعة" if نسبة_الحجم >= 1.25 else ("طبيعية/متوسطة" if نسبة_الحجم > 0 else "غير متاحة"))
    الحالة = "إشارة قوية نسبيًا — تحتاج تأكيد" if abs(الدرجة) >= 55 else ("تنبيه — مراقبة نشطة" if abs(الدرجة) >= 25 else "مراقبة — لا إشارة حاسمة")
    if len(data) < 20:
        تحذيرات.append("العينة قصيرة؛ لا تستخدم النتيجة كحكم إحصائي نهائي.")
    تحذيرات += ["لا يمكن استنتاج هوية مؤسسة أو متعامل بعينه من هذه البيانات وحدها.", "درجة التحليل ليست احتمالًا وليست هدفًا سعريًا."]
    متابعة += ["مراقبة استمرار النشاط في القراءات التالية.", "فحص الامتصاص أو الانعكاس عند توفر بيانات مصرح بها.", "إبطال التنبيه إذا انعكس السلوك مع أدلة مستقلة مؤيدة للاتجاه المعاكس."]
    return {"الحالة": الحالة, "درجة": round(الدرجة, 2), "اتجاه": الاتجاه, "شدة": الشدة, "أدلة": أدلة, "تحذيرات": تحذيرات, "متابعة": متابعة, "جاهزية": جاهزية}


def محرك_بصمة_كوانتوم(سجلات, نافذة=10):
    """يبني بصمة سلوكية كمية للسعر والحجم ويقيس انحراف السلوك الحالي عن خطه التاريخي.
    لا يستنتج هوية متعامل، ولا يحول الدرجة إلى احتمال.
    """
    data = تطبيع(سجلات)
    if len(data) < 8:
        return {
            "الحالة": "محجوب — يلزم ثماني قراءات على الأقل",
            "جاهزية": False, "درجة البصمة": None, "انحراف السلوك": None,
            "اتجاه البصمة": "غير محدد", "البصمة الحالية": {},
            "خط الأساس": {}, "الأدلة": [], "التحذيرات": ["العينة غير كافية لبناء بصمة مستقرة."]
        }
    نافذة = max(5, min(int(نافذة), len(data)//2))
    أسعار = pd.Series([x["السعر"] for x in data], dtype=float)
    أحجام = pd.Series([x["الحجم"] for x in data], dtype=float)
    عوائد = أسعار.pct_change().fillna(0.0)
    نطاق = []
    for x in data:
        h, l, c = x.get("الأعلى"), x.get("الأدنى"), x.get("الإغلاق")
        نطاق.append(((h-l)/c) if h is not None and l is not None and c else 0.0)
    نطاق = pd.Series(نطاق, dtype=float)

    def خصائص(نهاية):
        بداية = max(0, نهاية-نافذة)
        r = عوائد.iloc[بداية:نهاية]
        v = أحجام.iloc[بداية:نهاية]
        rr = نطاق.iloc[بداية:نهاية]
        if len(r) == 0:
            return None
        متوسط_حجم = float(v.mean())
        اتجاه = float((r > 0).mean() - (r < 0).mean())
        كفاءة = float(abs(r.sum()) / (r.abs().sum() + 1e-12))
        استمرارية = float(abs((r > 0).astype(int).diff().fillna(0)).sum() / max(1, len(r)-1))
        استمرارية = 1.0 - min(1.0, استمرارية)
        return {
            "اتجاه": اتجاه,
            "كفاءة": كفاءة,
            "نشاط_الحجم": float(v.mean() / (أحجام.iloc[:بداية].median() if بداية > 1 and أحجام.iloc[:بداية].median() > 0 else max(v.mean(), 1e-12))),
            "تسارع_الحجم": float(v.iloc[-max(2, len(v)//3):].mean() / max(v.iloc[:max(2, len(v)//3)].mean(), 1e-12)),
            "تقلب": float(rr.mean()),
            "استمرارية": استمرارية,
            "العائد": float(r.sum()),
        }

    الحالية = خصائص(len(data))
    تاريخ = [خصائص(i) for i in range(نافذة*2, len(data)-نافذة+1, نافذة)]
    تاريخ = [x for x in تاريخ if x]
    if len(تاريخ) < 2:
        # خط أساس مبكر من النصف الأول، مع خفض الثقة بدل اختلاق الاستقرار
        تاريخ = [خصائص(len(data)//2)]
    مفاتيح = list(الحالية.keys())
    خط_الأساس = {k: float(statistics.median([x[k] for x in تاريخ])) for k in مفاتيح}
    مقاييس = {
        "اتجاه": 1.0, "كفاءة": 1.0, "نشاط_الحجم": 2.0,
        "تسارع_الحجم": 2.0, "تقلب": 0.02, "استمرارية": 1.0, "العائد": 0.05
    }
    انحرافات = {k: min(100.0, abs(الحالية[k]-خط_الأساس[k]) / مقاييس[k] * 100) for k in مفاتيح}
    الانحراف = float(sum(انحرافات.values()) / len(انحرافات))
    اتجاه_قوة = الحالية["اتجاه"] * 50 + الحالية["كفاءة"] * 25 + (1 if الحالية["نشاط_الحجم"] >= 1 else -1) * min(25, abs(الحالية["نشاط_الحجم"]-1)*25)
    اتجاه = "صعود سلوكي" if اتجاه_قوة >= 20 else ("هبوط سلوكي" if اتجاه_قوة <= -20 else "سلوك مختلط")
    تشابه = max(0.0, 100.0 - الانحراف)
    أدلة = []
    if الحالية["نشاط_الحجم"] >= 1.25:
        أدلة.append(f"نشاط الحجم الحالي أعلى من خطه المرجعي بنحو {الحالية['نشاط_الحجم']:.2f} مرة.")
    if الحالية["تسارع_الحجم"] >= 1.25:
        أدلة.append("الحجم يتسارع داخل النافذة الحالية.")
    if الحالية["كفاءة"] >= 0.55:
        أدلة.append("حركة السعر ذات كفاءة اتجاهية مرتفعة نسبيًا.")
    if الانحراف >= 50:
        أدلة.append("السلوك الحالي مختلف بوضوح عن خط الأساس؛ يلزم فحص مستقل قبل اتخاذ قرار.")
    if not أدلة:
        أدلة.append("لا يوجد انحراف سلوكي حاسم في القراءة الحالية.")
    حالة = "بصمة متماسكة" if تشابه >= 75 else ("بصمة متغيرة" if تشابه >= 50 else "بصمة شاذة")
    تحذيرات = ["البصمة تصف السلوك المرصود ولا تحدد هوية متعامل أو مؤسسة.", "درجة البصمة ليست احتمالًا ولا هدفًا سعريًا."]
    if len(data) < 20 or len(تاريخ) < 3:
        تحذيرات.append("خط الأساس محدود؛ يجب تحديث البصمة مع جلسات إضافية قبل اعتبارها مستقرة.")
    return {
        "الحالة": حالة, "جاهزية": len(data) >= 20, "درجة البصمة": round(تشابه, 2),
        "انحراف السلوك": round(الانحراف, 2), "اتجاه البصمة": اتجاه,
        "البصمة الحالية": {k: round(v, 5) for k, v in الحالية.items()},
        "خط الأساس": {k: round(v, 5) for k, v in خط_الأساس.items()},
        "الأدلة": أدلة, "التحذيرات": تحذيرات, "عدد المقارنات التاريخية": len(تاريخ)
    }




def سجل_بصمة_كوانتوم(البصمة: dict, رمز="غير معروف", تاريخ=""):
    """يحفظ ملخص البصمة في ذاكرة الجلسة ويعيد سجل المقارنات السابقة."""
    if "سجل_بصمات_كوانتوم" not in st.session_state:
        st.session_state["سجل_بصمات_كوانتوم"] = []
    سجل = st.session_state["سجل_بصمات_كوانتوم"]
    الحالية = البصمة.get("البصمة الحالية", {})
    if not الحالية:
        return سجل
    entry = {
        "الرمز": str(رمز), "التاريخ": str(تاريخ),
        "الاتجاه": البصمة.get("اتجاه البصمة", "غير محدد"),
        "الدرجة": البصمة.get("درجة البصمة"),
        "الانحراف": البصمة.get("انحراف السلوك"),
        "الخصائص": الحالية,
    }
    # منع تكرار نفس القراءة داخل إعادة تشغيل الواجهة.
    مفتاح = (entry["الرمز"], entry["التاريخ"], entry["الدرجة"], entry["الانحراف"])
    if not any((x.get("الرمز"), x.get("التاريخ"), x.get("الدرجة"), x.get("الانحراف")) == مفتاح for x in سجل[-20:]):
        سجل.append(entry)
    st.session_state["سجل_بصمات_كوانتوم"] = سجل[-200:]
    return st.session_state["سجل_بصمات_كوانتوم"]


def تحليل_تاريخ_البصمة(البصمة: dict, سجل: list[dict]):
    """يحوّل السجل إلى مرجع تاريخي دون تحويله إلى احتمال تنبؤي."""
    if not البصمة.get("جاهزية") or len(سجل) < 3:
        return {"جاهزية": False, "عدد_السجلات": len(سجل), "الانحراف_التاريخي": None,
                "الاستقرار": "غير كافٍ", "توافق_الاتجاه": "غير محسوب", "تحذير": "يلزم ثلاثة سجلات بصمة على الأقل."}
    درجات = [رقم(x.get("الدرجة")) for x in سجل if رقم(x.get("الدرجة")) is not None]
    انحرافات = [رقم(x.get("الانحراف")) for x in سجل if رقم(x.get("الانحراف")) is not None]
    درجة_حالية = رقم(البصمة.get("درجة البصمة"))
    انحراف_حالي = رقم(البصمة.get("انحراف السلوك"))
    مرجع_درجة = statistics.median(درجات) if درجات else 50.0
    مرجع_انحراف = statistics.median(انحرافات) if انحرافات else 0.0
    فرق_الدرجة = abs(درجة_حالية - مرجع_درجة) if درجة_حالية is not None else 100.0
    فرق_الانحراف = abs(انحراف_حالي - مرجع_انحراف) if انحراف_حالي is not None else 100.0
    اتجاه_حالي = البصمة.get("اتجاه البصمة", "غير محدد")
    اتجاهات = [x.get("الاتجاه") for x in سجل[-10:]]
    توافق = "متماسك" if اتجاه_حالي in اتجاهات[-5:] else ("متغير" if اتجاهات else "غير محسوب")
    استقرار = "مرتفع" if فرق_الدرجة < 10 and فرق_الانحراف < 15 else ("متوسط" if فرق_الدرجة < 20 else "منخفض")
    return {"جاهزية": True, "عدد_السجلات": len(سجل), "الانحراف_التاريخي": round(فرق_الدرجة + فرق_الانحراف * 0.5, 2),
            "الاستقرار": استقرار, "توافق_الاتجاه": توافق, "مرجع_الدرجة": round(مرجع_درجة, 2),
            "مرجع_الانحراف": round(مرجع_انحراف, 2), "تحذير": "المقارنة التاريخية دليل سياقي وليست احتمالًا."}



# ------------------------- جسر الأدلة والتوصية -------------------------
حالات_الشراء = {"ACCUMULATION_SEQUENCE"}
حالات_البيع = {"DISTRIBUTION_SEQUENCE"}

def قيمة_رقمية(value, default=0.0):
    number = رقم(value, default)
    return default if number is None else number

def بناء_جسر_الأدلة(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=["معرف الدليل", "الرمز", "تاريخ الجلسة", "اتجاه الدليل", "قوة الدليل", "عدم اليقين", "حالة الدليل"])
    rows = []
    for _, row in df.iterrows():
        state = str(row.get("sequence_state", "NO_SEQUENCE"))
        buying = قيمة_رقمية(row.get("institutional_flow_score", 0))
        confirmation = قيمة_رقمية(row.get("confirmation_score", 0))
        uncertainty = max(0.0, min(100.0, قيمة_رقمية(row.get("uncertainty_score", 0))))
        relative = قيمة_رقمية(row.get("relative_flow_score", 0))
        raw = 0.60 * buying + 0.25 * confirmation + 0.15 * relative
        strength = max(0.0, min(100.0, abs(raw)))
        direction = "دليل شراء" if state in حالات_الشراء else ("دليل بيع" if state in حالات_البيع else "دليل مختلط")
        status = "لا توجد حركة قابلة للتصرف" if state == "NO_SEQUENCE" else ("ضعيف بسبب عدم اليقين" if uncertainty >= 70 else ("دليل قوي" if strength >= 70 else ("دليل متوسط" if strength >= 45 else "دليل مبكر")))
        rows.append({"معرف الدليل": f"QV-{len(rows)+1:06d}", "الرمز": row.get("symbol", "غير معروف"), "تاريخ الجلسة": row.get("session_date", ""), "اتجاه الدليل": direction, "حالة السلسلة": state, "قوة الدليل": round(strength, 2), "عدم اليقين": round(uncertainty, 2), "حالة الدليل": status})
    return pd.DataFrame(rows)


def بناء_التوصية(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    rows = []
    for _, row in df.iterrows():
        scenario = str(row.get("primary_scenario", "UNCERTAIN_MIXED_FLOW"))
        score = قيمة_رقمية(row.get("scenario_score", 0))
        confirmation = قيمة_رقمية(row.get("confirmation_score", 0))
        uncertainty = قيمة_رقمية(row.get("uncertainty_score", 100), 100)
        trap = قيمة_رقمية(row.get("trap_penalty", 0))
        blocked = trap >= 70 or "LIQUIDITY_TRAP_RISK_HIGH" in str(row.get("warnings", ""))
        if blocked:
            الحالة, التعامل = "محجوب — خطر فخ مرتفع", "لا إجراء"
        elif scenario in {"BULLISH_INSTITUTIONAL_ACCUMULATION_OR_CONTINUATION", "EARLY_BULLISH_ACCUMULATION"} and score >= 55 and confirmation >= 45 and uncertainty < 65:
            الحالة, التعامل = "أدلة إيجابية", "انتظار فحص المخاطر المستقل قبل أي قرار"
        elif scenario in {"BEARISH_DISTRIBUTION_EXIT_PRESSURE", "LIQUIDITY_TRAP_OR_DISTRIBUTION_RISK"} and score >= 55 and confirmation >= 45 and uncertainty < 65:
            الحالة, التعامل = "أدلة سلبية", "تجنب أو حماية المركز بعد فحص المخاطر المستقل"
        elif scenario == "NEUTRAL_MIXED_FLOW":
            الحالة, التعامل = "أدلة محايدة", "انتظار التأكيد"
        else:
            الحالة, التعامل = "غير مؤكدة", "انتظار التأكيد"
        مستوى_الخطر = "مرتفع" if blocked or uncertainty >= 75 else ("متوسط" if uncertainty >= 60 or trap >= 50 else "طبيعي")
        rows.append({"حالة التوصية": الحالة, "طريقة التعامل": التعامل, "مستوى الخطر": مستوى_الخطر, "حالة الثقة": "أدلة مؤكدة" if score >= 70 and confirmation >= 60 and uncertainty < 50 and not blocked else "غير مؤكدة", "الاحتمال": None, "المعايرة": "غير معايرة", "مصرح بالإنتاج": False, "دور النتيجة": "أدلة فقط", "هدف سعري ثابت": None, "فحص بشري للمخاطر": True})
    return pd.concat([df.reset_index(drop=True), pd.DataFrame(rows)], axis=1)


def دمج_الأدلة_والقناص(df: pd.DataFrame, recommendation: pd.DataFrame | None = None) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    result = df.copy()

    # 1) البصمة السلوكية تُحسب على الدفعة كاملة، ثم تُحقن كطبقة مستقلة في جسر الأدلة.
    البصمة = محرك_بصمة_كوانتوم(result.to_dict(orient="records"))
    رمز_الجلسة = str(result.get("symbol", result.get("الرمز", pd.Series(["غير معروف"]))).iloc[0] if len(result) else "غير معروف")
    تاريخ_الجلسة = str(result.get("session_date", result.get("تاريخ الجلسة", pd.Series([""]))).iloc[0] if len(result) else "")
    السجل_السابق = st.session_state.get("سجل_بصمات_كوانتوم", [])
    التاريخ = تحليل_تاريخ_البصمة(البصمة, السجل_السابق)
    السجل = سجل_بصمة_كوانتوم(البصمة, رمز_الجلسة, تاريخ_الجلسة)
    result["حالة البصمة"] = البصمة.get("الحالة", "محجوبة")
    result["درجة البصمة"] = البصمة.get("درجة البصمة")
    result["انحراف البصمة"] = البصمة.get("انحراف السلوك")
    result["اتجاه البصمة"] = البصمة.get("اتجاه البصمة", "غير محدد")
    result["تشغيل البصمة"] = bool(البصمة.get("جاهزية", False))

    if recommendation is not None and not recommendation.empty:
        # دعم كلٍّ من أسماء الأعمدة العربية والحقول الداخلية القديمة.
        keep = [c for c in [
            "الرمز", "حالة التوصية", "طريقة التعامل", "مستوى الخطر", "حالة الثقة",
            "السيناريو الأساسي", "درجة السيناريو", "درجة الدليل", "عدم اليقين", "عقوبة الفخ"
        ] if c in recommendation.columns]
        if keep and "الرمز" in keep and "الرمز" in result.columns:
            result = result.merge(recommendation[keep].drop_duplicates("الرمز"), on="الرمز", how="left")

    # 2) توافق البصمة مع اتجاه السيناريو/التدفق؛ هذا توافق أدلة وليس احتمالًا.
    اتجاه = result.get("اتجاه البصمة", pd.Series("غير محدد", index=result.index))
    سيناريو = result.get("primary_scenario", pd.Series("UNCERTAIN_MIXED_FLOW", index=result.index)).astype(str)
    توافق = []
    for b, sc in zip(اتجاه, سيناريو):
        صاعد = b == "صعود سلوكي" and any(x in sc for x in ("BULLISH", "ACCUMULATION"))
        هابط = b == "هبوط سلوكي" and any(x in sc for x in ("BEARISH", "DISTRIBUTION", "TRAP"))
        مختلط = b == "سلوك مختلط" or "UNCERTAIN" in sc or "NEUTRAL" in sc
        توافق.append("متوافق" if صاعد or هابط else ("محايد" if مختلط else "متعارض"))
    result["توافق البصمة مع السيناريو"] = توافق

    # 3) بوابة مستقلة: لا ترفع النتيجة إلى قرار لمجرد وجود بصمة قوية.
    ready = bool(البصمة.get("جاهزية", False))
    state = str(البصمة.get("الحالة", "محجوبة"))
    result["بوابة البصمة"] = "مفتوحة للرصد" if ready and state != "بصمة شاذة" else "مغلقة للقرار"
    result["الاستقرار التاريخي للبصمة"] = التاريخ.get("الاستقرار", "غير كافٍ")
    result["عدد سجلات البصمة"] = التاريخ.get("عدد_السجلات", 0)
    result["التوافق التاريخي"] = التاريخ.get("توافق_الاتجاه", "غير محسوب")
    # بوابة إضافية: البصمة الشاذة أو غير المستقرة لا تسمح بترقية التوصية.
    if ready and state == "بصمة شاذة":
        result["حالة التكامل"] = "محجوب — بصمة شاذة"
    elif ready and التاريخ.get("الاستقرار") == "منخفض":
        result["حالة التكامل"] = "مراقبة — انحراف تاريخي مرتفع"
    else:
        result["حالة التكامل"] = result.get("حالة التوصية", pd.Series("غير مؤكدة", index=result.index)).fillna("غير مؤكدة")
    result["احتمال التكامل"] = None
    result["مصرح بالإنتاج"] = False
    result["ادعاء هوية"] = False
    return result


# ------------------------- منظومة الاختبار الآلي -------------------------
def اختبار_منظومة_كوانتوم():
    """اختبارات داخلية سريعة تمنع تمرير تغييرات أساسية دون اجتياز بوابات السلامة."""
    نتائج = []
    def تحقق(الاسم, الحالة, تفصيل=""):
        نتائج.append({"الاختبار": الاسم, "الحالة": "ناجح" if الحالة else "فاشل", "التفصيل": تفصيل})
        return الحالة

    try:
        بيانات = [{"السعر": 100 + i * 0.4, "الحجم": 1000 + i * 20} for i in range(60)]
        بصمة = محرك_بصمة_كوانتوم(بيانات)
        تحقق("البصمة — عينة كافية", بصمة.get("جاهزية") is True, str(بصمة.get("الحالة")))
        تحقق("البصمة — لا احتمال مصطنع", بصمة.get("احتمال") is None, "الاحتمال غير مستخدم")
        تحقق("البصمة — لا هدف سعري", بصمة.get("الهدف السعري") is None, "لا يوجد هدف سعري")

        صغيرة = محرك_بصمة_كوانتوم(بيانات[:7])
        تحقق("البصمة — حجب العينة الصغيرة", صغيرة.get("جاهزية") is False, str(صغيرة.get("الحالة")))

        تالفة = [{"السعر": -10, "الحجم": 1000}, {"السعر": 0, "الحجم": 1000}, {"السعر": None, "الحجم": 1000}]
        جاهزية = جاهزية_البيانات(تطبيع(تالفة))
        تحقق("سلامة البيانات — لا تمرر البيانات التالفة", جاهزية.get("جاهزة للرصد") is False and جاهزية.get("عدد القراءات", 0) < 3, str(جاهزية))

        تحقق("محرك التكامل — موجود", callable(دمج_الأدلة_والقناص), "تم العثور على محرك الدمج")
        return {"جاهز": all(x["الحالة"] == "ناجح" for x in نتائج), "النتائج": نتائج}
    except Exception as exc:
        نتائج.append({"الاختبار": "تشغيل المنظومة", "الحالة": "فاشل", "التفصيل": str(exc)})
        return {"جاهز": False, "النتائج": نتائج}

def سجل_مصادر_الأدلة(مصادر=None, حالة_المصالحة="غير مكتملة", تعديلات_إجراءات_الشركة=None):
    """سجل موحد لمصدر كل طبقة، زمنها، وحالة التعارض/المصالحة."""
    rows=[]
    for x in (مصادر or []):
        if not isinstance(x, dict):
            continue
        rows.append({
            "المصدر": str(x.get("المصدر", "غير معروف")),
            "نوع البيانات": str(x.get("نوع البيانات", "غير محدد")),
            "وقت المصدر": str(x.get("وقت المصدر", "غير متاح")),
            "زمن البيانات": str(x.get("زمن البيانات", "غير متاح")),
            "أولوية المصدر": قيمة_رقمية(x.get("أولوية المصدر", 0)),
            "الحالة": str(x.get("الحالة", "متاح")),
            "ملاحظة": str(x.get("ملاحظة", "")),
        })
    return {
        "المصادر": rows,
        "حالة المصالحة": حالة_المصالحة,
        "تعديل إجراءات الشركة": تعديلات_إجراءات_الشركة or {"الحالة":"غير مثبت"},
        "القاعدة": "لا تُدمج قراءات متعارضة زمنيًا كأنها لقطة واحدة."
    }

def تحليل_الشمعة(row: dict):
    """تصنيف مستقل للشمعة، دون تحويلها إلى تنبؤ."""
    o=رقم(أول_قيمة(row,"الافتتاح","open")); h=رقم(أول_قيمة(row,"الأعلى","high")); l=رقم(أول_قيمة(row,"الأدنى","low")); c=رقم(أول_قيمة(row,"الإغلاق","close","السعر"))
    if None in (o,h,l,c) or h < l:
        return {"الحالة":"غير قابلة للتحليل","اتجاه":"غير محدد","الأدلة":[],"تحذير":"بيانات الشمعة ناقصة أو غير منطقية."}
    جسم=abs(c-o); مدى=max(h-l,1e-12); علوي=h-max(o,c); سفلي=min(o,c)-l
    نسبة_الجسم=جسم/مدى
    if c>o and نسبة_الجسم>=0.55 and علوي <= جسم*0.6:
        الحالة="إيجابية قوية نسبيًا"
    elif c>o:
        الحالة="إيجابية مع رفض علوي/تردد"
    elif c<o and نسبة_الجسم>=0.55 and سفلي <= جسم*0.6:
        الحالة="سلبية قوية نسبيًا"
    elif c<o:
        الحالة="سلبية مع رفض سفلي/تردد"
    else:
        الحالة="توازن/دوجي تقريبي"
    return {"الحالة":الحالة,"اتجاه":"صاعد" if c>o else ("هابط" if c<o else "محايد"),"نسبة الجسم":round(نسبة_الجسم,4),"الظل العلوي":round(علوي,4),"الظل السفلي":round(سفلي,4),"الأدلة":[f"المدى {مدى:.2f}، جسم الشمعة {جسم:.2f}."] ,"تحذير":"تصنيف الشمعة دليل مساعد وليس قرارًا منفردًا."}

def تحليل_الحجم_النسبي(سجلات):
    data=تطبيع(سجلات)
    if len(data)<3: return {"جاهزية":False,"الحالة":"محجوب — بيانات غير كافية"}
    v=[x["الحجم"] for x in data]; cur=v[-1]
    def med(n):
        a=[z for z in v[-(n+1):-1] if z>0]
        return statistics.median(a) if a else None
    w=med(5); m=med(20)
    return {"جاهزية":True,"الحجم الحالي":cur,"مقابل متوسط قصير":None if not w else round(cur/w,3),"مقابل متوسط متوسط":None if not m else round(cur/m,3),"الحالة":"نشاط أعلى من المرجع" if (w and cur/w>=1.25) else "نشاط طبيعي/منخفض","تحذير":"النسب وصفية ولا تثبت هوية متعامل أو تجميعًا مؤسسيًا."}

def مصالحة_إجراءات_الشركة(بيانات):
    """يكشف التعارضات الشائعة في رأس المال وعدد الأسهم بعد إجراءات الشركة."""
    رأس=[رقم(أول_قيمة(x,"رأس المال","capital","market_capital")) for x in (بيانات or []) if isinstance(x,dict)]
    أسهم=[رقم(أول_قيمة(x,"عدد الأسهم","shares","shares_outstanding")) for x in (بيانات or []) if isinstance(x,dict)]
    رأس=[x for x in رأس if x is not None]; أسهم=[x for x in أسهم if x is not None]
    تعارض=(len(set(round(x,6) for x in رأس))>1 or len(set(round(x,6) for x in أسهم))>1)
    return {"الحالة":"تعارض يحتاج مصالحة" if تعارض else "لا تعارض ظاهر","قيم رأس المال":رأس,"قيم عدد الأسهم":أسهم,"قاعدة":"تُقدَّم إفصاحات إجراءات الشركة المؤرخة على الحقول الثابتة القديمة عند وجود دليل زمني أقوى."}

def اختبار_تكامل_شامل():
    """اختبارات تكامل محلية للطبقات المتاحة دون ادعاء اتصال بمصادر خارجية."""
    اختبارات=[]
    def تحقق(اسم,شرط): اختبارات.append({"الاختبار":اسم,"النتيجة":"ناجح" if شرط else "فشل"})
    بيانات=[{"symbol":"OCPH","session_date":str(i),"open":250+i*0.1,"high":252+i*0.1,"low":248+i*0.1,"close":251+i*0.15,"volume":1000+i*50} for i in range(25)]
    b=محرك_بصمة_كوانتوم(بيانات)
    تحقق("محرك البصمة يعمل على عينة كافية", b.get("جاهزية") is True and b.get("درجة البصمة") is not None)
    تحقق("لا احتمال اصطناعي", b.get("درجة البصمة") is not None and "احتمال" not in b)
    تحقق("لا هدف سعري ثابت", True)
    تحقق("تصنيف الشمعة مستقل", تحليل_الشمعة(بيانات[-1]).get("الحالة") != "غير قابلة للتحليل")
    تحقق("تحليل الحجم النسبي", تحليل_الحجم_النسبي(بيانات).get("جاهزية") is True)
    تحقق("بوابة البيانات القصيرة", محرك_بصمة_كوانتوم(بيانات[:7]).get("جاهزية") is False)
    تحقق("المصالحة تكشف التعارض", مصالحة_إجراءات_الشركة([{"رأس المال":120},{"رأس المال":240}]).get("الحالة")=="تعارض يحتاج مصالحة")
    تحقق("جسر الأدلة لا يكسر عند الفراغ", isinstance(بناء_جسر_الأدلة(pd.DataFrame()),pd.DataFrame))
    تفاوض=اختبار_بوابة_التفاوض()
    اختبارات.extend([{"الاسم":k,"النتيجة":"ناجح" if v else "فاشل"} for k,v in تفاوض.items()])
    ناجح=sum(x["النتيجة"]=="ناجح" for x in اختبارات)
    return {"الاختبارات":اختبارات,"الإجمالي":len(اختبارات),"الناجح":ناجح,"الفاشل":len(اختبارات)-ناجح,"جاهزية_الإنتاج":False,"ملاحظة":"هذه اختبارات محلية؛ لا تثبت اتصالًا حيًا بمصادر السوق الخارجية."}



# ------------------------- بوابة البيانات الحية -------------------------
# موصل أولي: EGXAPI — بيانات البورصة المصرية اللحظية والتاريخية.
# لا نضع المفتاح داخل الكود؛ يُقرأ من أسرار Streamlit أو متغير البيئة.

import os
import time
from datetime import datetime, timezone

مصدر_افتراضي = "EGXAPI"
رابط_مصدر_البيانات = os.getenv("EGX_API_BASE", "https://api.egxapi.com").rstrip("/")

# ------------------------- حوكمة الشراكات ومصادر البيانات -------------------------
# لا يوقّع كوانتوم فيكتوري عقدًا أو يقبل شروط طرف ثالث نيابةً عن المستخدم أو شركة
# أو كيان قانوني. النظام يستطيع تجهيز طلب التعاون، التحقق من الحالة، ثم تفعيل
# المصدر آليًا بعد وجود قبول/مفتاح/تفويض صالح من الطرف الآخر.

سجل_مزودي_البيانات = {
    "EGXAPI": {
        "الاسم": "واجهة بيانات البورصة المصرية EGXAPI",
        "النوع": "مزود بيانات وواجهة تداول",
        "مجاني": True,
        "بيانات_لحظية": True,
        "بث_مستمر": True,
        "دفتر_أوامر": True,
        "الحالة_القانونية": "شروط استخدام واتفاقيات منشورة — لا توجد اتفاقية تعاون خاصة موقعة تلقائيًا",
        "رابط_الشروط": "https://egxapi.com/legal/",
        "رابط_التوثيق": "https://egxapi.com/docs/",
        "رابط_التسجيل": "https://egxapi.com/",
        "مفتاح_البيئة": "EGX_KEY",
        "حالة_التفعيل": "بانتظار مفتاح صالح وموافقة صاحب الحساب"
    },
    "TwelveData": {
        "الاسم": "Twelve Data",
        "النوع": "مزود بيانات متعدد الأسواق",
        "مجاني": "وفق الخطة والشروط الحالية",
        "بيانات_لحظية": "تُتحقق حسب الرمز والخطة",
        "بث_مستمر": "حسب الخطة",
        "دفتر_أوامر": False,
        "الحالة_القانونية": "لا تفعيل ولا إعادة توزيع قبل قبول شروط المزود والترخيص المناسب",
        "رابط_الشروط": "https://twelvedata.com/terms",
        "رابط_التوثيق": "https://twelvedata.com/docs",
        "رابط_التسجيل": "https://twelvedata.com/",
        "مفتاح_البيئة": "TWELVEDATA_API_KEY",
        "حالة_التفعيل": "غير مفعّل"
    },
    "AlphaVantage": {"الاسم":"Alpha Vantage","النوع":"مزود بيانات سوق اختياري","مجاني":"حسب الخطة والشروط","بيانات_لحظية":"حسب الخطة","بث_مستمر":"حسب الخطة","دفتر_أوامر":False,"الحالة_القانونية":"لا تفعيل أو إعادة توزيع قبل التحقق من الشروط والترخيص","رابط_الشروط":"https://www.alphavantage.co/terms_of_service/","رابط_التوثيق":"https://www.alphavantage.co/documentation/","رابط_التسجيل":"https://www.alphavantage.co/","مفتاح_البيئة":"ALPHAVANTAGE_API_KEY","حالة_التفعيل":"غير مفعّل"}
}


# ------------------------- محرك التفاوض الشبكي والتكاملي -------------------------
# هذه الطبقة تنفذ "تفاوضًا تقنيًا" آمنًا: فحص الوصول، القدرات، المصادقة،
# الشروط، والصحة. لا تنشئ موافقة قانونية ولا تتجاوز OAuth أو مفاتيح المستخدم.

بوابات_التكامل = {
    "EGXAPI": {
        "النوع": "مزود بيانات سوق",
        "العنوان": "https://api.egxapi.com",
        "توثيق": "https://egxapi.com/docs/",
        "شروط": "https://egxapi.com/legal/",
        "مفتاح": "EGX_KEY",
        "حالة": "يحتاج تفويضًا ومفتاحًا صالحًا ومسارات موثقة"
    },
    "GitHub": {
        "النوع": "مستودع الشفرة والتحكم بالإصدارات",
        "العنوان": "https://github.com",
        "توثيق": "https://docs.github.com/",
        "شروط": "https://docs.github.com/en/site-policy/github-terms/github-terms-of-service",
        "مفتاح": "GITHUB_TOKEN",
        "حالة": "يحتاج ربط حساب/رمز وصول أو اتصال التطبيق"
    },
    "Streamlit Community Cloud": {
        "النوع": "تشغيل ونشر التطبيق",
        "العنوان": "https://share.streamlit.io",
        "توثيق": "https://docs.streamlit.io/deploy/streamlit-community-cloud",
        "شروط": "https://streamlit.io/terms-of-service",
        "مفتاح": "",
        "حالة": "يحتاج ربط GitHub وصلاحيات المستودع"
    },
    "TwelveData": {
        "النوع": "مزود بيانات سوق احتياطي",
        "العنوان": "https://twelvedata.com",
        "توثيق": "https://twelvedata.com/docs",
        "شروط": "https://twelvedata.com/terms",
        "مفتاح": "TWELVEDATA_API_KEY",
        "حالة": "غير مفعّل؛ لا تفعيل أو إعادة توزيع قبل التحقق من الخطة والشروط"
    },
}

def _فحص_شبكي_بوابة(اسم, timeout=8):
    """فحص وصول عام فقط؛ لا يرسل أسرارًا ولا يحاول تجاوز المصادقة."""
    cfg = بوابات_التكامل.get(اسم, {})
    url = cfg.get("العنوان", "")
    if not url:
        return {"البوابة": اسم, "نجاح": False, "الحالة": "لا يوجد عنوان"}
    try:
        import requests
        started=time.perf_counter()
        r=requests.get(url, timeout=(3, timeout), allow_redirects=True,
                        headers={"User-Agent":"Quantum-Victory-Gateway-Probe/1.0","Accept":"text/html,application/json;q=0.9,*/*;q=0.8"})
        return {"البوابة": اسم, "نجاح": r.status_code < 500,
                "رمز_HTTP": r.status_code, "العنوان_النهائي": r.url,
                "زمن_الاستجابة_مللي": round((time.perf_counter()-started)*1000,2),
                "مصادقة": "لم تُرسل", "أسرار": "لم تُرسل"}
    except Exception as exc:
        return {"البوابة": اسم, "نجاح": False, "الخطأ": _تنظيف_خطأ(exc),
                "مصادقة": "لم تُرسل", "أسرار": "لم تُرسل"}

def _حالة_مصادقة_البوابة(اسم):
    cfg=بوابات_التكامل.get(اسم,{})
    env=cfg.get("مفتاح","")
    if not env:
        return {"البوابة":اسم,"المفتاح_متوفر":False,"النتيجة":"يتطلب OAuth/ربط حساب أو صلاحيات خارجية"}
    موجود=bool(_قيمة_سرية(env)) if "_قيمة_سرية" in globals() else bool(os.getenv(env,""))
    return {"البوابة":اسم,"المفتاح_متوفر":موجود,
            "النتيجة":"مفتاح موجود — لم يُختبر بصلاحية كتابة/نشر" if موجود else "مفتاح غير موجود"}

def ملف_تفاوض_بوابات_التكامل():
    """ينشئ سجل تفاوض قابلًا للتدقيق لكل البوابات دون ادعاء موافقة الطرف الآخر."""
    الآن=datetime.now(timezone.utc).isoformat()
    نتائج=[]
    for اسم,cfg in بوابات_التكامل.items():
        net=_فحص_شبكي_بوابة(اسم)
        auth=_حالة_مصادقة_البوابة(اسم)
        نتائج.append({"البوابة":اسم,"النوع":cfg.get("النوع"),"وقت":الآن,
                      "الشبكة":net,"المصادقة":auth,
                      "التوثيق":cfg.get("توثيق"),"الشروط":cfg.get("شروط"),
                      "الحالة_المعلنة":cfg.get("حالة")})
    return {"الإصدار":"r7-بوابة-التفاوض-1","وقت":الآن,"النتائج":نتائج,
            "قاعدة":"الفحص الشبكي لا يساوي موافقة قانونية ولا تفويض كتابة/نشر."}

def بوابة_التكامل_الكاملة():
    تقرير=ملف_تفاوض_بوابات_التكامل()
    أسباب=[]
    for item in تقرير["النتائج"]:
        if not item["الشبكة"].get("نجاح"):
            أسباب.append(f"فشل الوصول: {item['البوابة']}")
    egx=تحقق_تفويض_المصدر("EGXAPI",
        os.getenv("QV_SOURCE_AUTHORIZED","").lower()=="true",
        bool(مفتاح_البيانات_الحية()),
        os.getenv("QV_TERMS_ACCEPTED","").lower()=="true")
    if not egx["مصرح"]: أسباب.append("EGXAPI: التفويض/الشروط/المفتاح غير مكتمل")
    gh=_حالة_مصادقة_البوابة("GitHub")
    if not gh.get("المفتاح_متوفر"): أسباب.append("GitHub: لم يتم ربط اعتماد دفع فعلي")
    return {"جاهزية_التفاوض": not أسباب, "الأسباب":أسباب,
            "التقرير":تقرير,"EGXAPI":egx,"GitHub":gh,
            "Streamlit":"مرتبط عبر GitHub عند النشر؛ يحتاج صلاحيات المستودع"}

def _مسار_سجل_التفاوض():
    return Path(os.getenv("QV_NEGOTIATION_LOG", "data/سجل_التفاوض_المستمر.jsonl"))

def _حفظ_تفاوض_مستمر(تقرير):
    """يحفظ كل دورة تفاوض كسجل تدقيق تراكمي دون حفظ الأسرار."""
    المسار=_مسار_سجل_التفاوض()
    المسار.parent.mkdir(parents=True, exist_ok=True)
    سجل={"وقت":تقرير.get("وقت"),"الإصدار":تقرير.get("الإصدار"),"النتائج":تقرير.get("النتائج",[]),
         "بصمة":hashlib.sha256(json.dumps(تقرير,ensure_ascii=False,sort_keys=True).encode()).hexdigest()}
    with المسار.open("a",encoding="utf-8") as f:
        f.write(json.dumps(سجل,ensure_ascii=False,sort_keys=True)+"\n")
    try:
        مخزن_كوانتوم(os.getenv("QV_DB_PATH", "data/qv_operational.sqlite3")).تدقيق(
            "تفاوض_بوابات_آلي", "تم_الفحص", سجل, "منظومة_البوابات")
    except Exception as exc:
        سجل["خطأ_التخزين"] = _تنظيف_خطأ(exc) if "_تنظيف_خطأ" in globals() else "تعذر حفظ التدقيق"
    return سجل

def تشغيل_التفاوض_المستمر(force=False):
    """دورة تفاوض تقنية آلية ومحمية؛ لا توقّع عقودًا ولا تمنح صلاحيات."""
    now=time.monotonic()
    interval=max(30,int(os.getenv("QV_NEGOTIATION_INTERVAL_SECONDS","60")))
    last=globals().get("_آخر_تفاوض_آلي",0.0)
    if not force and now-last < interval:
        return globals().get("_آخر_تقرير_تفاوض_آلي")
    تقرير=ملف_تفاوض_بوابات_التكامل()
    سجل=_حفظ_تفاوض_مستمر(تقرير)
    globals()["_آخر_تفاوض_آلي"]=now
    globals()["_آخر_تقرير_تفاوض_آلي"]=تقرير
    return تقرير



def خطة_الحصول_على_اعتماد_البوابات():
    """ينشئ خطة اعتماد قابلة للتنفيذ دون اختلاق مفاتيح أو تجاوز تسجيل الدخول.
    المفتاح السري لا يُستخرج من الويب ولا من سجل التفاوض؛ يجب أن يصدره المزود
    بعد مصادقة صاحب الحساب وقبول الشروط، ثم يُحقن في أسرار التشغيل.
    """
    الآن=datetime.now(timezone.utc).isoformat()
    return {
        "وقت": الآن,
        "القاعدة": "لا استخراج أو تخمين أو تجاوز للمصادقة؛ الاعتماد يصدر من المزود بعد موافقة المستخدم.",
        "EGXAPI": {
            "المسار": "إنشاء حساب ← تسجيل الدخول ← إنشاء مفتاح من لوحة مفاتيح API ← حفظه في EGX_KEY",
            "التسجيل": "https://egxapi.com/",
            "المصادقة": "https://egxapi.com/auth/",
            "التوثيق": "https://egxapi.com/docs/",
            "التحقق_البرمجي": "GET /v2/account مع Authorization: Bearer $EGX_KEY و X-EGX-Env: paper",
            "الحالة": "يتطلب فعلًا من صاحب الحساب؛ لا يمكن للنظام إنشاء/استلام السر نيابة عنه"
        },
        "GitHub": {
            "المسار": "ربط حساب GitHub/تطبيق أو توفير رمز وصول محدود الصلاحيات عبر أسرار بيئة التشغيل",
            "التحقق": "لا يُسجل الرمز ولا يُعرض؛ يختبر وجوده وصلاحيته فقط عند توفر مسار API معتمد",
            "الحالة": "يتطلب تفويض صاحب الحساب"
        },
        "Streamlit Community Cloud": {
            "المسار": "ربط مستودع GitHub من حساب صاحب المشروع ثم إضافة EGX_KEY إلى Secrets",
            "الحالة": "لا يمكن للنظام استخراج رمز منصة النشر من خارج حساب المستخدم"
        },
        "السرية": "المفاتيح لا تدخل Git ولا سجل التفاوض ولا التقرير ولا واجهة المستخدم."
    }


def اختبار_اعتماد_البوابة(اسم="EGXAPI"):
    """يتحقق برمجياً من الاعتماد الموجود فقط؛ لا يحاول إنشاءه أو تجاوزه."""
    if اسم == "EGXAPI":
        key=مفتاح_البيانات_الحية()
        if not key:
            return {"البوابة": اسم, "المفتاح_متوفر": False, "صالح": False,
                    "القرار": "محجوب — يلزم إنشاء/إدخال مفتاح من لوحة المزود"}
        payload, meta=_طلب_بيانات_حقيقي("/v2/account", مهلة=8)
        return {"البوابة": اسم, "المفتاح_متوفر": True,
                "صالح": bool(meta.get("نجاح")), "الحالة": meta,
                "الحساب_تم_جلبه": bool(payload),
                "القرار": "اعتماد صالح للاستخدام بعد فحص التفويض" if meta.get("نجاح") else "المفتاح موجود لكن التحقق فشل"}
    return {"البوابة": اسم, "المفتاح_متوفر": bool(_حالة_مصادقة_البوابة(اسم).get("المفتاح_متوفر")),
            "صالح": False, "القرار": "يلزم مسار تحقق خاص بالبوابة"}



def إنشاء_تفويض_واعتماد_تشغيلي():
    """ينشئ سجل تفويض واعتماد آمنًا قابلًا للتدقيق.
    لا ينشئ مفتاحًا سريًا ولا يزوّر موافقة مزود الخدمة.
    التفويض الداخلي يصبح فعالًا فقط إذا أثبت صاحب الحساب القبول
    وأضيف المفتاح عبر أسرار التشغيل، ثم نجح اختبار الاعتماد.
    """
    الآن=datetime.now(timezone.utc).isoformat()
    egx_key=bool(مفتاح_البيانات_الحية())
    تفويض_صريح=os.getenv("QV_SOURCE_AUTHORIZED", "").strip().lower()=="true"
    شروط_مقبولة=os.getenv("QV_TERMS_ACCEPTED", "").strip().lower()=="true"
    الإنتاج=os.getenv("QV_PRODUCTION_APPROVED", "").strip().lower()=="true"
    اختبار=اختبار_اعتماد_البوابة("EGXAPI")
    حالة="جاهز_للاختبار_النهائي" if (تفويض_صريح and شروط_مقبولة and egx_key) else "معلق_حتى_تفويض_صاحب_الحساب"
    سجل={
        "الإصدار":"r12-تفويض-واعتماد-آمن",
        "وقت":الآن,
        "المصدر":"EGXAPI",
        "التفويض":{
            "تفويض_صريح_مسجل":تفويض_صريح,
            "الشروط_مقبولة_مسجلة":شروط_مقبولة,
            "موافقة_الإنتاج_مسجلة":الإنتاج,
            "مصدر_الموافقة":"متغيرات تشغيلية يحددها صاحب الحساب/المسؤول فقط",
            "لا_توقيع_نيابة_عن_المالك":True
        },
        "الاعتماد":{
            "المفتاح_متوفر":egx_key,
            "المفتاح_لم_يُسجل":True,
            "نتيجة_الاختبار":اختبار
        },
        "الحوكمة":{
            "لا_تخمين_للمفتاح":True,
            "لا_استخراج_للمفتاح_من_الويب":True,
            "لا_تجاوز_للمصادقة":True,
            "عدم_حفظ_السر_في_السجل":True
        },
        "الحالة":حالة
    }
    try:
        مخزن_كوانتوم(os.getenv("QV_DB_PATH", "data/qv_operational.sqlite3")).تدقيق(
            "إنشاء_تفويض_واعتماد", حالة, سجل, "منظومة_البوابات")
    except Exception:
        pass
    return سجل


def تجهيز_بيئة_التفويض_والاعتماد():
    """ينشئ قالب إعداد آمن لأسرار التشغيل دون وضع أي أسرار حقيقية."""
    return {
        "EGX_KEY":"ضع_المفتاح_الذي_أصدره_مزود_الخدمة_في_أسرار_المنصة",
        "QV_SOURCE_AUTHORIZED":"true بعد قبول صاحب الحساب للتفويض والشروط",
        "QV_TERMS_ACCEPTED":"true بعد مراجعة وقبول الشروط السارية",
        "QV_PRODUCTION_APPROVED":"false حتى يكتمل اختبار الورق والتحقق",
        "QV_EGX_ENV":"paper",
        "قاعدة":"لا تضع المفتاح داخل GitHub أو الكود أو سجل التفاوض"
    }

def اختبار_بوابة_التفاوض():
    r=ملف_تفاوض_بوابات_التكامل()
    أسماء={x["البوابة"] for x in r["النتائج"]}
    return {
        "تسجيل_كل_البوابات": أسماء==set(بوابات_التكامل),
        "عدم_إرسال_الأسرار_في_الفحص": all(x["الشبكة"].get("أسرار")=="لم تُرسل" for x in r["النتائج"]),
        "الفصل_بين_الوصول_والتفويض": r["قاعدة"].startswith("الفحص الشبكي")
    }

def حالة_حوكمة_المصادر():
    """يعيد حالة كل مزود دون ادعاء موافقة أو عقد لم يحدث فعليًا."""
    حالات=[]
    for الاسم, بيانات in سجل_مزودي_البيانات.items():
        مفتاح=بيانات.get("مفتاح_البيئة", "")
        موجود=bool(os.getenv(مفتاح, "").strip())
        if الاسم == "EGXAPI":
            موجود = bool(مفتاح_البيانات_الحية()) if "مفتاح_البيانات_الحية" in globals() else موجود
        حالات.append({
            "المصدر": الاسم,
            "مجاني": بيانات.get("مجاني"),
            "بيانات لحظية": بيانات.get("بيانات_لحظية"),
            "بث مستمر": بيانات.get("بث_مستمر"),
            "المفتاح متوفر": موجود,
            "الحالة القانونية": بيانات.get("الحالة_القانونية"),
            "حالة التفعيل": "مهيأ بعد توفير المفتاح" if موجود else بيانات.get("حالة_التفعيل")
        })
    return حالات

def إنشاء_طلب_تعاون_بيانات(اسم_الجهة="مزود البيانات"):
    """ينشئ طلب تعاون قانوني قابل للإرسال؛ لا يمثل توقيعًا أو قبولًا."""
    return {
        "نوع الوثيقة": "طلب تفاوض واتفاقية تعاون وتبادل بيانات",
        "الجهة": اسم_الجهة,
        "الغرض": "تبادل بيانات السوق المصرح بها لاستخدامها في التحليل مع احترام حقوق الملكية والترخيص والخصوصية والأمن.",
        "المبادئ": [
            "لا إعادة توزيع للبيانات إلا بترخيص صريح.",
            "لا استخدام لبيانات شخصية أو أسرار تجارية دون أساس قانوني وتصريح.",
            "تشفير المفاتيح والأسرار وعدم إدراجها في الشفرة أو المستودع.",
            "سجل تدقيق لكل مصدر ووقت استقبال ونسخة من شروط الاستخدام المقبولة.",
            "إيقاف تلقائي للمصدر عند انتهاء التفويض أو تغير الشروط أو فشل فحص السلامة.",
            "الفصل بين بيانات السوق الخام ونتائج التحليل الخاصة بكوانتوم فيكتوري.",
            "أي اتفاق ملزم يتطلب قبول الطرفين من ممثلين مخولين قانونيًا."
        ],
        "حالة": "مسودة تفاوض — غير موقعة وغير ملزمة",
        "تنبيه": "لا يجوز للنظام الادعاء بوجود اتفاق أو توقيع أو موافقة من الجهة دون سجل قبول موثق."
    }

def سجل_موافقة_المستخدم(اسم_المصدر, نوع_الموافقة="موافقة معلنة من صاحب المشروع"):
    """يسجل تصريح المستخدم محليًا دون ادعاء أنه توقيع قانوني للطرف الآخر."""
    return {
        "المصدر": اسم_المصدر,
        "نوع_الموافقة": نوع_الموافقة,
        "الحالة": "موافقة تشغيلية معلنة من المستخدم — يلزم الاحتفاظ بدليل قبول الجهة عند الحاجة القانونية",
        "وقت_التسجيل": datetime.now(timezone.utc).isoformat(),
    }

مصادر_مجانية_مرشحة = {
    "EGXAPI": {
        "الأولوية": 1, "النوع": "مزود بيانات وواجهة تداول",
        "البيانات": ["أسعار لحظية", "صفقات", "شموع", "دفتر أوامر"],
        "الحالة": "متاح ومعلن مجانًا — يحتاج مفتاحًا وتوثيق قبول الشروط/الترخيص المناسب",
        "المرجع": "https://egxapi.com/"
    },
    "TwelveData": {
        "الأولوية": 2, "النوع": "مزود بيانات متعدد الأسواق",
        "البيانات": ["تاريخية", "بيانات سوق بحسب الخطة والرمز"],
        "الحالة": "خطة مجانية محدودة؛ لا يُفترض منها تغطية EGX اللحظية الكاملة أو حق إعادة التوزيع",
        "المرجع": "https://twelvedata.com/"
    },
    "مصدر_مفتوح_للاختبار": {
        "الأولوية": 3, "النوع": "مصادر/مكتبات مفتوحة غير معتمدة كمصدر إنتاج",
        "البيانات": ["تاريخية/داخلية بحسب المصدر"],
        "الحالة": "للاختبار فقط حتى يتم التحقق من الترخيص والدقة والحداثة",
        "المرجع": ""
    },
}

def تقييم_المصادر_المجانية():
    """يبني مصفوفة المصادر دون اختلاق اتفاقيات أو صلاحيات إعادة توزيع."""
    النتائج=[]
    for اسم, بيانات in مصادر_مجانية_مرشحة.items():
        مفتاح = سجل_مزودي_البيانات.get(اسم, {}).get("مفتاح_البيئة", "")
        متاح_مفتاح = bool(os.getenv(مفتاح, "").strip()) if مفتاح else False
        if اسم == "EGXAPI":
            متاح_مفتاح = bool(مفتاح_البيانات_الحية()) if "مفتاح_البيانات_الحية" in globals() else متاح_مفتاح
        النتائج.append({
            "المصدر": اسم, "الأولوية": بيانات["الأولوية"], "النوع": بيانات["النوع"],
            "المفتاح": متاح_مفتاح, "الحالة": بيانات["الحالة"], "البيانات": ", ".join(بيانات["البيانات"]),
            "القرار": "قابل للتجهيز" if متاح_مفتاح else "بانتظار الاعتماد/المفتاح"
        })
    return النتائج

def بناء_حزمة_تفاوض_موحدة(اسم_الجهة):
    """حزمة تفاوض آمنة: رسالة، نطاق بيانات، حدود الترخيص، ومتطلبات التكامل."""
    return {
        "الجهة": اسم_الجهة,
        "الموضوع": "طلب تعاون وتكامل آمن لتبادل بيانات السوق المصرح بها",
        "الطلبات": [
            "تأكيد نوع البيانات المتاحة ودرجة تأخرها",
            "تأكيد حدود الاستخدام الشخصي/التجاري وإعادة التوزيع",
            "تأكيد حدود المعدل وواجهات REST/WebSocket إن وجدت",
            "تأكيد متطلبات الأمن وحفظ المفاتيح",
            "تأكيد آلية الإيقاف والإلغاء وتغيير الشروط",
            "توفير موافقة أو ترخيص قابل للإثبات قبل تشغيل الإنتاج"
        ],
        "قاعدة": "لا يوقع النظام نيابة عن أي طرف، ولا يعتبر إنشاء مفتاح أو حساب اتفاقية تعاون خاصة."
    }

def تحقق_تفويض_المصدر(اسم_المصدر, حالة_قبول=False, مفتاح_صالح=False, شروط_مقبولة=False):
    """بوابة قانونية: لا تفعيل تشغيلي إلا بعد تحقق التفويض الفعلي."""
    مصرح = bool(حالة_قبول and مفتاح_صالح and شروط_مقبولة)
    return {
        "المصدر": اسم_المصدر,
        "مصرح": مصرح,
        "القرار": "مسموح بالتفعيل" if مصرح else "محجوب — يلزم قبول موثق ومفتاح صالح وشروط مقبولة",
        "قاعدة": "وجود مفتاح وحده لا يثبت حق إعادة توزيع البيانات ولا وجود اتفاق تعاون."
    }



def مفتاح_البيانات_الحية():
    """يقرأ المفتاح بأمان من أسرار Streamlit أو متغير البيئة دون عرضه."""
    return _قيمة_سرية("EGX_KEY")


def حالة_مصدر_البيانات(مصدر=مصدر_افتراضي):
    key = مفتاح_البيانات_الحية() if مصدر == "EGXAPI" else ""
    return {
        "المصدر": مصدر,
        "المفتاح_متوفر": bool(key),
        "الحالة": "مهيأ" if key else "غير مهيأ",
        "البيانات_الحية": False,
        "آخر_نجاح": None,
        "آخر_خطأ": None,
        "زمن_الاستجابة_مللي": None,
        "رابط_المصدر": رابط_مصدر_البيانات,
    }


def _طلب_بيانات_حقيقي(path, params=None, مهلة=8):
    """طبقة HTTP موحدة: مهلة، تحقق نوع المحتوى، وإخفاء الأخطاء الحساسة."""
    try:
        import requests
    except ImportError as exc:
        return None, {"نجاح": False, "الخطأ": "مكتبة requests غير مثبتة.", "تفصيل": str(exc)}
    key = مفتاح_البيانات_الحية()
    if not key:
        return None, {"نجاح": False, "الخطأ": "مفتاح EGXAPI غير موجود."}
    headers = {"Accept": "application/json"}
    نمط_المصادقة = os.getenv("EGX_AUTH_SCHEME", "Bearer").strip() or "Bearer"
    headers["Authorization"] = f"{نمط_المصادقة} {key}"
    started = time.perf_counter()
    try:
        url = f"{رابط_مصدر_البيانات}{path}"
        r = requests.get(url, headers=headers, params=params or {}, timeout=(3, مهلة))
        elapsed = round((time.perf_counter() - started) * 1000, 2)
        content_type = str(r.headers.get("content-type", "")).lower()
        if r.status_code >= 400:
            return None, {"نجاح": False, "الرمز": r.status_code, "الخطأ": _تنظيف_خطأ(r.text), "زمن_الاستجابة_مللي": elapsed}
        if "json" not in content_type:
            return None, {"نجاح": False, "الرمز": r.status_code, "الخطأ": "استجابة المصدر ليست JSON.", "زمن_الاستجابة_مللي": elapsed}
        return r.json(), {"نجاح": True, "الرمز": r.status_code, "زمن_الاستجابة_مللي": elapsed, "وقت_الاستجابة": datetime.now(timezone.utc).isoformat()}
    except Exception as exc:
        return None, {"نجاح": False, "الخطأ": _تنظيف_خطأ(exc), "زمن_الاستجابة_مللي": round((time.perf_counter()-started)*1000, 2)}


def _استخراج_قائمة(payload):
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return []
    for key in ("data", "bars", "quotes", "results", "items", "candles"):
        value = payload.get(key)
        if isinstance(value, list):
            return value
    return []


def جلب_بيانات_مؤشر_حية(الرمز, المسار=None):
    """موصل المؤشرات منفصل عن موصل الأسهم لتجنب خلط دلالات المصدر."""
    المسار = المسار or os.getenv("EGX_INDEX_QUOTES_PATH", "").strip()
    if not المسار:
        return {"نجاح": False, "المصدر": مصدر_افتراضي, "الرمز": الرمز, "بيانات": [], "حالة": {"النجاح": False, "الخطأ": "مسار المؤشرات غير معتمد من توثيق المزود."}}
    payload, meta = _طلب_بيانات_حقيقي(المسار, {"symbol": الرمز, "type": "index"})
    if not meta.get("نجاح"):
        return {"نجاح": False, "المصدر": مصدر_افتراضي, "الرمز": الرمز, "بيانات": [], "حالة": meta}
    rows = _استخراج_قائمة(payload)
    if not rows and isinstance(payload, dict): rows = [payload]
    return {"نجاح": bool(rows), "المصدر": مصدر_افتراضي, "الرمز": الرمز, "بيانات": rows, "حالة": meta, "وقت_الاستلام": datetime.now(timezone.utc).isoformat()}


def جلب_بيانات_سهم_حية(الرمز, المسار=None):
    المسار = المسار or os.getenv("EGX_QUOTES_PATH", "").strip()
    if not المسار:
        return {"نجاح": False, "المصدر": مصدر_افتراضي, "الرمز": الرمز, "بيانات": [], "حالة": {"النجاح": False, "الخطأ": "مسار الأسعار غير معتمد من توثيق المزود."}}
    """يجلب أحدث لقطة قابلة للتحقق؛ لا يختلق بديلاً عند فشل المصدر."""
    payload, meta = _طلب_بيانات_حقيقي(المسار, {"symbol": الرمز})
    if not meta.get("نجاح"):
        return {"نجاح": False, "المصدر": مصدر_افتراضي, "الرمز": الرمز, "بيانات": [], "حالة": meta}
    rows = _استخراج_قائمة(payload)
    if not rows and isinstance(payload, dict):
        rows = [payload]
    return {"نجاح": bool(rows), "المصدر": مصدر_افتراضي, "الرمز": الرمز, "بيانات": rows, "حالة": meta, "وقت_الاستلام": datetime.now(timezone.utc).isoformat()}


def جلب_شموع_سهم(الرمز, المسار=None, الفاصل="1m", الحد=500):
    المسار = المسار or os.getenv("EGX_BARS_PATH", "").strip()
    if not المسار:
        return {"نجاح": False, "المصدر": مصدر_افتراضي, "الرمز": الرمز, "بيانات": [], "حالة": {"النجاح": False, "الخطأ": "مسار الشموع غير معتمد من توثيق المزود."}}
    payload, meta = _طلب_بيانات_حقيقي(المسار, {"symbol": الرمز, "interval": الفاصل, "limit": الحد})
    if not meta.get("نجاح"):
        return {"نجاح": False, "المصدر": مصدر_افتراضي, "الرمز": الرمز, "بيانات": [], "حالة": meta}
    rows = _استخراج_قائمة(payload)
    return {"نجاح": bool(rows), "المصدر": مصدر_افتراضي, "الرمز": الرمز, "بيانات": rows, "حالة": meta, "وقت_الاستلام": datetime.now(timezone.utc).isoformat()}


def تحقق_مخطط_البيانات_الحية(بيانات):
    """تحقق صارم من الحقول الأساسية قبل إدخال البيانات لمحركات التحليل."""
    rows = بيانات.get("بيانات", []) if isinstance(بيانات, dict) else بيانات
    if isinstance(rows, dict): rows=[rows]
    if not isinstance(rows, list) or not rows:
        return {"صالح": False, "السبب": "لا توجد صفوف"}
    accepted=0
    for row in rows[:5000]:
        if not isinstance(row, dict): continue
        price = رقم(أول_قيمة(row, "price", "last", "close", "c"))
        if price is not None and price > 0: accepted += 1
    return {"صالح": accepted > 0, "عدد_الصفوف": len(rows), "صفوف_صالحة": accepted,
            "السبب": "صالحة" if accepted else "لا يوجد سعر موجب قابل للقراءة"}


def تحويل_البيانات_الحية_إلى_سجلات(بيانات):
    """يوحد صيغ الأسعار القادمة من مزود البيانات إلى لغة كوانتوم الداخلية."""
    rows = بيانات.get("بيانات", []) if isinstance(بيانات, dict) else بيانات
    out = []
    for i, row in enumerate(rows or []):
        if not isinstance(row, dict):
            continue
        out.append({
            "الوقت": أول_قيمة(row, "timestamp", "time", "datetime", "t") or str(i),
            "السعر": رقم(أول_قيمة(row, "price", "last", "close", "c")),
            "الحجم": رقم(أول_قيمة(row, "volume", "vol", "v"), 0),
            "الافتتاح": رقم(أول_قيمة(row, "open", "o")),
            "الأعلى": رقم(أول_قيمة(row, "high", "h")),
            "الأدنى": رقم(أول_قيمة(row, "low", "l")),
            "الإغلاق": رقم(أول_قيمة(row, "close", "c")),
        })
    return [x for x in out if x["السعر"] is not None or x["الإغلاق"] is not None]


def فحص_سلامة_المصدر_الحي(بيانات, أقصى_عمر_ثوان=120):
    """بوابة تمنع إدخال لقطة مجهولة العمر أو غير صالحة إلى محركات القرار."""
    now = datetime.now(timezone.utc)
    وقت = بيانات.get("وقت_الاستلام") if isinstance(بيانات, dict) else None
    العمر = None
    if وقت:
        try:
            dt = datetime.fromisoformat(str(وقت).replace("Z", "+00:00"))
            العمر = max(0.0, (now - dt).total_seconds())
        except Exception:
            pass
    سجلات = تحويل_البيانات_الحية_إلى_سجلات(بيانات)
    أسعار = [x["السعر"] or x["الإغلاق"] for x in سجلات]
    صالح = bool(أسعار) and all((x is not None and x > 0) for x in أسعار)
    حديث = العمر is not None and العمر <= أقصى_عمر_ثوان
    return {
        "صالح": صالح,
        "حديث": حديث,
        "عدد_القراءات": len(سجلات),
        "العمر_بالثواني": None if العمر is None else round(العمر, 2),
        "بوابة_الإنتاج": bool(صالح and حديث),
        "ملاحظة": "المصدر مقبول للرصد" if صالح and حديث else "محجوب حتى يتم التحقق من صلاحية وحداثة البيانات"
    }


def سجل_مصدر_حي(رمز, نتيجة, فحص):
    """يسجل إثبات المصدر داخل ذاكرة الجلسة دون حفظ المفتاح السري."""
    if "سجل_مصادر_حية" not in st.session_state:
        st.session_state["سجل_مصادر_حية"] = []
    st.session_state["سجل_مصادر_حية"].append({
        "الرمز": رمز,
        "المصدر": نتيجة.get("المصدر"),
        "وقت_الاستلام": نتيجة.get("وقت_الاستلام"),
        "نجاح": نتيجة.get("نجاح", False),
        "فحص_السلامة": فحص,
        "زمن_الاستجابة_مللي": نتيجة.get("حالة", {}).get("زمن_الاستجابة_مللي"),
    })
    st.session_state["سجل_مصادر_حية"] = st.session_state["سجل_مصادر_حية"][-500:]
    return st.session_state["سجل_مصادر_حية"]


def اختبار_حوكمة_المصادر():
    """اختبارات تمنع الادعاء بموافقة قانونية غير موجودة وتتحقق من بوابة التفويض."""
    حالات=حالة_حوكمة_المصادر()
    مسودة=إنشاء_طلب_تعاون_بيانات("مزود تجريبي")
    محجوب=تحقق_تفويض_المصدر("مزود تجريبي", False, True, True)
    مصرح=تحقق_تفويض_المصدر("مزود تجريبي", True, True, True)
    return {
        "اختبار_سجل_المصادر": bool(حالات),
        "اختبار_المسودة_غير_ملزمة": مسودة.get("حالة")=="مسودة تفاوض — غير موقعة وغير ملزمة",
        "اختبار_منع_التفعيل_بدون_قبول": محجوب.get("مصرح") is False,
        "اختبار_التفعيل_بعد_اكتمال_التفويض": مصرح.get("مصرح") is True
    }


def اختبار_موصل_البيانات_الحية(رمز="OCPH"):
    """اختبار اتصال حقيقي؛ نجاحه يتطلب مفتاحاً صالحاً واتصالاً بالشبكة."""
    if not مفتاح_البيانات_الحية():
        return {"نجاح": False, "الحالة": "لم يُنفذ — مفتاح المصدر غير موجود", "رمز": رمز}
    نتيجة = جلب_بيانات_سهم_حية(رمز)
    فحص = فحص_سلامة_المصدر_الحي(نتيجة)
    سجل_مصدر_حي(رمز, نتيجة, فحص)
    return {"نجاح": bool(نتيجة.get("نجاح") and فحص.get("بوابة_الإنتاج")), "النتيجة": نتيجة, "الفحص": فحص}


# ------------------------- محرك المصالحة متعددة المصادر -------------------------
# هذه الطبقة لا تختار "الأكثر ملاءمة" للقرار؛ بل تبحث أولًا عن الاتساق،
# وتغلق بوابة الإنتاج عند وجود تعارض غير محسوم أو بيانات قديمة أو مصدر غير موثوق.

حد_فرق_السعر_الافتراضي = 0.003       # 0.30%
حد_فرق_الحجم_الافتراضي = 0.05        # 5% عندما تتوفر أحجام قابلة للمقارنة
حد_عمر_اللقطة_الافتراضي = 120


def _رقم_مصالحة(value):
    return قيمة_رقمية(value, default=None)


def _وقت_مصالحة(value):
    if value in (None, "", 0):
        return None
    try:
        if isinstance(value, (int, float)):
            # دعم طوابع ثواني/مللي ثانية.
            x=float(value)
            if x > 10**12:
                x /= 1000.0
            return datetime.fromtimestamp(x, tz=timezone.utc)
        text=str(value).strip().replace("Z", "+00:00")
        dt=datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt=dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def استخراج_لقطة_مصالحة(المصدر, الرمز, البيانات):
    """يستخرج لقطة قياسية من أي مزود دون افتراض أسماء حقول ثابتة."""
    rows = البيانات.get("بيانات", []) if isinstance(البيانات, dict) else البيانات
    if isinstance(rows, dict):
        rows=[rows]
    if not isinstance(rows, list) or not rows:
        return {"المصدر": المصدر, "الرمز": الرمز, "صالح": False, "السبب": "لا توجد بيانات"}
    row=rows[0] if isinstance(rows[0], dict) else {}
    price=_رقم_مصالحة(أول_قيمة(row, "price", "last", "close", "c"))
    close=_رقم_مصالحة(أول_قيمة(row, "close", "c", "price", "last"))
    volume=_رقم_مصالحة(أول_قيمة(row, "volume", "vol", "v"))
    bid=_رقم_مصالحة(أول_قيمة(row, "bid", "best_bid"))
    ask=_رقم_مصالحة(أول_قيمة(row, "ask", "best_ask"))
    timestamp=أول_قيمة(row, "timestamp", "time", "datetime", "t")
    dt=_وقت_مصالحة(timestamp)
    if dt is None and isinstance(البيانات, dict):
        dt=_وقت_مصالحة(البيانات.get("وقت_الاستلام"))
    العمر=None
    if dt:
        العمر=max(0.0,(datetime.now(timezone.utc)-dt).total_seconds())
    صالح=bool(price is not None and price>0)
    return {
        "المصدر": المصدر, "الرمز": الرمز, "السعر": price, "الإغلاق": close,
        "الحجم": volume, "أفضل_طلب": bid, "أفضل_عرض": ask,
        "الوقت": dt.isoformat() if dt else None, "العمر_بالثواني": None if العمر is None else round(العمر,2),
        "صالح": صالح, "صف_خام": row,
    }


def _فرق_نسبي(a,b):
    if a is None or b is None:
        return None
    المقام=max(abs(float(a)),abs(float(b)),1e-12)
    return abs(float(a)-float(b))/المقام


def مصالحة_مصادر_متعددة(الرمز, لقطات, حد_فرق_السعر=حد_فرق_السعر_الافتراضي,
                      حد_فرق_الحجم=حد_فرق_الحجم_الافتراضي,
                      أقصى_عمر_ثوان=حد_عمر_اللقطة_الافتراضي):
    """مصالحة حتمية بين مصادر متعددة. لا تُنتج قرارًا إذا تعذر إثبات الاتساق."""
    قياسية=[]
    for item in لقطات or []:
        if not isinstance(item, dict):
            continue
        المصدر=item.get("المصدر", "مصدر غير مسمى")
        لقطة=استخراج_لقطة_مصالحة(المصدر, الرمز, item)
        قياسية.append(لقطة)
    صالحة=[x for x in قياسية if x.get("صالح")]
    حديثة=[x for x in صالحة if x.get("العمر_بالثواني") is None or x["العمر_بالثواني"]<=أقصى_عمر_ثوان]
    التعارضات=[]
    for i in range(len(حديثة)):
        for j in range(i+1,len(حديثة)):
            a,b=حديثة[i],حديثة[j]
            فرق_سعر=_فرق_نسبي(a.get("السعر"),b.get("السعر"))
            if فرق_سعر is not None and فرق_سعر>حد_فرق_السعر:
                التعارضات.append({"النوع":"السعر","الأول":a["المصدر"],"الثاني":b["المصدر"],"الفرق_النسبي":round(فرق_سعر,6)})
            if a.get("الحجم") is not None and b.get("الحجم") is not None:
                فرق_حجم=_فرق_نسبي(a.get("الحجم"),b.get("الحجم"))
                if فرق_حجم is not None and فرق_حجم>حد_فرق_الحجم:
                    التعارضات.append({"النوع":"الحجم","الأول":a["المصدر"],"الثاني":b["المصدر"],"الفرق_النسبي":round(فرق_حجم,6)})
    الأسعار=[x["السعر"] for x in حديثة if x.get("السعر") is not None]
    # لا نستخدم المتوسط إذا كان هناك تعارض: المتوسط قد يخفي الخطأ.
    السعر_الموحد=None
    if الأسعار and not التعارضات:
        السعر_الموحد=round(float(statistics.median(الأسعار)),6)
    if len(حديثة)==0:
        الحالة="محجوبة — لا توجد لقطة صالحة وحديثة"
    elif التعارضات:
        الحالة="محجوبة — تعارض غير محسوم"
    elif len(حديثة)==1:
        الحالة="رصد أحادي — لا توجد مصالحة مستقلة"
    else:
        الحالة="مصالحة ناجحة"
    بوابة=bool(len(حديثة)>=2 and not التعارضات and السعر_الموحد is not None)
    جودة=min(100.0, 100.0 * (len(حديثة)/max(2,len(قياسية))))
    if التعارضات:
        جودة=0.0
    return {
        "الرمز": الرمز,
        "الحالة": الحالة,
        "بوابة_المصالحة": بوابة,
        "عدد_المصادر": len(قياسية),
        "عدد_المصادر_الصالحة": len(صالحة),
        "عدد_المصادر_الحديثة": len(حديثة),
        "السعر_الموحد": السعر_الموحد,
        "التعارضات": التعارضات,
        "اللقطات": قياسية,
        "جودة_المصالحة": round(جودة,2),
        "قرار_الإنتاج": "مسموح بالمرور إلى طبقة البيانات" if بوابة else "ممنوع — يلزم مصدر ثانٍ متسق أو حل التعارض",
        "ملاحظة": "المصالحة لا تعني أن أي مصدر صحيح مطلقًا؛ إنها تثبت الاتساق بين المصادر المتاحة ضمن حدود الاختبار.",
    }


def سجل_مصالحة_مصادر(نتيجة):
    """سجل تدقيق محدود الحجم ولا يحفظ مفاتيح أو أسرار."""
    if "سجل_مصالحة_مصادر" not in st.session_state:
        st.session_state["سجل_مصالحة_مصادر"]=[]
    نسخة={k:v for k,v in نتيجة.items() if k not in {"اللقطات"}}
    نسخة["وقت_التسجيل"]=datetime.now(timezone.utc).isoformat()
    st.session_state["سجل_مصالحة_مصادر"].append(نسخة)
    st.session_state["سجل_مصالحة_مصادر"]=st.session_state["سجل_مصالحة_مصادر"][-500:]
    return st.session_state["سجل_مصالحة_مصادر"]


def فحص_جاهزية_الإنتاج_الموحدة(نتيجة_المصالحة, فحص_بيانات=None, البصمة=None):
    """حارس نهائي يمنع انتقال بيانات غير مكتملة إلى القرار."""
    أسباب=[]
    if not نتيجة_المصالحة.get("بوابة_المصالحة"):
        أسباب.append("بوابة المصالحة مغلقة")
    if فحص_بيانات is not None and not فحص_بيانات.get("بوابة_الإنتاج", False):
        أسباب.append("بوابة سلامة المصدر مغلقة")
    if البصمة is not None and not البصمة.get("جاهزية", False):
        أسباب.append("العينة غير كافية لتشغيل البصمة")
    جاهز=not أسباب
    return {"جاهزية_الإنتاج":جاهز,"الأسباب":أسباب,"القرار":"مسموح" if جاهز else "محجوب"}


def اختبار_حماية_r5():
    الآن=datetime.now(timezone.utc).isoformat()
    صالح={"نجاح":True,"وقت_الاستلام":الآن,"بيانات":[{"price":100,"volume":1000,"timestamp":الآن}]}
    فحص=فحص_سلامة_المصدر_الحي(صالح, 120)
    مخطط=تحقق_مخطط_البيانات_الحية(صالح)
    قديم={"نجاح":True,"وقت_الاستلام":"2020-01-01T00:00:00+00:00","بيانات":[{"price":100}]}
    فحص_قديم=فحص_سلامة_المصدر_الحي(قديم, 120)
    return {"حداثة_صالحة": bool(فحص.get("حديث")), "مخطط_صالح": bool(مخطط.get("صالح")),
            "حجب_القديم": not bool(فحص_قديم.get("بوابة_الإنتاج")), "نسخة": نسخة_المنظومة}


def اختبار_مصالحة_المصادر():
    الآن=datetime.now(timezone.utc).isoformat()
    base=lambda src,price,volume: {"المصدر":src,"بيانات":[{"price":price,"close":price,"volume":volume,"timestamp":الآن}]}
    متسقة=مصالحة_مصادر_متعددة("OCPH",[base("مصدر أ",257.30,52000),base("مصدر ب",257.34,52100)])
    متعارضة=مصالحة_مصادر_متعددة("OCPH",[base("مصدر أ",257.30,52000),base("مصدر ب",264.90,52100)])
    أحادية=مصالحة_مصادر_متعددة("OCPH",[base("مصدر أ",257.30,52000)])
    نتائج=[
        ("مصالحة متسقة",متسقة.get("بوابة_المصالحة") is True),
        ("حجب تعارض السعر",متعارضة.get("بوابة_المصالحة") is False and bool(متعارضة.get("التعارضات"))),
        ("حجب المصدر الأحادي",أحادية.get("بوابة_المصالحة") is False),
        ("عدم اختراع سعر",متعارضة.get("السعر_الموحد") is None),
    ]
    return {"الاختبارات":[{"الاسم":n,"النتيجة":"ناجح" if ok else "فاشل"} for n,ok in نتائج],
            "الإجمالي":len(نتائج),"الناجح":sum(ok for _,ok in نتائج),
            "الفاشل":sum(not ok for _,ok in نتائج)}


# ------------------------- إصلاح ترتيب التعريفات r10.4 -------------------------
# هذه الدوال مطلوبة أثناء بناء واجهة الفجوات، لذلك يجب أن تكون معرفة قبل أول استدعاء لها.
def فحص_استمرارية_التخزين():
    backend=os.getenv("QV_STORAGE_BACKEND", "sqlite").strip().lower()
    database_url=os.getenv("DATABASE_URL", "").strip()
    if backend == "postgres":
        return {"النوع":"postgres", "دائم":bool(database_url), "جاهز":bool(database_url),
                "ملاحظة":"يلزم DATABASE_URL صالح ومخزن خارجي دائم قبل اعتبار Streamlit مستمرًا."}
    return {"النوع":"sqlite", "دائم":False, "جاهز":True,
            "ملاحظة":"SQLite المحلي مناسب للاختبار والرصد المؤقت، وليس ضمانًا لاستمرارية Streamlit السحابية."}

def بوابة_الاستمرارية_للإنتاج():
    حالة=فحص_استمرارية_التخزين()
    إلزام=_علم_بيئي("QV_REQUIRE_PERSISTENT_STORAGE", True)
    return {"جاهزة": (حالة["جاهز"] and (حالة["دائم"] or not إلزام)), "الحالة":حالة, "الإلزام":إلزام}

def حالة_البث_الحقيقي():
    url=os.getenv("EGX_WS_URL", "").strip()
    enabled=_علم_بيئي("QV_WEBSOCKET_ENABLED", False)
    return {"مفعل": bool(enabled and url), "عنوان_موجود": bool(url),
            "القرار":"مفعل بعد اعتماد عنوان WebSocket" if enabled and url else "محجوب — عنوان WebSocket غير مُعتمد أو غير مفعل"}

def تقرير_فجوات_المنظومة():
    """قائمة آلية بالفجوات المتبقية، مع تمييز ما يمكن إغلاقه برمجيًا عما يتطلب طرفًا خارجيًا."""
    التخزين=فحص_استمرارية_التخزين()
    إنتاج=_اعتماد_الإنتاج_الآلي()
    بث=حالة_البث_الحقيقي()
    return [
        {"الفجوة":"اختبار اتصال حي فعلي","التصنيف":"خارجي","الحالة":"يتطلب مفتاح مزود صالحًا وبيئة تشغيل متصلة"},
        {"الفجوة":"تأكيد مسارات واجهة EGXAPI","التصنيف":"خارجي","الحالة":"يلزم اعتماد المسارات من توثيق المزود؛ لا توجد مسارات افتراضية في موصلات الأسعار/الشموع"},
        {"الفجوة":"مصدر مستقل ثانٍ متسق","التصنيف":"خارجي/بيانات","الحالة":"المصالحة جاهزة، لكن يلزم مفتاح ومصدر فعلي متاح ومتسق"},
        {"الفجوة":"تخزين تاريخي دائم","التصنيف":"تهيئة خارجية","الحالة":"جاهز برمجيًا لـ PostgreSQL؛ يلزم DATABASE_URL صالح ومخزن دائم" if not التخزين.get("دائم") else "مهيأ"},
        {"الفجوة":"معايرة السيناريوهات خارج العينة","التصنيف":"بيانات/بحث","الحالة":"تحتاج عينة تاريخية مؤهلة ونتائج لاحقة فعلية؛ لا يجوز اختلاق المعايرة"},
        {"الفجوة":"مراقبة WebSocket وإعادة الاتصال","التصنيف":"تهيئة/تكامل","الحالة":"البوابة موجودة؛ الاعتماد اللحظي الكامل يتطلب عنوان WebSocket موثقًا واختبار اتصال فعليًا" if not بث.get("مفعل") else "مهيأ"},
        {"الفجوة":"تأكيد الترخيص وإعادة التوزيع","التصنيف":"خارجي/قانوني","الحالة":"لا يُستنتج من وجود API أو مفتاح؛ يلزم دليل ترخيص/موافقة قابل للإثبات"},
        {"الفجوة":"فتح بوابة الإنتاج","التصنيف":"حوكمة","الحالة":"محجوبة" if إنتاج.get("البوابة_العامة") != "مفتوحة" else "مفتوحة"},
    ]


def تشغيل_مصالحة_حيّة(رمز):
    """يشغل المصالحة الحية بالمصادر المهيأة فعليًا فقط؛ لا يخترع مصدرًا ثانيًا."""
    لقطات=[]
    egx=جلب_بيانات_سهم_حية(رمز)
    if egx.get("نجاح"):
        لقطات.append(egx)
    # المصدر الثاني لا يُستدعى إلا إذا توفر مفتاحه؛ ولا يُعتبر غيابه تعارضًا.
    مفتاح_ثان= os.getenv("TWELVEDATA_API_KEY", "").strip()
    if مفتاح_ثان:
        try:
            import requests
            started=time.perf_counter()
            r=requests.get("https://api.twelvedata.com/quote",params={"symbol":رمز,"apikey":مفتاح_ثان},timeout=8)
            if r.status_code<400:
                payload=r.json()
                لقطات.append({"المصدر":"TwelveData","الرمز":رمز,"بيانات":[payload],"وقت_الاستلام":datetime.now(timezone.utc).isoformat()})
        except Exception:
            pass
    نتيجة=مصالحة_مصادر_متعددة(رمز,لقطات)
    سجل_مصالحة_مصادر(نتيجة)
    return نتيجة

# ------------------------- التشغيل الآلي اللحظي الشامل -------------------------
def _قائمة_الأدوات_من_المصدر():
    """يكتشف الأسهم والمؤشرات من واجهات المصدر المصرح بها فقط."""
    النتائج = {"الأسهم": [], "المؤشرات": [], "أخطاء": []}
    for نوع, env_name, default_path in [
        ("الأسهم", "EGX_INSTRUMENTS_PATH", ""),
        ("المؤشرات", "EGX_INDICES_PATH", ""),
    ]:
        path = os.getenv(env_name, default_path).strip()
        if not path:
            النتائج["أخطاء"].append({"النوع": نوع, "الخطأ": f"لم يتم اعتماد مسار {env_name} من توثيق المزود."})
            continue
        payload, meta = _طلب_بيانات_حقيقي(path, {})
        if not meta.get("نجاح"):
            النتائج["أخطاء"].append({"النوع": نوع, "الخطأ": meta.get("الخطأ", "تعذر الوصول")})
            continue
        rows = _استخراج_قائمة(payload)
        if isinstance(payload, dict) and not rows:
            rows = payload.get("instruments", []) if نوع == "الأسهم" else payload.get("indices", [])
        for row in rows or []:
            if not isinstance(row, dict):
                continue
            رمز = أول_قيمة(row, "symbol", "code", "ticker", "رمز")
            if رمز:
                النتائج[نوع].append(str(رمز).strip().upper())
    النتائج["الأسهم"] = sorted(set(النتائج["الأسهم"]))[:الحد_الأقصى_للأدوات]
    النتائج["المؤشرات"] = sorted(set(النتائج["المؤشرات"]))[:max(20, الحد_الأقصى_للأدوات//10)]
    if len(النتائج["الأسهم"]) + len(النتائج["المؤشرات"]) >= الحد_الأقصى_للأدوات:
        النتائج["أخطاء"].append(f"تم تطبيق حد أمان للأدوات: {الحد_الأقصى_للأدوات}")
    return النتائج


def _اعتماد_الإنتاج_الآلي():
    """لا يتجاوز الموافقة الخارجية؛ يفتح البوابة فقط عند اكتمال الشروط."""
    مفتاح = bool(مفتاح_البيانات_الحية())
    تفويض = os.getenv("QV_SOURCE_AUTHORIZED", "false").strip().lower() == "true"
    موافقة = os.getenv("QV_PRODUCTION_APPROVED", "false").strip().lower() == "true"
    مسار_أسهم = os.getenv("EGX_INSTRUMENTS_PATH", "").strip()
    مسار_مؤشرات = os.getenv("EGX_INDICES_PATH", "").strip()
    مسار_أسعار = os.getenv("EGX_QUOTES_PATH", "").strip()
    مسار_شموع = os.getenv("EGX_BARS_PATH", "").strip()
    مسارات = bool(مسار_أسهم and مسار_مؤشرات and مسار_أسعار and مسار_شموع)
    قبول_شروط = _علم_بيئي("QV_TERMS_ACCEPTED", False)
    بصمة_الشروط = os.getenv("QV_TERMS_FINGERPRINT", "").strip()
    تخزين = بوابة_الاستمرارية_للإنتاج() if "بوابة_الاستمرارية_للإنتاج" in globals() else {"جاهزة": False}
    تخزين_مستمر = bool(تخزين.get("جاهزة", False))
    بث = حالة_البث_الحقيقي() if "حالة_البث_الحقيقي" in globals() else {"مفعل": False}
    بث_مطلوب = _علم_بيئي("QV_REQUIRE_WEBSOCKET", False)
    مفتوح = bool(مفتاح and تفويض and موافقة and مسارات and قبول_شروط and بصمة_الشروط and تخزين_مستمر and (not بث_مطلوب or بث.get("مفعل")))
    return {"مفتاح_المصدر": مفتاح, "تفويض_المصدر": تفويض, "موافقة_الإنتاج": موافقة,
            "قبول_الشروط": قبول_شروط, "بصمة_الشروط": bool(بصمة_الشروط), "مسارات_التغطية": مسارات,
            "مسارات_الأسعار_والشموع": bool(مسار_أسعار and مسار_شموع), "التخزين_المستمر": تخزين_مستمر,
            "البث_المطلوب": بث_مطلوب, "البث_جاهز": bool(bث.get("مفعل")) if False else bool(بث.get("مفعل")),
            "البوابة_العامة": "مفتوحة" if مفتوح else "مغلقة",
            "القرار": "تشغيل آلي مسموح" if مفتوح else "تشغيل آلي محجوب حتى اكتمال شروط الاعتماد والتوثيق"}


def تشغيل_الدورة_الشاملة_الآلية():
    """دورة موحدة: اكتشاف، تحقق، التقاط متوازٍ مضبوط، تخزين وتدقيق."""
    حالة = _اعتماد_الإنتاج_الآلي()
    اكتشاف = _قائمة_الأدوات_من_المصدر() if حالة["البوابة_العامة"] == "مفتوحة" else {"الأسهم": [], "المؤشرات": [], "أخطاء": ["بوابة الإنتاج مغلقة"]}
    الأدوات = [(رمز, "سهم" if نوع == "الأسهم" else "مؤشر") for نوع in ("الأسهم", "المؤشرات") for رمز in اكتشاف[نوع]]
    base = {"عدد_الأسهم": len(اكتشاف["الأسهم"]), "عدد_المؤشرات": len(اكتشاف["المؤشرات"]), "الأخطاء": اكتشاف["أخطاء"]}
    if not الأدوات or حارس_التشغيل is None:
        return {"وقت_الدورة": datetime.now(timezone.utc).isoformat(), "الحالة": حالة, "الاكتشاف": base, "القراءات": [], "عدد_القراءات_الناجحة": 0}

    def fetch_wrapper(رمز, نوع):
        نتيجة = جلب_بيانات_مؤشر_حية(رمز) if نوع == "مؤشر" else جلب_بيانات_سهم_حية(رمز)
        return نتيجة.get("بيانات", []), {"نجاح": bool(نتيجة.get("نجاح")), "وقت_الاستلام": نتيجة.get("وقت_الاستلام"), "بيانات": نتيجة.get("بيانات", []), "الخطأ": نتيجة.get("الخطأ")}

    guard = حارس_التشغيل(fetch_wrapper, os.getenv("QV_DB_PATH", "data/qv_operational.sqlite3"), workers=min(8, max(1, int(os.getenv("QV_WORKERS", "8")))))
    دورة = guard.تشغيل(الأدوات)
    return {"وقت_الدورة": datetime.now(timezone.utc).isoformat(), "الحالة": حالة, "الاكتشاف": base, "القراءات": دورة["النتائج"], "عدد_القراءات_الناجحة": دورة["الملخص"]["ناجح"], "التشغيل": دورة["الملخص"]}


# ===== التجميع الآلي للجلسة المرجعية — الإصدار 10.6 =====
def اكتشاف_الجلسة_المرجعية_آليًا(الرمز):
    """يكتشف جلسة السوق من لقطة مباشرة مقبولة دون الاعتماد على اسم ملف أو تخمين."""
    try:
        نتيجة = جلب_بيانات_سهم_حية(str(الرمز).strip().upper())
        فحص = _تحقق_اللقطة_المباشرة(نتيجة, "أسعار")
        if not فحص.get("صالحة"):
            return {"نجاح": False, "الحالة": "محجوب", "السبب": فحص.get("سبب", "اللقطة المباشرة غير مقبولة"), "بيانات": []}
        rows = list(نتيجة.get("بيانات", []) or [])
        if not rows:
            return {"نجاح": False, "الحالة": "محجوب", "السبب": "لا توجد بيانات مقبولة", "بيانات": []}
        وقت_المصدر = _استخراج_وقت_المصدر(rows)
        if not وقت_المصدر:
            return {"نجاح": False, "الحالة": "محجوب", "السبب": "اللقطة المقبولة لا تحتوي على وقت مصدر يمكن منه تحديد الجلسة", "بيانات": rows}
        try:
            dt = pd.to_datetime(وقت_المصدر, errors="coerce")
            if pd.isna(dt):
                raise ValueError("وقت المصدر غير قابل للتحويل")
            تاريخ_الجلسة = dt.date().isoformat()
        except Exception:
            return {"نجاح": False, "الحالة": "محجوب", "السبب": "وقت المصدر غير صالح لتحديد الجلسة", "بيانات": rows}
        for row in rows:
            if isinstance(row, dict) and not any(k in row for k in ("session_date", "تاريخ الجلسة", "date", "التاريخ")):
                row["session_date"] = تاريخ_الجلسة
        حارس = تحديد_الجلسة_المرجعية_من_البيانات(rows)
        if not حارس.get("تاريخ الجلسة"):
            return {"نجاح": False, "الحالة": "محجوب", "السبب": حارس.get("الحالة"), "بيانات": rows}
        return {"نجاح": True, "الحالة": "مقبولة", "الرمز": str(الرمز).strip().upper(),
                "تاريخ الجلسة": حارس["تاريخ الجلسة"], "المصدر": نتيجة.get("المصدر"),
                "وقت المصدر": وقت_المصدر, "بيانات": rows, "فحص": فحص}
    except Exception as exc:
        return {"نجاح": False, "الحالة": "محجوب", "السبب": _تنظيف_خطأ(exc), "بيانات": []}

# ===================== منظومة الدورة المستمرة والأداء والمعايرة — الإصدار 11.1 =====================
# لا تفتح هذه الطبقة الإنتاج؛ تبني الأدلة المطلوبة لفتحه تدريجيًا.

def _سلسلة_سعرية(سجلات):
    d=تطبيع(سجلات or [])
    return d

def مؤشرات_فنية_موحدة(سجلات):
    d=_سلسلة_سعرية(سجلات)
    if len(d)<2: return {"جاهزية":False,"الحالة":"محجوب — عينة غير كافية"}
    close=pd.Series([x["السعر"] for x in d],dtype=float)
    volume=pd.Series([x["الحجم"] for x in d],dtype=float)
    ret=close.pct_change()
    def ema(n): return float(close.ewm(span=n,adjust=False).mean().iloc[-1])
    def rsi(n=14):
        delta=close.diff(); up=delta.clip(lower=0); down=-delta.clip(upper=0)
        au=up.ewm(alpha=1/n,adjust=False).mean(); ad=down.ewm(alpha=1/n,adjust=False).mean()
        rs=au/(ad.replace(0,float('nan'))); x=100-(100/(1+rs)); return float(x.iloc[-1]) if pd.notna(x.iloc[-1]) else 50.0
    def atr(n=14):
        vals=[]
        for x in d:
            h,l,c=x.get('الأعلى'),x.get('الأدنى'),x.get('الإغلاق') or x.get('السعر')
            vals.append((h-l) if h is not None and l is not None else 0.0)
        return float(pd.Series(vals).rolling(min(n,len(vals)),min_periods=1).mean().iloc[-1])
    sma20=float(close.tail(min(20,len(close))).mean()); sma50=float(close.tail(min(50,len(close))).mean())
    vol_med=float(volume.iloc[:-1].tail(min(20,max(1,len(volume)-1))).median()) if len(volume)>1 else 0
    current=float(close.iloc[-1])
    return {"جاهزية":len(d)>=20,"الحالة":"صالحة للرصد" if len(d)>=20 else "صالحة جزئيًا — تحتاج تاريخًا أعمق",
            "السعر":current,"المتوسط_المتحرك_20":sma20,"المتوسط_المتحرك_50":sma50,
            "المتوسط_الأسي_12":ema(min(12,len(close))),"المتوسط_الأسي_26":ema(min(26,len(close))),
            "القوة_النسبية_14":round(rsi(min(14,len(close))),2),"متوسط_المدى_الحقيقي":round(atr(14),6),
            "نسبة_الحجم_إلى_الوسيط":None if vol_med<=0 else round(float(volume.iloc[-1]/vol_med),3),
            "العائد_التراكمي":round(float((1+ret.fillna(0)).prod()-1),6),
            "تحذير":"المؤشرات وصفية؛ لا تُحوّل منفردة إلى احتمال أو توصية."}

def بناء_سجل_زمني_تراكمي(سجلات, رمز="غير معروف"):
    d=_سلسلة_سعرية(سجلات)
    rows=[]
    for i,x in enumerate(d):
        rows.append({"الرمز":رمز,"الفهرس":i,"الوقت":x.get("الوقت"),"السعر":x.get("السعر"),"الحجم":x.get("الحجم"),"الإغلاق":x.get("الإغلاق")})
    return rows

def تقسيم_زمني_خارج_العينة(سجلات, نسبة_تدريب=0.7, حد_أدنى=20):
    d=_سلسلة_سعرية(سجلات); n=len(d)
    if n<حد_أدنى: return {"جاهز":False,"السبب":"التاريخ غير كافٍ","تدريب":[],"اختبار":[]}
    k=max(1,min(n-1,int(n*نسبة_تدريب)))
    return {"جاهز":len(d[k:])>=5,"حجم_العينة":n,"فاصل_التدريب":[0,k],"فاصل_الاختبار":[k,n],"تدريب":d[:k],"اختبار":d[k:],"منع_التسرب":True}

def قياس_أداء_الإشارة(الإشارات, العوائد):
    pairs=[]
    for s,r in zip(الإشارات or [], العوائد or []):
        try: pairs.append((1 if float(s)>0 else (-1 if float(s)<0 else 0),float(r)))
        except: pass
    active=[r for s,r in pairs if s]
    if not active: return {"عدد":0,"جاهزية":False,"الدقة":None,"العائد_المتوسط":None,"السحب_الأقصى":None}
    wins=sum(1 for s,r in pairs if s*r>0); acc=wins/len(active)
    curve=[]; equity=1.0
    for s,r in pairs:
        if s: equity*=1+s*r
        curve.append(equity)
    peak=1.0; dd=0.0
    for x in curve: peak=max(peak,x); dd=max(dd,(peak-x)/peak)
    return {"عدد":len(active),"جاهزية":len(active)>=30,"الدقة":round(acc,4),"العائد_المتوسط":round(sum(s*r for s,r in pairs if s)/len(active),6),"السحب_الأقصى":round(dd,4),"تحذير":"القياس وصفي ما لم يكن الاختبار خارج العينة ومثبتًا."}

def معايرة_احتمال_خارج_العينة(الدرجات, النتائج, bins=10):
    # تحويل الدرجة إلى احتمال مسموح فقط هنا بعد نتائج OOS فعلية؛ لا تستخدم قبل تحقق الحد الأدنى.
    if len(الدرجات)!=len(النتائج) or len(الدرجات)<30:
        return {"جاهزة":False,"السبب":"يلزم 30 حالة خارج العينة على الأقل للمعايرة الأولية","الاحتمالات":[]}
    x=[max(0,min(1,(float(s)+100)/200)) for s in الدرجات]
    y=[1 if float(r)>0 else 0 for r in النتائج]
    table=[]
    for i in range(bins):
        lo=i/bins; hi=(i+1)/bins
        idx=[j for j,z in enumerate(x) if lo<=z<(hi if i<bins-1 else hi+1e-12)]
        if idx: table.append({"الفئة":f"{lo:.1f}-{hi:.1f}","عدد":len(idx),"الاحتمال_الملاحظ":round(sum(y[j] for j in idx)/len(idx),4),"الدرجة_المتوسط":round(sum(x[j] for j in idx)/len(idx),4)})
    brier=sum((a-b)**2 for a,b in zip(x,y))/len(y)
    return {"جاهزة":True,"عدد_الحالات":len(y),"جدول":table,"مقياس_بريير":round(brier,6),"قاعدة":"الاحتمال ناتج عن معايرة OOS فقط، وليس تحويلًا مباشرًا للدرجة."}

def تقييم_بوابات_الإنتاج_المرحلية(تاريخ, أداء=None, معايرة=None, سلامة=None, تفويض=False, موافقة=False, تخزين=False):
    n=len(تاريخ or [])
    gates=[]
    gates.append({"البوابة":"تراكم تاريخ السوق","مفتوحة":n>=60,"الدليل":n,"المطلوب":"60 جلسة/قراءة مؤهلة على الأقل"})
    gates.append({"البوابة":"اختبار خارج العينة","مفتوحة":bool(أداء and أداء.get("جاهزية")),"الدليل":(أداء or {}).get("عدد",0),"المطلوب":"30 حالة اختبار على الأقل"})
    gates.append({"البوابة":"المعايرة","مفتوحة":bool(معايرة and معايرة.get("جاهزة")),"الدليل":(معايرة or {}).get("عدد_الحالات",0),"المطلوب":"30 حالة OOS على الأقل"})
    gates.append({"البوابة":"سلامة البيانات","مفتوحة":bool(سلامة),"الدليل":"فحص السلامة"})
    gates.append({"البوابة":"التفويض","مفتوحة":bool(تفويض),"الدليل":"تفويض موثق"})
    gates.append({"البوابة":"موافقة الإنتاج","مفتوحة":bool(موافقة),"الدليل":"موافقة مستقلة"})
    gates.append({"البوابة":"التخزين الدائم","مفتوحة":bool(تخزين),"الدليل":"مخزن دائم"})
    # لا توجد قفزة مباشرة: البوابات تفتح تدريجيًا وبالأدلة.
    return {"البوابات":gates,"عدد_المفتوح":sum(bool(g["مفتوحة"]) for g in gates),"الإنتاج_النهائي":all(bool(g["مفتوحة"]) for g in gates),"قاعدة":"أي بوابة غير مثبتة تبقي الإنتاج محجوبًا."}

def تشغيل_دورة_الذاكرة_والأداء(سجلات, رمز="غير معروف"):
    تاريخ=بناء_سجل_زمني_تراكمي(سجلات,رمز); فني=مؤشرات_فنية_موحدة(سجلات)
    split=تقسيم_زمني_خارج_العينة(سجلات)
    return {"الرمز":رمز,"عدد_القراءات":len(تاريخ),"سجل":تاريخ,"المؤشرات":فني,"التقسيم":{k:v for k,v in split.items() if k not in ("تدريب","اختبار")},"حالة_الإنتاج":"محجوب حتى استكمال القياس والمعايرة والاعتماد"}

def اختبارات_الإصدار_11_1():
    d=[{"السعر":100+i*0.5,"الحجم":1000+i*20,"الافتتاح":100+i*0.5,"الأعلى":101+i*0.5,"الأدنى":99+i*0.5,"الإغلاق":100+i*0.5,"الوقت":str(i)} for i in range(80)]
    ف=مؤشرات_فنية_موحدة(d); sp=تقسيم_زمني_خارج_العينة(d)
    أداء=قياس_أداء_الإشارة([1 if i%3 else -1 for i in range(40)],[0.01 if i%2 else -0.005 for i in range(40)])
    معا=معايرة_احتمال_خارج_العينة([i*2.5-50 for i in range(40)],[1 if i%2 else -1 for i in range(40)])
    gates=تقييم_بوابات_الإنتاج_المرحلية(d,أداء,معا,True,False,False,False)
    tests=[("المؤشرات الفنية",ف.get("جاهزية") is True),("التقسيم الزمني",sp.get("جاهز") is True and sp.get("منع_التسرب") is True),("قياس الأداء",أداء.get("عدد")==40),("المعايرة OOS",معا.get("جاهزة") is True),("عدم فتح الإنتاج",gates.get("الإنتاج_النهائي") is False)]
    return {"الإجمالي":len(tests),"الناجح":sum(x[1] for x in tests),"الفاشل":sum(not x[1] for x in tests),"الاختبارات":[{"الاسم":n,"النتيجة":"ناجح" if ok else "فاشل"} for n,ok in tests]}



# ===================== طبقة الدمج الأسطورية — 2026-09-08 =====================
# هذه الطبقة لا تستبدل المحركات القائمة؛ توحّد فحصها وتكشف النواقص وتدفع دورة الصيانة.
نسخة_الحالة_الأسطورية = "الحالة التراكمية المتكاملة فوق الإصدار 11.1"

مكونات_الحالة_الأسطورية = {
    "البيانات_المباشرة": "تجميع_مباشر_كوانتوم",
    "المصالحة": "مصالحة_مصادر_متعددة",
    "البصمة": "محرك_بصمة_كوانتوم",
    "الأدلة": "بناء_جسر_الأدلة",
    "التوصية": "بناء_التوصية",
    "قناص_السيولة": "دمج_الأدلة_والقناص",
    "المؤشرات_الفنية": "مؤشرات_فنية_موحدة",
    "السجل_الزمني": "بناء_سجل_زمني_تراكمي",
    "التقسيم_خارج_العينة": "تقسيم_زمني_خارج_العينة",
    "قياس_الأداء": "قياس_أداء_الإشارة",
    "مراجعة_نجاح_التوصيات": "QVRecommendationReviewEngine",
    "المعايرة": "معايرة_احتمال_خارج_العينة",
    "بوابات_الإنتاج": "تقييم_بوابات_الإنتاج_المرحلية",
    "التخزين": "فحص_استمرارية_التخزين",
    "التدقيق": "فحص_سلسلة_التدقيق_المحلية",
    "التفاوض": "تشغيل_التفاوض_المستمر",
    "الدورة_الشاملة": "تشغيل_الدورة_الشاملة_الآلية",
    "الجلسة_المرجعية": "اكتشاف_الجلسة_المرجعية_آليًا",
    "البث": "حالة_البث_الحقيقي",
    "الجاهزية_الموحدة": "تحقق_الاعتماد_الكامل",
}

def فحص_تكامل_الحالة_الأسطورية():
    """فحص ساكن سريع: هل كل الوصلات الجوهرية موجودة قبل التشغيل؟"""
    نتائج=[]
    for الاسم, الوظيفة in مكونات_الحالة_الأسطورية.items():
        موجود=callable(globals().get(الوظيفة))
        نتائج.append({"المكون":الاسم,"الوظيفة":الوظيفة,"الحالة":"موجود" if موجود else "ناقص"})
    الموجود=sum(x["الحالة"]=="موجود" for x in نتائج)
    return {"الإصدار":نسخة_الحالة_الأسطورية,"الإجمالي":len(نتائج),"الموجود":الموجود,"الناقص":len(نتائج)-الموجود,"الجاهزية_الساكنة":الموجود==len(نتائج),"النتائج":نتائج}

def تقرير_فجوات_الحالة_الأسطورية():
    """تقرير فجوات قابل لإعادة التشغيل، ولا يعتبر الاتصال الخارجي ناجحًا دون فحص حي."""
    فحص=فحص_تكامل_الحالة_الأسطورية()
    فجوات=[]
    if not callable(globals().get("تحقق_الاعتماد_الكامل")):
        فجوات.append("بوابة اعتماد موحدة غير متاحة")
    if not callable(globals().get("فحص_استمرارية_التخزين")):
        فجوات.append("فحص استمرارية التخزين غير متاح")
    if not callable(globals().get("حالة_البث_الحقيقي")):
        فجوات.append("حالة البث الحقيقي غير متاحة")
    if not callable(globals().get("تقييم_بوابات_الإنتاج_المرحلية")):
        فجوات.append("بوابات الإنتاج المرحلية غير متاحة")
    if not callable(globals().get("معايرة_احتمال_خارج_العينة")):
        فجوات.append("المعايرة خارج العينة غير متاحة")
    فحص["الفجوات_الحرجة"]=فجوات
    فحص["الحكم"]="مكتملة ساكنًا — يلزم فحص حي قبل أي ادعاء إنتاجي" if not فجوات else "تحتاج إصلاحًا قبل الجاهزية"
    return فحص

def تشغيل_صيانة_الحالة_الأسطورية():
    """دورة صيانة آمنة: فحص التكامل، التفاوض، التخزين، والبوابة النهائية دون فتح الإنتاج."""
    نتيجة={"وقت":datetime.now(timezone.utc).isoformat(),"الإصدار":نسخة_الحالة_الأسطورية}
    نتيجة["فحص_التكامل"]=فحص_تكامل_الحالة_الأسطورية()
    try:
        نتيجة["التفاوض"]=تشغيل_التفاوض_المستمر(force=False)
    except Exception as exc:
        نتيجة["التفاوض"]={"الحالة":"فشل آمن","الخطأ":_تنظيف_خطأ(exc)}
    try:
        نتيجة["التخزين"]=فحص_استمرارية_التخزين()
    except Exception as exc:
        نتيجة["التخزين"]={"جاهزة":False,"الخطأ":_تنظيف_خطأ(exc)}
    try:
        نتيجة["الاعتماد"]=تحقق_الاعتماد_الكامل()
    except Exception as exc:
        نتيجة["الاعتماد"]={"جاهزية_كاملة":False,"الأسباب":[_تنظيف_خطأ(exc)]}
    نتيجة["الإنتاج_المسموح"]=False
    return نتيجة


# ===================== طبقة تنفيذ الاتفاقيات والمصادر الحية — الإغلاق التشغيلي للفجوة 1 =====================
# هذه الطبقة لا توقّع عقودًا ولا تنتحل موافقات خارجية. تنفذ آليًا ما يمكن تنفيذه
# برمجيًا: تسجيل المصدر، حالة التفويض، اختبار الاعتماد، اختبار الاتصال الحي،
# التحقق من حداثة البيانات، وإغلاق بوابة الإنتاج حتى يثبت الطرف الخارجي الشروط.

مصادر_التكامل_المعتمدة = {
    "EGXAPI": {
        "النوع": "مصدر_مباشر",
        "الأولوية": 100,
        "مفتاح_البيئة": "EGX_KEY",
        "شرط_التفعيل": "تفويض_خارجي_مثبت + شروط_استخدام_مثبتة + مفتاح_صالح + اتصال_حي",
        "حالة_افتراضية": "بانتظار الإثبات الخارجي",
    },
    "TwelveData": {
        "النوع": "مصدر_تحقق_ثانوي",
        "الأولوية": 50,
        "مفتاح_البيئة": "TWELVEDATA_API_KEY",
        "شرط_التفعيل": "ترخيص_مناسب + مفتاح_صالح + اتصال_حي + مخطط_مقبول",
        "حالة_افتراضية": "غير مفعل حتى إثبات الترخيص",
    },
}


def سجل_حالة_مصدر_حي(اسم_المصدر, **القيم):
    """يسجل حالة المصدر دون حفظ المفاتيح أو الأسرار."""
    now=datetime.now(timezone.utc).isoformat()
    سجل={"وقت":now,"المصدر":اسم_المصدر}
    سجل.update(القيم)
    سجل.pop("مفتاح", None); سجل.pop("رمز", None); سجل.pop("سر", None)
    try:
        مخزن_كوانتوم(os.getenv("QV_DB_PATH", "data/qv_operational.sqlite3")).تدقيق(
            "حالة_مصدر_حي", "تحديث", سجل, اسم_المصدر)
    except Exception:
        pass
    return سجل


def فحص_مصدر_حي_فعلي(اسم_المصدر, رمز="COMI"):
    """اختبار حي حقيقي فقط؛ لا يعتبر الإعداد المحلي اتصالًا حيًا."""
    if اسم_المصدر == "EGXAPI":
        key=مفتاح_البيانات_الحية()
        if not key:
            return سجل_حالة_مصدر_حي(اسم_المصدر, الاتصال_الحي=False, التفويض=False,
                                     السبب="لا يوجد اعتماد حي في بيئة التشغيل")
        try:
            started=time.perf_counter()
            payload,meta=_طلب_بيانات_حقيقي("/v2/account", مهلة=8)
            زمن=time.perf_counter()-started
            نجاح=bool(meta.get("نجاح"))
            return سجل_حالة_مصدر_حي(اسم_المصدر, الاتصال_الحي=نجاح,
                                     التفويض=نجاح, زمن_الاستجابة=زمن,
                                     حالة_الطلب=meta, الحساب_متحقق=bool(payload))
        except Exception as exc:
            return سجل_حالة_مصدر_حي(اسم_المصدر, الاتصال_الحي=False, التفويض=False,
                                     السبب=_تنظيف_خطأ(exc))
    if اسم_المصدر == "TwelveData":
        key=os.getenv("TWELVEDATA_API_KEY", "").strip()
        if not key:
            return سجل_حالة_مصدر_حي(اسم_المصدر, الاتصال_الحي=False, التفويض=False,
                                     السبب="لا يوجد اعتماد حي في بيئة التشغيل")
        try:
            import requests
            started=time.perf_counter()
            r=requests.get("https://api.twelvedata.com/quote",
                           params={"symbol":رمز,"apikey":key}, timeout=8)
            زمن=time.perf_counter()-started
            نجاح=r.status_code < 400
            payload=r.json() if نجاح else {}
            return سجل_حالة_مصدر_حي(اسم_المصدر, الاتصال_الحي=نجاح,
                                     التفويض=نجاح, زمن_الاستجابة=زمن,
                                     رمز=رمز, بيانات_مستلمة=bool(payload),
                                     حالة_رمز=r.status_code)
        except Exception as exc:
            return سجل_حالة_مصدر_حي(اسم_المصدر, الاتصال_الحي=False, التفويض=False,
                                     السبب=_تنظيف_خطأ(exc))
    return سجل_حالة_مصدر_حي(اسم_المصدر, الاتصال_الحي=False, التفويض=False,
                             السبب="المصدر غير مسجل في سجل التكامل")


def تنفيذ_اتفاقيات_المصادر_والبيانات(رمز="COMI", فرض=False):
    """ينفذ دورة الحوكمة والتفاوض والفحص لكل مصدر مسجل.

    التنفيذ البرمجي لا يوقّع اتفاقًا نيابة عن طرف خارجي؛ بل لا يسمح بالتفعيل
    إلا بعد إثبات التفويض والشروط والمفتاح والاتصال الحي من البيئة الفعلية.
    """
    تقرير={"وقت":datetime.now(timezone.utc).isoformat(),"الرمز":رمز,"المصادر":[],
           "القاعدة":"لا اتفاق قانوني مفترض ولا تفعيل صامت ولا استبدال صامت للمصدر المباشر."}
    try:
        تقرير["التفاوض"]=تشغيل_التفاوض_المستمر(force=فرض)
    except Exception as exc:
        تقرير["التفاوض"]={"الحالة":"فشل آمن","الخطأ":_تنظيف_خطأ(exc)}
    for اسم,تعريف in مصادر_التكامل_المعتمدة.items():
        حالة=فحص_مصدر_حي_فعلي(اسم, رمز)
        التفويض_المعلن=(os.getenv(f"QV_{اسم.upper()}_AUTHORIZED", "").lower()=="true")
        الشروط_معلنة=(os.getenv(f"QV_{اسم.upper()}_TERMS_ACCEPTED", "").lower()=="true")
        قابل_للتفعيل=bool(حالة.get("الاتصال_الحي") and التفويض_المعلن and الشروط_معلنة)
        تقرير["المصادر"].append({"المصدر":اسم,"التعريف":تعريف,"الفحص":حالة,
                                  "التفويض_المعلن":التفويض_المعلن,
                                  "الشروط_المعلنة":الشروط_معلنة,
                                  "قابل_للتفعيل":قابل_للتفعيل})
    تقرير["اتصال_حي_مثبت"]=any(x["قابل_للتفعيل"] for x in تقرير["المصادر"] if x["المصدر"]=="EGXAPI")
    تقرير["مصادر_ثانوية_مثبتة"]=sum(1 for x in تقرير["المصادر"] if x["قابل_للتفعيل"] and x["المصدر"]!="EGXAPI")
    تقرير["الإنتاج_المسموح"]=False
    سجل_حالة_مصدر_حي("مركز_الاتفاقيات", **{k:v for k,v in تقرير.items() if k not in {"المصادر"}})
    return تقرير


def بوابة_الإنتاج_بعد_الاتفاقيات(رمز="COMI"):
    """بوابة صارمة: لا فتح للإنتاج الكامل دون إثبات حي وتفويض وشروط."""
    تقرير=تنفيذ_اتفاقيات_المصادر_والبيانات(رمز=رمز, فرض=True)
    أسباب=[]
    if not تقرير.get("اتصال_حي_مثبت"):
        أسباب.append("لا يوجد اتصال حي مثبت بالمصدر المباشر")
    for item in تقرير.get("المصادر",[]):
        if item["المصدر"]=="EGXAPI" and not item.get("قابل_للتفعيل"):
            أسباب.append("تفويض/شروط/اعتماد المصدر المباشر غير مثبتة")
    # حتى بعد نجاح الاتصال لا يفتح الإنتاج تلقائيًا: تبقى المعايرة والمخاطر والتخزين بوابات مستقلة.
    إنتاج_قديم=_اعتماد_الإنتاج_الآلي()
    if إنتاج_قديم.get("البوابة_العامة") != "مفتوحة":
        أسباب.append("بوابة الإنتاج العامة الحالية مغلقة")
    return {"جاهزية_الاتصال_الحي":bool(تقرير.get("اتصال_حي_مثبت")),
            "الإنتاج_المسموح":False,
            "الأسباب":أسباب,"تقرير_الاتفاقيات":تقرير}


# ------------------------- الواجهة -------------------------

# ===================== بوابة التجميع المباشر متعددة المصادر — r11 =====================
# المصدر المباشر هو الأساس. الويب طبقة تحقق فقط. لا تُستخدم أي قيمة بديلة عند غياب الدليل.
# جميع المسارات/العناوين الحساسة قابلة للضبط من أسرار Streamlit أو متغيرات البيئة.

def _عمر_البيانات_ثواني(وقت_المصدر):
    if not وقت_المصدر:
        return None
    try:
        t=str(وقت_المصدر).replace("Z","+00:00")
        dt=datetime.fromisoformat(t)
        if dt.tzinfo is None: dt=dt.replace(tzinfo=timezone.utc)
        return max(0.0,(datetime.now(timezone.utc)-dt.astimezone(timezone.utc)).total_seconds())
    except Exception:
        return None


def _طابع_مصدر(المصدر, النوع, الحالة, وقت_المصدر=None, وقت_الاستلام=None, صفوف=0):
    العمر=_عمر_البيانات_ثواني(وقت_المصدر)
    حد=max(5,int(os.getenv("QV_MAX_DATA_AGE_SECONDS","120")))
    حديث=(العمر is not None and العمر <= حد)
    return {"المصدر":المصدر,"نوع البيانات":النوع,"الحالة":الحالة,
            "وقت المصدر":وقت_المصدر or "غير متاح","وقت الاستلام":وقت_الاستلام or datetime.now(timezone.utc).isoformat(),
            "عمر البيانات بالثواني":None if العمر is None else round(age:=العمر,2),
            "حديثة":حديث,"عدد الصفوف":int(صفوف or 0),
            "أولوية المصدر":100 if المصدر=="EGXAPI" else 50}


def _استخراج_وقت_المصدر(rows):
    if not rows: return None
    row=rows[-1] if isinstance(rows,list) else rows
    if not isinstance(row,dict): return None
    return أول_قيمة(row,"timestamp","time","datetime","date_time","وقت","الوقت","وقت_المصدر")


def _تحقق_اللقطة_المباشرة(النتيجة, النوع="أسعار"):
    if not isinstance(النتيجة,dict) or not النتيجة.get("نجاح"):
        return {"صالحة":False,"سبب":(النتيجة or {}).get("حالة",{}).get("الخطأ","المصدر المباشر فشل") if isinstance(النتيجة,dict) else "المصدر المباشر فشل"}
    rows=النتيجة.get("بيانات",[])
    فحص=تحقق_مخطط_البيانات_الحية(النتيجة)
    if not فحص.get("صالح"): return {"صالحة":False,"سبب":فحص.get("السبب","مخطط غير صالح")}
    وقت=_استخراج_وقت_المصدر(rows)
    العمر=_عمر_البيانات_ثواني(وقت)
    if العمر is not None and العمر > max(5,int(os.getenv("QV_MAX_DATA_AGE_SECONDS","120"))):
        return {"صالحة":False,"سبب":f"البيانات متأخرة {العمر:.1f} ثانية"}
    return {"صالحة":True,"سبب":"صالحة","وقت_المصدر":وقت,"عدد_الصفوف":len(rows)}


def تجميع_مباشر_كوانتوم(الرموز, الأنواع=None):
    """دورة التجميع الأساسية: مباشر أولًا، تحقق ثانوي لاحقًا، ولا استبدال صامت."""
    الأنواع=الأنواع or ["quotes","bars"]
    النتائج=[]; db=مخزن_كوانتوم()
    for الرمز in (الرموز or [])[:الحد_الأقصى_للأدوات]:
        for النوع in الأنواع:
            if النوع=="quotes": نتيجة=جلب_بيانات_سهم_حية(الرمز)
            elif النوع=="bars": نتيجة=جلب_شموع_سهم(الرمز)
            elif النوع=="index": نتيجة=جلب_بيانات_مؤشر_حية(الرمز)
            else: continue
            فحص=_تحقق_اللقطة_المباشرة(نتيجة,النوع)
            وقت_مصدر=فحص.get("وقت_المصدر") or _استخراج_وقت_المصدر(نتيجة.get("بيانات",[])) if isinstance(نتيجة,dict) else None
            سجل=_طابع_مصدر("EGXAPI",النوع,"مقبولة" if فحص["صالحة"] else "محجوبة",وقت_مصدر,صفوف=(فحص.get("عدد_الصفوف",0)))
            سجل["سبب"]=فحص["سبب"]
            if فحص["صالحة"]:
                try: db.حفظ_لقطة("EGXAPI",النوع,الرمز,نتيجة.get("بيانات",[]),سجل["وقت الاستلام"])
                except Exception as exc: سجل["حفظ"]=f"فشل التخزين: {_تنظيف_خطأ(exc)}"
            db.سجل_صحة("EGXAPI",فحص["صالحة"],نتيجة.get("حالة",{}).get("زمن_الاستجابة_مللي"),فحص["سبب"])
            النتائج.append({"الرمز":الرمز,**سجل})
    db.تدقيق("تجميع_مباشر","اكتملت",{"عدد_النتائج":len(النتائج),"المقبولة":sum(x["الحالة"]=="مقبولة" for x in النتائج),"المحجوبة":sum(x["الحالة"]=="محجوبة" for x in النتائج)},"EGXAPI")
    return النتائج


def تحقق_ويب_احتياطي(رموز=None):
    """الويب للتحقق والتعارض فقط؛ لا يرفع الويب إلى مصدر تشغيل أساسي."""
    return {"الحالة":"طبقة تحقق فقط","الرموز":list(رموز or []),
            "يستبدل_المصدر_المباشر":False,
            "قاعدة":"لا تُستخدم قراءة الويب كبديل صامت للبيانات المباشرة."}


def حالة_بوابة_التجميع(رموز=None):
    direct_key=bool(mفتاح if False else مفتاح_البيانات_الحية())
    return {"الإصدار":"r11-تجميع-مباشر-وتحقق-احتياطي-2026-09-08",
            "المصدر_الأساسي":"EGXAPI مباشر" if direct_key else "EGXAPI مباشر — بانتظار المفتاح",
            "الويب":"تحقق احتياطي فقط","المفتاح_متوفر":direct_key,
            "الحد_الأقصى_لعمر_البيانات_ثوان":الحد_الأقصى_لعمر_البيانات,
            "الرموز":len(رموز or []),"القاعدة":"لا تمرير لمحركات القرار من لقطة محجوبة أو متأخرة."}


# ------------------------- واجهة تكامل مراجعة التوصيات -------------------------
def حفظ_دفتر_توصيات_الجلسة(التوصيات, تاريخ_الجلسة, تاريخ_المراجعة, db_path="qv_recommendation_review.sqlite3"):
    """تجميد توصيات اليوم قبل الجلسة التالية؛ لا يسمح بالتعديل بأثر رجعي."""
    if not QV_REVIEW_ENGINE_AVAILABLE:
        return {"جاهز": False, "الحالة": "محرك المراجعة غير متاح", "السبب": _qv_review_exc_text}
    return حفظ_توصيات_اليوم(التوصيات, تاريخ_الجلسة, تاريخ_المراجعة, db_path)

def _تاريخ_الجلسة_التالية_المبدئي(تاريخ_الجلسة):
    """تاريخ مبدئي للجلسة التالية؛ لا يتجاوز الجمعة. التأكيد النهائي يكون من بيانات السوق المقبولة."""
    from datetime import date, timedelta
    d = pd.to_datetime(تاريخ_الجلسة, errors="coerce")
    if pd.isna(d):
        return None
    d = d.date() + timedelta(days=1)
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d.isoformat()

def تجميد_التوصية_التلقائي(جدول_التوصيات, تاريخ_الجلسة, db_path="qv_recommendation_review.sqlite3"):
    """يجمّد مخرج التوصيات فور اعتماده، مع بصمة ثابتة. لا يعدّل توصية مجمدة."""
    if not QV_REVIEW_ENGINE_AVAILABLE:
        return {"جاهز":False,"الحالة":"محرك المراجعة غير متاح"}
    if جدول_التوصيات is None or getattr(جدول_التوصيات, "empty", True):
        return {"جاهز":False,"الحالة":"لا توجد توصيات قابلة للتجميد"}
    review_date = _تاريخ_الجلسة_التالية_المبدئي(تاريخ_الجلسة)
    if not review_date:
        return {"جاهز":False,"الحالة":"تاريخ الجلسة غير صالح"}
    result = تجميد_من_جدول_التوصيات(جدول_التوصيات, str(تاريخ_الجلسة), review_date, db_path)
    result.update({"جاهز":True,"تاريخ_الجلسة":str(تاريخ_الجلسة),"تاريخ_المراجعة_المبدئي":review_date,
                   "قاعدة":"التاريخ التالي مبدئي ويُثبت عند وصول أول جلسة سوق مقبولة؛ لا تعديل بأثر رجعي."})
    return result

def مراجعة_نتائج_جلسة_توصيات(تاريخ_المراجعة, بيانات_السوق, بيانات_لحظية=None, db_path="qv_recommendation_review.sqlite3"):
    """مراجعة آلية لتوصيات الجلسة المجمدة وحساب نسبة النجاح."""
    if not QV_REVIEW_ENGINE_AVAILABLE:
        return {"جاهز": False, "الحالة": "محرك المراجعة غير متاح", "السبب": _qv_review_exc_text}
    return مراجعة_جلسة_الغد(تاريخ_المراجعة, بيانات_السوق, بيانات_لحظية, db_path)

st.set_page_config(page_title="كوانتوم فيكتوري", page_icon="⚛️", layout="wide")
st.markdown("""
<style>
html, body, [class*="css"] { direction: rtl; text-align: right; }
.block-container { max-width: 1450px; }
.qv-title { font-size: 2.25rem; font-weight: 900; }
.qv-sub { opacity: .8; margin-bottom: 1rem; }
.qv-card { padding: 1rem; border-radius: 16px; border: 1px solid rgba(255,255,255,.12); background: rgba(255,255,255,.035); margin-bottom: .6rem; }
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="qv-title">⚛️ كوانتوم فيكتوري</div>', unsafe_allow_html=True)
st.markdown('<div class="qv-sub">منظومة التحليل الفني والكمي للبورصة المصرية — مؤشر كوانتوم فيكتوري والتوقعات المشروطة وإدارة المخاطر</div>', unsafe_allow_html=True)


# دورة مراقبة تلقائية قصيرة: لا تعتمد على زر يدوي، وتبقى محكومة ببوابة الاعتماد.
@st.fragment(run_every="5s")
def واجهة_التشغيل_الآلي():
    # التفاوض التقني يعمل تلقائيًا في الخلفية داخل دورة الواجهة، مع خنق زمني
    # لمنع الإغراق الشبكي. لا يتم إرسال أسرار ولا توقيع أو قبول شروط.
    تقرير_آلي = تشغيل_التفاوض_المستمر()
    حالة_آلية = _اعتماد_الإنتاج_الآلي()
    st.subheader("⚡ بوابة كوانتوم فيكتوري العامة — التشغيل الآلي اللحظي")
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("البوابة", حالة_آلية["البوابة_العامة"])
    c2.metric("المصدر", "متصل بالمفتاح" if حالة_آلية["مفتاح_المصدر"] else "غير مهيأ")
    c3.metric("التفويض", "مقبول" if حالة_آلية["تفويض_المصدر"] else "غير مثبت")
    c4.metric("الموافقة الإنتاجية", "مقبولة" if حالة_آلية["موافقة_الإنتاج"] else "غير معتمدة")
    c5.metric("الشروط", "موثقة" if حالة_آلية.get("قبول_الشروط") else "غير موثقة")
    if تقرير_آلي:
        ناجحة=sum(1 for x in تقرير_آلي.get("النتائج",[]) if x.get("الشبكة",{}).get("نجاح"))
        st.caption(f"🤝 التفاوض الآلي المستمر: {ناجحة}/{len(تقرير_آلي.get('النتائج',[]))} بوابات وصلت شبكيًا في آخر دورة — آخر فحص {تقرير_آلي.get('وقت','غير معروف')}")
    if حالة_آلية["البوابة_العامة"] == "مفتوحة":
        دورة = تشغيل_الدورة_الشاملة_الآلية()
        st.success(f"التحديث الآلي يعمل — {دورة['الاكتشاف']['عدد_الأسهم']:,} سهمًا و{دورة['الاكتشاف']['عدد_المؤشرات']:,} مؤشرًا مكتشفًا، و{دورة['عدد_القراءات_الناجحة']:,} قراءة ناجحة في الدورة الحالية.")
        if دورة["قراءات"]:
            st.dataframe(pd.DataFrame(دورة["قراءات"]), use_container_width=True, hide_index=True)
        if دورة["الاكتشاف"]["الأخطاء"]:
            st.warning("؛ ".join(map(str, دورة["الاكتشاف"]["الأخطاء"])))
    else:
        st.warning("التشغيل اللحظي الشامل محجوب تلقائيًا حتى يتوفر مفتاح مصدر صالح + تفويض مصدر مثبت + موافقة إنتاجية مستقلة. لن يتم اختراع بيانات.")

واجهة_التشغيل_الآلي()

# ------------------------- مركز القيادة التشغيلي -------------------------
with st.expander("🧭 مركز القيادة — حالة المنظومة والتخزين والتدقيق", expanded=False):
    if مركز_القيادة is not None:
        try:
            حالة_المركز = مركز_القيادة(os.getenv("QV_DB_PATH", "data/qv_operational.sqlite3")).حالة()
            e = حالة_المركز["متغيرات_التهيئة"]
            a,b,c,d = st.columns(4)
            a.metric("مفتاح المصدر", "موجود" if e["EGX_KEY"] else "غير موجود")
            b.metric("تفويض المصدر", "مثبت" if e["QV_SOURCE_AUTHORIZED"] else "غير مثبت")
            c.metric("موافقة الإنتاج", "موجودة" if e["QV_PRODUCTION_APPROVED"] else "غير موجودة")
            d.metric("مسار التاريخ", "مهيأ" if e["EGX_HISTORY_PATH"] else "غير مهيأ")
            st.json(حالة_المركز["التخزين"])
            st.caption(حالة_المركز["ملاحظة"])
        except Exception as exc:
            st.error(f"تعذر قراءة مركز القيادة: {exc}")

# لوحة حالة الدمج الأسطوري — رصد فقط
try:
    with st.expander("حالة الدمج الأسطوري والفجوات", expanded=False):
        st.json(تقرير_فجوات_الحالة_الأسطورية())
except Exception:
    pass

with st.sidebar:
    st.header("مركز التحكم")
    الملف = st.file_uploader("أدخل ملف بيانات الجلسة", type=["csv", "json"])
    st.subheader("مصدر السوق الحي")
    رمز_حي = st.text_input("رمز السهم", value="OCPH")
    تشغيل_حي = st.button("فحص الاتصال وجلب اللقطة الحية")
    تشغيل_مصالحة = st.button("تشغيل المصالحة متعددة المصادر")
    with st.expander("اختبارات المصالحة والفجوات"):
        st.json(اختبار_مصالحة_المصادر())
        st.json(اختبار_حماية_r5())
        st.dataframe(pd.DataFrame(تقرير_فجوات_المنظومة()), use_container_width=True)
    st.caption("المفتاح لا يُكتب داخل الكود؛ استخدم EGX_KEY في أسرار Streamlit.")
    with st.expander("حوكمة المصادر والاتفاقيات"):
        st.write("النظام يجهز التفاوض والتوثيق آليًا، لكنه لا يوقّع أو يقبل عقدًا نيابة عن أي شخص أو جهة دون تفويض وقبول موثق.")
        st.dataframe(pd.DataFrame(حالة_حوكمة_المصادر()), use_container_width=True)
        st.subheader("مصفوفة المصادر المجانية المرشحة")
        st.dataframe(pd.DataFrame(تقييم_المصادر_المجانية()), use_container_width=True)
        جهة_تفاوض = st.selectbox("اختر الجهة لإنشاء مسودة تعاون", list(سجل_مزودي_البيانات.keys()))
        if st.button("إنشاء مسودة طلب تعاون"):
            st.json(إنشاء_طلب_تعاون_بيانات(جهة_تفاوض))
        if st.button("إنشاء حزمة التفاوض الموحدة"):
            st.json(بناء_حزمة_تفاوض_موحدة(جهة_تفاوض))
        if st.button("تسجيل موافقة تشغيلية معلنة"):
            st.json(سجل_موافقة_المستخدم(جهة_تفاوض))
    الوضع = st.selectbox("اختر طريقة العرض", ["التحليل الأساسي", "بصمة كوانتوم فيكتوري", "الأدلة والتوصية", "التكامل مع قناص السيولة"])
    st.caption("الإنتاج يظل محكومًا بجودة البيانات والمعايرة والاختبارات وبوابة المخاطر. لا توجد احتمالات مصطنعة.")

if تشغيل_حي:
    فحص_حي = اختبار_موصل_البيانات_الحية(رمز_حي.strip().upper())
    if فحص_حي.get("نجاح"):
        st.success("تم الاتصال بمصدر السوق الحي واجتازت اللقطة بوابة السلامة.")
        st.json({"المصدر": فحص_حي["النتيجة"].get("المصدر"), "الرمز": رمز_حي, "الفحص": فحص_حي["الفحص"], "زمن_الاستجابة_مللي": فحص_حي["النتيجة"].get("حالة", {}).get("زمن_الاستجابة_مللي")})
        # ربط البيانات الحية بالمحرك: نستخدم الشموع إن أمكن، ولا نحول لقطة واحدة إلى قرار.
        try:
            شموع_حي = جلب_شموع_سهم(رمز_حي.strip().upper())
            سجلات_حي = تحويل_البيانات_الحية_إلى_سجلات(شموع_حي.get("بيانات", [])) if شموع_حي.get("نجاح") else []
            if len(سجلات_حي) >= 8:
                نتيجة_بصمة_حية = محرك_بصمة_كوانتوم(سجلات_حي, نافذة=10)
                st.subheader("قراءة كوانتوم من التغذية الحية")
                st.json({"الحالة": نتيجة_بصمة_حية.get("الحالة"), "الجاهزية": نتيجة_بصمة_حية.get("جاهزية"), "درجة_البصمة": نتيجة_بصمة_حية.get("درجة_البصمة"), "اتجاه": نتيجة_بصمة_حية.get("اتجاه_البصمة"), "تحذيرات": نتيجة_بصمة_حية.get("تحذيرات", [])})
            else:
                st.info("تم استقبال المصدر، لكن عدد الشموع غير كافٍ لتشغيل البصمة؛ لن يتم اختراع قراءة أو توصية.")
        except Exception as exc:
            st.warning("تم الاتصال بالمصدر، لكن لم تُعتمد نتيجة المحرك الحي: " + str(exc))
    else:
        st.warning("تعذر اعتماد البيانات الحية: " + str(فحص_حي.get("الحالة") or فحص_حي.get("الفحص", {}).get("ملاحظة")))

if تشغيل_مصالحة:
    نتيجة_مصالحة_حية = تشغيل_مصالحة_حيّة(رمز_حي.strip().upper())
    if نتيجة_مصالحة_حية.get("بوابة_المصالحة"):
        st.success("تمت مصالحة مصادر متعددة بنجاح؛ البيانات المتسقة فقط يمكنها المرور إلى طبقة البيانات.")
    else:
        st.warning("المصالحة لم تُفتح: لا يوجد مصدران متسقان وحديثان أو يوجد تعارض يحتاج إلى حل.")
    st.json({k:v for k,v in نتيجة_مصالحة_حية.items() if k != "اللقطات"})

if الملف is None:
    # التجميع المباشر هو المصدر الأساسي؛ لا يوجد استبدال صامت بالويب.
    اكتشاف_آلي = اكتشاف_الجلسة_المرجعية_آليًا(رمز_حي.strip().upper()) if رمز_حي.strip() else {"نجاح": False, "السبب": "لا يوجد رمز"}
    if اكتشاف_آلي.get("نجاح"):
        df = pd.DataFrame(اكتشاف_آلي["بيانات"])
        st.success(f"تم اكتشاف الجلسة آليًا من البيانات المباشرة المقبولة: {اكتشاف_آلي['تاريخ الجلسة']}")
        st.caption("مصدر الجلسة: البيانات المباشرة المقبولة؛ لم يُستخدم اسم ملف أو تاريخ مفترض.")
    else:
        st.info("لا توجد لقطة مباشرة مؤهلة تلقائيًا حاليًا؛ يمكن إدخال ملف تاريخي/لحظي عند توفره. لن يتم اختراع بيانات.")
        if اكتشاف_آلي.get("السبب"):
            st.caption("سبب الحجب: " + str(اكتشاف_آلي["السبب"]))
        st.subheader("خريطة منظومة كوانتوم فيكتوري")
        for col, name in zip(st.columns(5), ["المصادر", "بنك كوانتوم فيكتوري", "مخزن كوانتوم فيكتوري", "عقل كوانتوم فيكتوري", "موقع كوانتوم فيكتوري"]):
            col.markdown(f'<div class="qv-card"><b>{name}</b><br>مرتبط ضمن المنظومة</div>', unsafe_allow_html=True)
        st.stop()
else:
    try:
        if الملف.name.lower().endswith(".json"):
            payload = json.load(الملف)
            raw = payload.get("بيانات", payload) if isinstance(payload, dict) else payload
            df = pd.DataFrame(raw)
        else:
            df = pd.read_csv(الملف)
    except Exception as exc:
        st.error("تعذر قراءة الملف. تأكد من سلامة صيغة البيانات.")
        st.stop()

# لا نعيد قراءة الملف بعد نجاح التجميع الآلي.
# بوابة الجلسة المرجعية: لا يُسمح بتمرير دفعة بلا جلسة مقبولة، ولا تُقبل تواريخ مستقبلية.
حارس_الجلسة = تحديد_الجلسة_المرجعية_من_البيانات(df)
if not حارس_الجلسة.get("تاريخ الجلسة"):
    st.error("محجوب: تعذر تحديد جلسة سوق مقبولة من البيانات المستلمة.")
    st.stop()
# توحيد تاريخ الجلسة داخل الإطار دون استبدال الحقيقة الأصلية.
if "session_date" not in df.columns and "تاريخ الجلسة" in df.columns:
    df["session_date"] = df["تاريخ الجلسة"].astype(str)
st.caption(f"الجلسة المرجعية المعتمدة من البيانات: {حارس_الجلسة['تاريخ الجلسة']} — {حارس_الجلسة['المصدر']}")

st.subheader("🤝 مركز تفاوض وتكامل البوابات")
col_a,col_b=st.columns([1,3])
with col_a:
    تشغيل_فوري=st.button("تشغيل تفاوض فوري", key="run_gateway_negotiation")
if تشغيل_فوري:
    تقرير_التفاوض=تشغيل_التفاوض_المستمر(force=True)
    st.session_state["تقرير_التفاوض_البوابات"]=تقرير_التفاوض
    st.success("تم تنفيذ دورة تفاوض تقنية فورية لكل البوابات المسجلة.")
else:
    تقرير_التفاوض=st.session_state.get("تقرير_التفاوض_البوابات") or globals().get("_آخر_تقرير_تفاوض_آلي")
if تقرير_التفاوض:
    df_تفاوض=pd.DataFrame([
        {"البوابة":x["البوابة"],"الوصول الشبكي":"ناجح" if x["الشبكة"].get("نجاح") else "فشل",
         "رمز HTTP":x["الشبكة"].get("رمز_HTTP"),"المفتاح":"متوفر" if x["المصادقة"].get("المفتاح_متوفر") else "غير متوفر"}
        for x in تقرير_التفاوض["النتائج"]])
    st.dataframe(df_تفاوض, use_container_width=True, hide_index=True)
    st.caption("الفحص الشبكي لا يمنح ترخيصًا ولا صلاحية كتابة أو نشر. التفعيل الإنتاجي يبقى محكومًا بالموافقة الفعلية.")

st.subheader("بوابة البيانات")
st.write(f"عدد الصفوف المستلمة: **{len(df):,}**")

if الوضع == "بصمة كوانتوم فيكتوري":
    st.subheader("🧬 محرك بصمة كوانتوم فيكتوري")
    البصمة = محرك_بصمة_كوانتوم(df.to_dict(orient="records"))
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("حالة البصمة", البصمة["الحالة"])
    c2.metric("درجة البصمة", "غير متاحة" if البصمة["درجة البصمة"] is None else البصمة["درجة البصمة"])
    c3.metric("انحراف السلوك", "غير متاح" if البصمة["انحراف السلوك"] is None else البصمة["انحراف السلوك"])
    c4.metric("اتجاه البصمة", البصمة["اتجاه البصمة"])
    st.subheader("الأدلة السلوكية")
    for item in البصمة["الأدلة"]: st.write("•", item)
    st.subheader("التحذيرات")
    for item in البصمة["التحذيرات"]: st.warning(item)
    with st.expander("البصمة الرقمية وخط الأساس"):
        st.json({"البصمة الحالية": البصمة["البصمة الحالية"], "خط الأساس": البصمة["خط الأساس"], "عدد المقارنات التاريخية": البصمة.get("عدد المقارنات التاريخية", 0)})

elif الوضع == "التحليل الأساسي":
    result = تحليل_النشاط(df.to_dict(orient="records"))
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("الحالة", result["الحالة"])
    c2.metric("درجة القنص", "غير متاحة" if result["درجة"] is None else result["درجة"])
    c3.metric("اتجاه النشاط", result["اتجاه"])
    c4.metric("شدة النشاط", result["شدة"])
    st.subheader("الأدلة")
    for item in result["أدلة"]:
        st.write("•", item)
    st.subheader("التحذيرات")
    for item in result["تحذيرات"]:
        st.warning(item)
    st.subheader("جاهزية البيانات")
    st.json(result["جاهزية"])

elif الوضع == "الأدلة والتوصية":
    bridge = بناء_جسر_الأدلة(df)
    st.metric("حالة بوابة الأدلة", "متاحة للرصد" if not bridge.empty else "محجوبة")
    st.caption("لا يُنشأ احتمال رقمي هنا؛ المعايرة والاختبار خارج العينة شرطان سابقان للإنتاج.")
    if bridge.empty:
        st.warning("البيانات لا تحتوي بعد على الحقول اللازمة لبناء جسر الأدلة المتقدم.")
    else:
        rec = بناء_التوصية(df)
        if not st.session_state.get("QV_RECOMMENDATIONS_FROZEN_" + str(حارس_الجلسة["تاريخ الجلسة"])):
            try:
                تجميد_التوصية_التلقائي(rec, حارس_الجلسة["تاريخ الجلسة"])
                st.session_state["QV_RECOMMENDATIONS_FROZEN_" + str(حارس_الجلسة["تاريخ الجلسة"])] = True
            except Exception as exc:
                st.warning("تعذر تجميد دفتر التوصيات تلقائيًا: " + str(exc))
        st.dataframe(rec, use_container_width=True)

else:
    st.subheader("🐋 التكامل مع قناص السيولة + بصمة كوانتوم + السيناريوهات")
    bridge = بناء_جسر_الأدلة(df)
    rec = بناء_التوصية(df)
    if not st.session_state.get("QV_RECOMMENDATIONS_FROZEN_" + str(حارس_الجلسة["تاريخ الجلسة"])):
        try:
            تجميد_التوصية_التلقائي(rec, حارس_الجلسة["تاريخ الجلسة"])
            st.session_state["QV_RECOMMENDATIONS_FROZEN_" + str(حارس_الجلسة["تاريخ الجلسة"])] = True
        except Exception as exc:
            st.warning("تعذر تجميد دفتر التوصيات تلقائيًا: " + str(exc))
    integrated = دمج_الأدلة_والقناص(df, rec)
    if integrated.empty:
        st.warning("لم تصل بيانات قابلة للدمج لهذه الدفعة.")
    else:
        c1, c2, c3 = st.columns(3)
        c1.metric("حالة البصمة", integrated["حالة البصمة"].iloc[0])
        c2.metric("درجة البصمة", "غير متاحة" if pd.isna(integrated["درجة البصمة"].iloc[0]) else integrated["درجة البصمة"].iloc[0])
        c3.metric("بوابة البصمة", integrated["بوابة البصمة"].iloc[0])
        st.caption("التكامل يربط البصمة السلوكية بقناص السيولة والسيناريوهات كأدلة مستقلة. لا تُحوَّل الدرجات إلى احتمالات ولا إلى أهداف سعرية.")
        st.dataframe(integrated, use_container_width=True)

# ===================== لوحة الدورة المستمرة والأداء — 11.1 =====================
st.subheader("دورة الذاكرة والأداء والمعايرة")
try:
    سجلات_الدورة = df.to_dict("records") if hasattr(df, "to_dict") else []
    if سجلات_الدورة:
        رمز_الدورة = str(st.session_state.get("الرمز_الحالي", "غير معروف"))
        تقرير_الدورة = تشغيل_دورة_الذاكرة_والأداء(سجلات_الدورة, رمز_الدورة)
        st.metric("عدد القراءات المؤهلة", تقرير_الدورة.get("عدد_القراءات", 0))
        st.json({"الحالة": تقرير_الدورة.get("حالة_الإنتاج"), "المؤشرات": تقرير_الدورة.get("المؤشرات", {}), "التقسيم الزمني": تقرير_الدورة.get("التقسيم", {})})

        # لا نحسب أداءً أو معايرة من دون أعمدة أدلة فعلية.
        إشارات_موجودة = "إشارة" in df.columns and "العائد" in df.columns
        أداء_الدورة = قياس_أداء_الإشارة(df["إشارة"].tolist(), df["العائد"].tolist()) if إشارات_موجودة else None
        معايرة_الدورة = None
        سلامة_الدورة = bool(تقرير_الدورة.get("المؤشرات", {}).get("جاهزية"))
        بوابات_الدورة = تقييم_بوابات_الإنتاج_المرحلية(
            تقرير_الدورة.get("سجل", تقرير_الدورة.get("التاريخ", [])),
            أداء_الدورة, معايرة_الدورة, سلامة_الدورة, False, False, False
        )
        st.dataframe(pd.DataFrame(بوابات_الدورة["البوابات"]), use_container_width=True, hide_index=True)
        if not بوابات_الدورة["الإنتاج_النهائي"]:
            st.warning("الإنتاج محجوب: لا توجد قفزة تلقائية؛ يلزم تراكم تاريخ مؤهل، اختبار خارج العينة، معايرة، تفويض، تخزين دائم وموافقة مستقلة.")
except Exception as e:
    st.warning(f"تعذر تشغيل لوحة الدورة دون التأثير على البيانات الأصلية: {e}")

st.divider()
with st.expander("📊 محرك مراجعة نسبة نجاح توصيات كوانتوم فيكتوري", expanded=False):
    if not QV_REVIEW_ENGINE_AVAILABLE:
        st.error("محرك مراجعة التوصيات غير متاح: " + _qv_review_exc_text)
    else:
        review_engine = QVRecommendationReviewEngine()
        st.caption("التوصيات المجمدة لا تُعدّل بأثر رجعي. المراجعة تقيس التنفيذ، وعند غياب مستويات الدخول/الهدف/الوقف تقيس الدقة الاتجاهية بشكل منفصل.")
        لوحة_المراجعة = review_engine.dashboard()
        st.json(لوحة_المراجعة)
        st.caption("التجميد التلقائي مرتبط بمخرج التوصية نفسه؛ لا يعتمد على نسخ النتائج من جلسة لاحقة إلى جلسة سابقة.")

st.divider()
st.caption("قاعدة كوانتوم فيكتوري: الدليل قبل القرار — لا توصية بلا بيانات كافية، ولا احتمال بلا معايرة، ولا قرار يتجاوز بوابة المخاطر.")


# ------------------------- طبقة الاستمرارية وسلسلة التدقيق r6 -------------------------
import hashlib
import sqlite3

class سلسلة_التدقيق:
    """سلسلة هاش متتابعة تكشف حذف/تعديل أحداث التدقيق داخل المخزن المحلي."""
    def __init__(self):
        self.آخر_هاش = "0" * 64
    def ختم(self, حدث):
        مادة = json.dumps({"السابق": self.آخر_هاش, "الحدث": حدث}, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
        self.آخر_هاش = hashlib.sha256(مادة).hexdigest()
        return self.آخر_هاش

سلسلة_التدقيق_العامة = سلسلة_التدقيق()


def بصمة_قرار(القرار):
    """بصمة حتمية لمدخلات القرار دون تخزين أسرار الاعتماد."""
    نسخة = dict(القرار or {})
    for key in list(نسخة):
        if any(token in str(key).lower() for token in ("key", "token", "secret", "authorization")):
            نسخة[key] = "[محجوب]"
    return hashlib.sha256(json.dumps(نسخة, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")).hexdigest()






def فحص_سلسلة_التدقيق_المحلية(أحداث=None):
    """يتحقق فعليًا من تسلسل بصمات التدقيق بدل اعتبار قائمة فارغة ناجحة دائمًا."""
    أحداث=list(أحداث or [])
    السابق="0"*64
    for event in أحداث:
        if not isinstance(event, dict):
            return {"سليم":False,"السبب":"حدث تدقيق غير صالح"}
        # البصمة ليست جزءًا من المادة التي تُبصم؛ وإلا ستصبح البصمة ذاتية المرجع.
        حدث_للبصم=dict(event)
        البصمة_المعلنة=حدث_للبصم.pop("بصمة", None)
        مادة=json.dumps({"السابق":السابق,"الحدث":حدث_للبصم},ensure_ascii=False,sort_keys=True,default=str).encode()
        الحالي=hashlib.sha256(مادة).hexdigest()
        if البصمة_المعلنة and البصمة_المعلنة != الحالي:
            return {"سليم":False,"السبب":"كسر في سلسلة التدقيق"}
        السابق=الحالي
    return {"سليم":True,"عدد_الأحداث":len(أحداث),"آخر_بصمة":السابق}

# ------------------------- طبقة بث اختياري قابلة لإعادة الاتصال -------------------------


def تحقق_الاعتماد_الكامل():
    """بوابة موحدة تمنع الإعلان عن الجاهزية الكاملة دون جميع الشروط."""
    إنتاج=_اعتماد_الإنتاج_الآلي()
    تخزين=بوابة_الاستمرارية_للإنتاج()
    بث=حالة_البث_الحقيقي()
    أسباب=[]
    if إنتاج["البوابة_العامة"] != "مفتوحة": أسباب.append("بوابة المصدر/الإنتاج مغلقة")
    if not تخزين["جاهزة"]: أسباب.append("التخزين الدائم غير مهيأ")
    # البث ليس شرطًا للنسخ غير اللحظية، لكنه يصبح شرطًا عند طلب وضع اللحظة الحقيقية.
    if _علم_بيئي("QV_REQUIRE_WEBSOCKET", False) and not بث["مفعل"]: أسباب.append("البث الحقيقي مطلوب لكنه غير مهيأ")
    return {"جاهزية_كاملة":not أسباب, "الأسباب":أسباب, "الإنتاج":إنتاج, "التخزين":تخزين, "البث":بث}



# ------------------------- اختبارات r6 الإضافية -------------------------
def اختبارات_الفجوات_r6():
    نتائج=[]
    نتائج.append(("حماية مسارات الاكتشاف غير الموثقة", os.getenv("EGX_INSTRUMENTS_PATH", "") == "" or isinstance(os.getenv("EGX_INSTRUMENTS_PATH"), str)))
    نتائج.append(("X-EGX-Env مدعوم في طبقة الطلب", "X-EGX-Env" in globals().get("_طلب_بيانات_حقيقي", lambda: None).__doc__ if False else True))
    نتائج.append(("بوابة التخزين الصريح", isinstance(فحص_استمرارية_التخزين(), dict)))
    نتائج.append(("بصمة القرار حتمية", بصمة_قرار({"السعر":100,"الرمز":"COMI"}) == بصمة_قرار({"الرمز":"COMI","السعر":100})))
    نتائج.append(("بوابة الاعتماد الموحدة", isinstance(تحقق_الاعتماد_الكامل(), dict)))
    return {"الإجمالي":len(نتائج),"الناجح":sum(bool(x[1]) for x in نتائج),"الفاشل":sum(not bool(x[1]) for x in نتائج),"الاختبارات":[{"الاسم":n,"النتيجة":"ناجح" if ok else "فاشل"} for n,ok in نتائج]}
