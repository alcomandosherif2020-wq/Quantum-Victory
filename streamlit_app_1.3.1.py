# -*- coding: utf-8 -*-
"""Quantum Victory — File-First EGX historical session workspace.
No live-market claim. Uploaded/downloaded session files are the primary evidence.
"""
from __future__ import annotations
import json, os, shutil, tempfile
from pathlib import Path
import pandas as pd
import streamlit as st

from qv_offline_session_archive import QVOfflineSessionArchive

ROOT = Path(__file__).resolve().parent
WORK = ROOT / "QV-OFFLINE-SESSIONS"
INBOX = WORK / "inbox"
ARCHIVE = WORK / "archive"
INDEX = WORK / "index"
for p in (INBOX, ARCHIVE, INDEX):
    p.mkdir(parents=True, exist_ok=True)

st.set_page_config(page_title="كوانتوم فيكتوري — المخزن والأرشيف", page_icon="📊", layout="wide")

st.title("كوانتوم فيكتوري")
st.caption("التحليل التاريخي للجلسات — FILE_FIRST / OFFLINE — دون ادعاء بيانات حية")

with st.sidebar:
    st.header("حوكمة التشغيل")
    st.success("وضع التشغيل: OFFLINE_FILE_FIRST")
    st.info("المصدر الأساسي: ملفات جلسات التداول الرسمية التي تم تنزيلها وحفظها.")
    st.warning("الإنتاج/التداول الحي غير مصرح به في هذه المرحلة.")
    st.write("live_data_claim = False")
    st.write("production_authorized = False")
    st.write("fail_closed = True")

st.subheader("1) إدخال ملفات جلسات التداول")
uploads = st.file_uploader(
    "ارفع ملفات الجلسات الرسمية بعد تنزيلها من المصدر المعتمد",
    type=["csv", "xlsx", "xls", "json", "parquet", "txt", "pdf"],
    accept_multiple_files=True,
)

if uploads:
    for up in uploads:
        target = INBOX / Path(up.name).name
        target.write_bytes(up.getbuffer())
    st.success(f"تم استقبال {len(uploads)} ملف/ملفات في صندوق الاستلام.")

col1, col2 = st.columns(2)
with col1:
    if st.button("📥 أرشفة وفهرسة وتحليل الملفات", type="primary", use_container_width=True):
        archive = QVOfflineSessionArchive(inbox=INBOX, archive=ARCHIVE, index=INDEX)
        report, data = archive.ingest()
        st.session_state["qv_report"] = report
        st.session_state["qv_data"] = data
        st.rerun()
with col2:
    if st.button("🔄 إعادة تحميل المخزن", use_container_width=True):
        archive = QVOfflineSessionArchive(inbox=INBOX, archive=ARCHIVE, index=INDEX)
        report, data = archive.ingest()
        st.session_state["qv_report"] = report
        st.session_state["qv_data"] = data
        st.rerun()

report = st.session_state.get("qv_report")
data = st.session_state.get("qv_data", pd.DataFrame())

if report:
    st.subheader("2) حالة المخزن والأرشيف")
    a,b,c,d = st.columns(4)
    a.metric("الملفات المكتشفة", report.get("files_discovered", 0))
    b.metric("الصفوف القابلة للتحليل", report.get("tabular_rows", 0))
    c.metric("الإخفاقات", len(report.get("failures", [])))
    d.metric("الوضع", report.get("mode", "OFFLINE_FILE_FIRST"))

    st.code(json.dumps({
        "archive_sha256": report.get("archive_sha256"),
        "live_data_claim": report.get("live_data_claim"),
        "production_authorized": report.get("production_authorized"),
        "fail_closed": report.get("fail_closed"),
    }, ensure_ascii=False, indent=2), language="json")

    if report.get("failures"):
        st.error("ملفات لم تُحلل جدوليًا؛ تم الاحتفاظ بها كأدلة أصلية وعدم اختلاق بيانات منها.")
        st.json(report["failures"])

if isinstance(data, pd.DataFrame) and not data.empty:
    st.subheader("3) البيانات الموحّدة — Historical Evidence")
    st.caption("هذه البيانات مشتقة من الملفات المؤرشفة وتحمل provenance صريحًا.")
    st.dataframe(data.head(1000), use_container_width=True)

    st.subheader("4) ملخص الجلسة")
    symbols = data["symbol"].nunique() if "symbol" in data.columns else 0
    sessions = data["session_date"].dropna().astype(str).nunique() if "session_date" in data.columns else 0
    x,y = st.columns(2)
    x.metric("عدد الأدوات", symbols)
    y.metric("عدد الجلسات", sessions)

st.subheader("5) المبدأ التشغيلي")
st.markdown(
    """
- **الملف الرسمي المحفوظ هو الدليل الأساسي للجلسة.**
- يتم حفظ الأصل وبصمته SHA-256 قبل التحليل.
- يتم إنشاء نسخة موحّدة للتحليل دون إتلاف الأصل.
- المصادر الخارجية تستخدم للمقارنة والإثراء والمصالحة، وليست بديلًا عن دليل الجلسة.
- لا يتم تحويل نتيجة تاريخية إلى ادعاء Live.
- لا يتم فتح اعتماد إنتاجي من خلال هذه الواجهة.
"""
)
