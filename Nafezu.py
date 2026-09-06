# -*- coding: utf-8 -*-
"""
نفذ — مركز قيادة افتتاح الجلسة وقناص الحيتان والسيولة
كوانتوم فيكتوري | إصدار تنفيذي محادثي مستقل

تشغيل:
    python Nafezu.py
    python Nafezu.py --csv بيانات.csv
    python Nafezu.py --json بيانات.json
    python Nafezu.py --server --port 8765

صيغة البيانات الدنيا: الوقت،السعر،الحجم،الافتتاح،الأعلى،الأدنى،الإغلاق
يمكن تشغيل القناص على بيانات الجلسة المتاحة فقط. لا يدعي معرفة هوية المؤسسات.
"""
from __future__ import annotations
import argparse, csv, json, math, statistics
from dataclasses import dataclass, asdict
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

اسم_الإصدار = "نفذ — مركز قيادة افتتاح الجلسة ٥.٩.٣"

@dataclass
class نتيجة:
    الحالة: str
    درجة_القنص: float | None
    اتجاه_السيولة: str
    شدة_السيولة: str
    دلائل: list[str]
    تحذيرات: list[str]
    نقاط_المتابعة: list[str]
    جاهزية: dict[str, Any]
    إنتاج: bool = False


def رقم(x, default=None):
    try:
        if x is None or x == "": return default
        return float(str(x).replace(",", ""))
    except Exception:
        return default


def تطبيع(سجلات):
    out=[]
    for i,r in enumerate(سجلات or []):
        d={str(k).strip().lower():v for k,v in dict(r).items()}
        def g(*ks):
            for k in ks:
                if k in d: return d[k]
            return None
        price=رقم(g("price","السعر","close","الإغلاق"))
        vol=رقم(g("volume","الحجم","vol"),0)
        if price is None: continue
        out.append({"الترتيب":i,"الوقت":g("time","الوقت","timestamp") or str(i),
                    "السعر":price,"الحجم":vol,
                    "الافتتاح":رقم(g("open","الافتتاح")),
                    "الأعلى":رقم(g("high","الأعلى")),"الأدنى":رقم(g("low","الأدنى")),
                    "الإغلاق":رقم(g("close","الإغلاق"),price)})
    return out


def جاهزية_البيانات(data):
    n=len(data)
    return {"عدد_القراءات":n,
            "جاهزة_للقنص": n>=3,
            "جاهزة_لتحليل_أعمق": n>=20,
            "دفتر_الأوامر":False,
            "بيانات_تنفيذ_تفصيلية":False,
            "ملاحظة":"تحتاج بيانات دفتر الأوامر والتنفيذ التفصيلي إن أريدت مؤشرات لحظية أعمق."}


def حلل(data):
    data=تطبيع(data)
    جاهزية=جاهزية_البيانات(data)
    تحذيرات=[]; دلائل=[]; متابعة=[]
    if len(data)<3:
        return نتيجة("محجوب — بيانات غير كافية",None,"غير محدد","غير كافية",[],["يلزم ٣ قراءات سعر/حجم على الأقل."],[],جاهزية)
    prices=[x["السعر"] for x in data]; vols=[x["الحجم"] for x in data]
    recent=prices[-1]; prev=prices[-2]
    تغير=(recent-prev)/prev*100 if prev else 0
    base=statistics.median(vols[:-1]) if len(vols)>1 else vols[-1]
    ratio=vols[-1]/base if base>0 else 0
    # قياس اتجاه التدفق بشكل محافظ من تغير السعر + تغير الحجم.
    score=0.0
    if تغير>0: score += min(30, تغير*10)
    elif تغير<0: score += max(-30, تغير*10)
    if ratio>=2: score += 30 if تغير>0 else -30
    elif ratio>=1.25: score += 15 if تغير>0 else -15
    if len(prices)>=4:
        momentum=(prices[-1]-prices[-4])/prices[-4]*100
        if momentum>0: score += min(20,momentum*5)
        elif momentum<0: score += max(-20,momentum*5)
    score=max(-100,min(100,score))
    if تغير>0 and ratio>=1.25:
        اتجاه="شراء مرجح"; دلائل.append(f"ارتفاع السعر {تغير:.2f}% مع حجم يقارب {ratio:.2f} مرة من خط الأساس.")
    elif تغير<0 and ratio>=1.25:
        اتجاه="بيع مرجح"; دلائل.append(f"انخفاض السعر {abs(تغير):.2f}% مع حجم يقارب {ratio:.2f} مرة من خط الأساس.")
    else:
        اتجاه="مختلط / يحتاج تأكيد"; دلائل.append(f"تغير السعر {تغير:.2f}% ونسبة الحجم {ratio:.2f}؛ الدلالة غير حاسمة.")
    if ratio>=2: شدة="مرتفعة جدًا"
    elif ratio>=1.25: شدة="مرتفعة"
    elif ratio>0: شدة="طبيعية/متوسطة"
    else: شدة="غير متاحة"
    # لا نحول الدرجة إلى احتمال.
    if abs(score)>=55: حالة="إشارة قوية نسبيًا — تحتاج تأكيد"
    elif abs(score)>=25: حالة="تنبيه قنص — مراقبة نشطة"
    else: حالة="مراقبة — لا إشارة حاسمة"
    if len(data)<20: تحذيرات.append("العينة قصيرة؛ لا تستخدم النتيجة كحكم إحصائي نهائي.")
    تحذيرات.append("لا يمكن استنتاج هوية حوت أو مؤسسة من هذه البيانات وحدها.")
    تحذيرات.append("درجة القنص ليست احتمالًا ولا هدفًا سعريًا.")
    متابعة += ["مراقبة استمرار التدفق في القراءات التالية.","فحص الامتصاص أو الانعكاس عند توفر بيانات تنفيذ/دفتر أوامر.","إبطال التنبيه إذا انعكس السلوك مع حجم مؤيد للاتجاه المعاكس."]
    return نتيجة(حالة,round(score,2),اتجاه,شدة,دلائل,تحذيرات,متابعة,جاهزية)


