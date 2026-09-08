# -*- coding: utf-8 -*-
"""عامل مستقل للتفاوض التقني المستمر في كوانتوم فيكتوري.
لا يوقع عقودًا، ولا يقبل شروطًا، ولا يرسل أسرارًا في فحص الوصول.
يستمر حتى إيقاف العملية، ويكتب كل دورة في سجل المشروع.
"""
import os, time, json, importlib.util, traceback
from pathlib import Path
APP=Path(__file__).with_name("app.py")
spec=importlib.util.spec_from_file_location("qv_app", APP)
mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
interval=max(30,int(os.getenv("QV_NEGOTIATION_INTERVAL_SECONDS","60")))
print(f"كوانتوم فيكتوري: عامل التفاوض المستمر بدأ — الفاصل {interval} ثانية", flush=True)
while True:
    started=time.time()
    try:
        report=mod.تشغيل_التفاوض_المستمر(force=True)
        ok=sum(1 for x in (report or {}).get("النتائج",[]) if x.get("الشبكة",{}).get("نجاح"))
        total=len((report or {}).get("النتائج",[]))
        print(json.dumps({"وقت":(report or {}).get("وقت"),"وصل_شبكيًا":ok,"الإجمالي":total},ensure_ascii=False),flush=True)
    except Exception as exc:
        print(json.dumps({"الحالة":"فشل دورة تفاوض","الخطأ":str(exc)},ensure_ascii=False),flush=True)
    time.sleep(max(1, interval-(time.time()-started)))
