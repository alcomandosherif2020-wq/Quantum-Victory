# -*- coding: utf-8 -*-
"""
كوانتوم فيكتوري — النسخة الموحدة لواجهة التحليل
تشغيل: streamlit run كوانتوم_فيكتوري_النسخة_الموحدة.py

هذه النسخة مستقلة عن الملفات الداخلية الأساسية، وتحتفظ ببوابات الفشل الآمن:
لا بيانات كافية = لا قرار، ولا احتمال رقمي غير معاير، ولا ادعاء بهوية كبار المتعاملين.
"""
from __future__ import annotations
import json
import math
import statistics
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

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
    if recommendation is not None and not recommendation.empty and "الرمز" in recommendation.columns and "الرمز" in result.columns:
        keep = [c for c in ["الرمز", "حالة التوصية", "طريقة التعامل", "مستوى الخطر", "حالة الثقة", "السيناريو الأساسي", "درجة السيناريو", "درجة الدليل", "عدم اليقين", "عقوبة الفخ"] if c in recommendation.columns]
        if keep:
            result = result.merge(recommendation[keep].drop_duplicates("الرمز"), on="الرمز", how="left")
    result["حالة التكامل"] = result.get("حالة التوصية", pd.Series("غير مؤكدة", index=result.index)).fillna("غير مؤكدة")
    result["احتمال التكامل"] = None
    result["مصرح بالإنتاج"] = False
    result["ادعاء هوية"] = False
    return result


# ------------------------- الواجهة -------------------------
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

with st.sidebar:
    st.header("مركز التحكم")
    الملف = st.file_uploader("أدخل ملف بيانات الجلسة", type=["csv", "json"])
    الوضع = st.selectbox("اختر طريقة العرض", ["التحليل الأساسي", "الأدلة والتوصية", "التكامل مع قناص السيولة"])
    st.caption("الإنتاج يظل محكومًا بجودة البيانات والمعايرة والاختبارات وبوابة المخاطر. لا توجد احتمالات مصطنعة.")

if الملف is None:
    st.info("أدخل ملفًا تاريخيًا أو لحظيًا لتشغيل التحليل. لن يتم اختراع بيانات عند غيابها.")
    st.subheader("خريطة منظومة كوانتوم فيكتوري")
    for col, name in zip(st.columns(5), ["المصادر", "بنك كوانتوم فيكتوري", "مخزن كوانتوم فيكتوري", "عقل كوانتوم فيكتوري", "موقع كوانتوم فيكتوري"]):
        col.markdown(f'<div class="qv-card"><b>{name}</b><br>مرتبط ضمن المنظومة</div>', unsafe_allow_html=True)
    st.stop()

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

st.subheader("بوابة البيانات")
st.write(f"عدد الصفوف المستلمة: **{len(df):,}**")

if الوضع == "التحليل الأساسي":
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
        st.dataframe(rec, use_container_width=True)

else:
    st.subheader("🐋 التكامل مع قناص السيولة")
    bridge = بناء_جسر_الأدلة(df)
    if bridge.empty:
        st.warning("لم تصل أدلة القناص بالشكل المطلوب لهذه الدفعة.")
    else:
        rec = بناء_التوصية(df)
        integrated = دمج_الأدلة_والقناص(df, rec)
        st.dataframe(integrated, use_container_width=True)

st.divider()
st.caption("قاعدة كوانتوم فيكتوري: الدليل قبل القرار — لا توصية بلا بيانات كافية، ولا احتمال بلا معايرة، ولا قرار يتجاوز بوابة المخاطر.")