def قراءة_ملف(path):
    p=Path(path)
    if p.suffix.lower()=='.json':
        return json.loads(p.read_text(encoding='utf-8'))
    with p.open('r',encoding='utf-8-sig',newline='') as f: return list(csv.DictReader(f))


def عرض(res):
    print("\n"+"="*72)
    print(اسم_الإصدار)
    print("="*72)
    print("الحالة:",res.الحالة)
    print("درجة القنص:",res.درجة_القنص if res.درجة_القنص is not None else "غير متاحة")
    print("اتجاه السيولة:",res.اتجاه_السيولة)
    print("شدة السيولة:",res.شدة_السيولة)
    print("\nالدلائل:")
    for x in res.دلائل: print(" •",x)
    print("\nنقاط المتابعة:")
    for x in res.نقاط_المتابعة: print(" •",x)
    print("\nالحواجز:")
    for x in res.تحذيرات: print(" •",x)
    print("\nجاهزية البيانات:",json.dumps(res.جاهزية,ensure_ascii=False,indent=2))
    print("الإنتاج مصرح؟", "نعم" if res.إنتاج else "لا")


def خادم(port):
    class Handler(BaseHTTPRequestHandler):
        def send_json(self,obj,code=200):
            raw=json.dumps(obj,ensure_ascii=False,indent=2).encode('utf-8')
            self.send_response(code); self.send_header('Content-Type','application/json; charset=utf-8'); self.send_header('Content-Length',str(len(raw))); self.end_headers(); self.wfile.write(raw)
        def do_GET(self):
            if self.path.rstrip('/')=='/حالة':
                self.send_json({"الإصدار":اسم_الإصدار,"الحالة":"جاهز قبل الجلسة","الإنتاج":False})
            else: self.send_json({"رسالة":"استخدم /حالة أو أرسل بيانات إلى /تحليل"},404)
        def do_POST(self):
            if self.path.rstrip('/')!='/تحليل': return self.send_json({"خطأ":"المسار غير صحيح"},404)
            n=int(self.headers.get('Content-Length','0')); body=self.rfile.read(n)
            try:
                payload=json.loads(body.decode('utf-8')); data=payload.get('بيانات',payload)
                self.send_json(asdict(حلل(data)))
            except Exception as e: self.send_json({"خطأ":"تعذر تحليل البيانات","تفصيل":str(e)},400)
        def log_message(self,fmt,*args): pass
    server=HTTPServer(('127.0.0.1',port),Handler)
    print(f"نفذ يعمل محليًا على المنفذ {port}. أوقفه بـ Ctrl+C")
    server.serve_forever()


def main():
    ap=argparse.ArgumentParser(description="مركز قيادة افتتاح الجلسة وقناص السيولة")
    ap.add_argument('--csv',help='ملف بيانات بصيغة CSV')
    ap.add_argument('--json',help='ملف بيانات بصيغة JSON')
    ap.add_argument('--server',action='store_true',help='تشغيل واجهة محلية')
    ap.add_argument('--port',type=int,default=8765)
    args=ap.parse_args()
    if args.server: return خادم(args.port)
    if args.csv or args.json:
        res=حلل(قراءة_ملف(args.csv or args.json)); عرض(res); return
    print(اسم_الإصدار)
    print("جاهز قبل بداية الجلسة. أدخل ٣ قراءات أو أكثر بصيغة: السعر,الحجم")
    rows=[]
    while True:
        s=input("نفذ> ").strip()
        if s in ('خروج','exit','quit'): break
        if s in ('جاهزية','استعداد'):
            print(json.dumps(جاهزية_البيانات(rows),ensure_ascii=False,indent=2)); continue
        try:
            p,v=[x.strip() for x in s.split(',',1)]; rows.append({'السعر':p,'الحجم':v}); عرض(حلل(rows))
        except Exception:
            print("الصيغة المطلوبة: السعر,الحجم — مثال: 10.25,150000")

if __name__=='__main__': main()
