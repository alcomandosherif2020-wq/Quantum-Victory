from __future__ import annotations
import json, sqlite3, hashlib
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Any

ENGINE_VERSION = "QV-REVIEW-ENGINE-1.0"

@dataclass
class Recommendation:
    session_date: str
    review_date: str
    symbol: str
    direction: str
    entry_low: Optional[float] = None
    entry_high: Optional[float] = None
    target1: Optional[float] = None
    target2: Optional[float] = None
    stop: Optional[float] = None
    reference_price: Optional[float] = None
    qv_grade: Optional[str] = None
    qv_score: Optional[float] = None
    neffus_score: Optional[float] = None
    source: str = "Quantum Victory"
    recommendation_id: Optional[str] = None
    notes: str = ""

class QVRecommendationReviewEngine:
    """Persistent next-session recommendation recorder and outcome grader.

    Design rule: the recommendation is frozen at issuance time. Later market
    data can grade it but cannot rewrite it. Daily OHLC alone cannot establish
    target-before-stop ordering when both levels occur in the same candle;
    that case is explicitly marked AMBIGUOUS until intraday data is supplied.
    """
    def __init__(self, db_path: str = "qv_recommendation_review.sqlite3"):
        self.db_path = str(db_path)
        self._init_db()

    def _connect(self):
        return sqlite3.connect(self.db_path)

    def _init_db(self):
        with self._connect() as c:
            c.executescript("""
            CREATE TABLE IF NOT EXISTS recommendations (
                recommendation_id TEXT PRIMARY KEY,
                session_date TEXT NOT NULL,
                review_date TEXT NOT NULL,
                symbol TEXT NOT NULL,
                direction TEXT NOT NULL,
                entry_low REAL,
                entry_high REAL,
                target1 REAL,
                target2 REAL,
                stop REAL,
                reference_price REAL,
                qv_grade TEXT,
                qv_score REAL,
                neffus_score REAL,
                source TEXT,
                notes TEXT,
                frozen_at TEXT NOT NULL,
                fingerprint TEXT NOT NULL UNIQUE
            );
            CREATE TABLE IF NOT EXISTS outcomes (
                recommendation_id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                activation_price REAL,
                activation_seen INTEGER NOT NULL DEFAULT 0,
                target1_hit INTEGER NOT NULL DEFAULT 0,
                target2_hit INTEGER NOT NULL DEFAULT 0,
                stop_hit INTEGER NOT NULL DEFAULT 0,
                ambiguous INTEGER NOT NULL DEFAULT 0,
                pnl_pct REAL,
                directional_hit INTEGER,
                directional_return_pct REAL,
                r_multiple REAL,
                outcome_at TEXT NOT NULL,
                evidence_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_at TEXT NOT NULL,
                event TEXT NOT NULL,
                recommendation_id TEXT,
                details_json TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_rec_review_date ON recommendations(review_date);
            CREATE INDEX IF NOT EXISTS idx_rec_session_date ON recommendations(session_date);
            """)

    @staticmethod
    def _fingerprint(payload: dict) -> str:
        return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()

    @staticmethod
    def _direction(direction: str) -> str:
        d = str(direction).upper().strip()
        if d in {"BUY", "LONG", "UP", "شراء", "صاعد", "موجب"}: return "LONG"
        if d in {"SELL", "SHORT", "DOWN", "بيع", "هابط", "سالب"}: return "SHORT"
        return "NEUTRAL"

    def freeze_recommendations(self, recommendations: list[dict | Recommendation]) -> dict:
        """Freeze today's recommendations so tomorrow's review has a fixed baseline."""
        inserted = 0
        rejected = 0
        ids = []
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as c:
            for item in recommendations:
                r = item if isinstance(item, Recommendation) else Recommendation(**item)
                r.direction = self._direction(r.direction)
                payload = asdict(r)
                rid = r.recommendation_id or self._fingerprint(payload)[:20]
                payload["recommendation_id"] = rid
                fp = self._fingerprint(payload)
                try:
                    c.execute("""INSERT INTO recommendations
                    (recommendation_id,session_date,review_date,symbol,direction,entry_low,entry_high,target1,target2,stop,
                     reference_price,qv_grade,qv_score,neffus_score,source,notes,frozen_at,fingerprint)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (rid,r.session_date,r.review_date,r.symbol.upper(),r.direction,r.entry_low,r.entry_high,r.target1,r.target2,r.stop,
                     r.reference_price,r.qv_grade,r.qv_score,r.neffus_score,r.source,r.notes,now,fp))
                    inserted += 1; ids.append(rid)
                    c.execute("INSERT INTO audit_log(event_at,event,recommendation_id,details_json) VALUES(?,?,?,?)",
                              (now,"RECOMMENDATION_FROZEN",rid,json.dumps(payload,ensure_ascii=False,sort_keys=True)))
                except sqlite3.IntegrityError:
                    rejected += 1
        return {"engine":ENGINE_VERSION,"inserted":inserted,"already_frozen_or_rejected":rejected,"ids":ids}

    @staticmethod
    def _activation(direction, low, high, day):
        if low is None and high is None:
            return None
        if day is None: return None
        lo = float(low if low is not None else high)
        hi = float(high if high is not None else low)
        if direction == "LONG":
            if float(day.get("low")) <= hi and float(day.get("high")) >= lo:
                return max(lo, min(hi, float(day.get("open", lo))))
        elif direction == "SHORT":
            if float(day.get("high")) >= lo and float(day.get("low")) <= hi:
                return min(hi, max(lo, float(day.get("open", hi))))
        return None

    def grade_one(self, recommendation_id: str, day: dict, intraday: Optional[list[dict]] = None) -> dict:
        with self._connect() as c:
            row = c.execute("SELECT * FROM recommendations WHERE recommendation_id=?", (recommendation_id,)).fetchone()
        if not row: raise KeyError(recommendation_id)
        cols = [d[1] for d in sqlite3.connect(self.db_path).execute("PRAGMA table_info(recommendations)").fetchall()]
        rec = dict(zip(cols,row))
        direction = rec["direction"]
        activation = self._activation(direction, rec["entry_low"], rec["entry_high"], day)
        status = "NOT_ACTIVATED"
        target1_hit = target2_hit = stop_hit = ambiguous = False
        pnl_pct = r_multiple = None
        evidence = {"day": day, "intraday_used": bool(intraday)}

        def grade_sequence(points):
            nonlocal status,target1_hit,target2_hit,stop_hit,ambiguous,pnl_pct,r_multiple
            for p in points:
                hi, lo = float(p["high"]), float(p["low"])
                t1, t2, st = rec["target1"], rec["target2"], rec["stop"]
                if direction == "LONG":
                    hit_t1 = t1 is not None and hi >= t1
                    hit_t2 = t2 is not None and hi >= t2
                    hit_st = st is not None and lo <= st
                else:
                    hit_t1 = t1 is not None and lo <= t1
                    hit_t2 = t2 is not None and lo <= t2
                    hit_st = st is not None and hi >= st
                if hit_t1: target1_hit = True
                if hit_t2: target2_hit = True
                if hit_st: stop_hit = True
                if hit_t1 and hit_st and not intraday:
                    ambiguous = True; status = "AMBIGUOUS"; return
                if hit_t1:
                    status = "SUCCESS"
                    exitp = float(t1)
                    base = float(activation or rec["reference_price"] or day["open"])
                    pnl_pct = (exitp/base-1)*100 if direction=="LONG" else (base/exitp-1)*100
                    if rec["stop"] is not None and rec["entry_low"] is not None:
                        risk = abs(float(rec["entry_low"])-float(rec["stop"]))
                        reward = abs(exitp-float(rec["entry_low"]))
                        r_multiple = reward/risk if risk else None
                    return
                if hit_st:
                    status = "FAIL"
                    exitp = float(st)
                    base = float(activation or rec["reference_price"] or day["open"])
                    pnl_pct = (exitp/base-1)*100 if direction=="LONG" else (base/exitp-1)*100
                    return
            if status not in {"SUCCESS","FAIL","AMBIGUOUS"}:
                status = "UNRESOLVED"

        if activation is not None:
            if intraday:
                grade_sequence(intraday)
            else:
                grade_sequence([day])
        evidence["activation_price"] = activation
        directional_hit = None
        directional_return_pct = None
        if rec["reference_price"] is not None and day.get("close") is not None and direction in {"LONG", "SHORT"}:
            ref=float(rec["reference_price"]); close=float(day["close"])
            directional_return_pct = ((close/ref)-1)*100 if direction=="LONG" else ((ref/close)-1)*100
            directional_hit = int(directional_return_pct > 0)
            if status == "NOT_ACTIVATED":
                status = "DIRECTIONAL_HIT" if directional_hit else "DIRECTIONAL_MISS"
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as c:
            c.execute("""INSERT INTO outcomes(recommendation_id,status,activation_price,activation_seen,target1_hit,target2_hit,stop_hit,ambiguous,pnl_pct,directional_hit,directional_return_pct,r_multiple,outcome_at,evidence_json)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                       ON CONFLICT(recommendation_id) DO UPDATE SET status=excluded.status,activation_price=excluded.activation_price,
                       activation_seen=excluded.activation_seen,target1_hit=excluded.target1_hit,target2_hit=excluded.target2_hit,
                       stop_hit=excluded.stop_hit,ambiguous=excluded.ambiguous,pnl_pct=excluded.pnl_pct,r_multiple=excluded.r_multiple,
                       directional_hit=excluded.directional_hit,directional_return_pct=excluded.directional_return_pct,r_multiple=excluded.r_multiple,
                outcome_at=excluded.outcome_at,evidence_json=excluded.evidence_json""",
                      (recommendation_id,status,activation,int(activation is not None),int(target1_hit),int(target2_hit),int(stop_hit),int(ambiguous),pnl_pct,directional_hit,directional_return_pct,r_multiple,now,json.dumps(evidence,ensure_ascii=False)))
            c.execute("INSERT INTO audit_log(event_at,event,recommendation_id,details_json) VALUES(?,?,?,?)",
                      (now,"RECOMMENDATION_GRADED",recommendation_id,json.dumps(evidence,ensure_ascii=False)))
        return {"recommendation_id":recommendation_id,"symbol":rec["symbol"],"status":status,"activation_price":activation,
                "target1_hit":target1_hit,"target2_hit":target2_hit,"stop_hit":stop_hit,"ambiguous":ambiguous,"pnl_pct":pnl_pct,"directional_hit":directional_hit,"directional_return_pct":directional_return_pct,"r_multiple":r_multiple}

    def review_session(self, review_date: str, market_data: dict[str,dict], intraday_data: Optional[dict[str,list[dict]]] = None) -> dict:
        with self._connect() as c:
            recs = c.execute("SELECT recommendation_id,symbol FROM recommendations WHERE review_date=?", (review_date,)).fetchall()
        results=[]
        for rid,symbol in recs:
            day = market_data.get(symbol.upper())
            if not day:
                results.append({"recommendation_id":rid,"symbol":symbol,"status":"NO_DATA"})
                continue
            results.append(self.grade_one(rid, day, (intraday_data or {}).get(symbol.upper())))
        return self._aggregate(review_date, results)

    def _aggregate(self, review_date: str, results: list[dict]) -> dict:
        valid=[r for r in results if r["status"] != "NO_DATA"]
        activated=[r for r in valid if r["status"] in {"SUCCESS","FAIL","UNRESOLVED","AMBIGUOUS"} and r.get("activation_price") is not None]
        wins=[r for r in activated if r["status"]=="SUCCESS"]
        losses=[r for r in activated if r["status"]=="FAIL"]
        unresolved=[r for r in activated if r["status"]=="UNRESOLVED"]
        ambiguous=[r for r in activated if r["status"]=="AMBIGUOUS"]
        directional=[r for r in valid if r.get("directional_hit") is not None]
        directional_wins=[r for r in directional if r.get("directional_hit")==1]
        pnl=[r["pnl_pct"] for r in activated if r.get("pnl_pct") is not None]
        rs=[r["r_multiple"] for r in wins if r.get("r_multiple") is not None]
        hit_all=(len(wins)/len(valid)*100) if valid else None
        hit_activated=(len(wins)/len(activated)*100) if activated else None
        return {
            "engine":ENGINE_VERSION,"review_date":review_date,"total_recommendations":len(results),"with_market_data":len(valid),
            "activated":len(activated),"not_activated":len(valid)-len(activated),"success":len(wins),"fail":len(losses),
            "unresolved":len(unresolved),"ambiguous":len(ambiguous),
            "success_rate_all_pct":round(hit_all,2) if hit_all is not None else None,
            "success_rate_activated_pct":round(hit_activated,2) if hit_activated is not None else None,
            "directional_sample":len(directional),
            "directional_success_rate_pct":round(len(directional_wins)/len(directional)*100,2) if directional else None,
            "avg_pnl_pct":round(sum(pnl)/len(pnl),4) if pnl else None,
            "avg_r_multiple":round(sum(rs)/len(rs),4) if rs else None,
            "results":results,
            "rule":"لا يُحسب النجاح من مجرد ارتفاع السهم؛ يجب تفعيل منطقة الدخول ثم تحقق الهدف قبل الوقف. تعارض الهدف/الوقف داخل شمعة يومية واحدة = AMBIGUOUS دون بيانات intraday."
        }

    def dashboard(self) -> dict:
        with self._connect() as c:
            rows=c.execute("""SELECT review_date, COUNT(*) total,
                SUM(CASE WHEN o.status='SUCCESS' THEN 1 ELSE 0 END) success,
                SUM(CASE WHEN o.status='FAIL' THEN 1 ELSE 0 END) fail,
                SUM(CASE WHEN o.status='NOT_ACTIVATED' THEN 1 ELSE 0 END) not_activated,
                SUM(CASE WHEN o.status='AMBIGUOUS' THEN 1 ELSE 0 END) ambiguous
                FROM recommendations r LEFT JOIN outcomes o ON r.recommendation_id=o.recommendation_id
                GROUP BY review_date ORDER BY review_date DESC""").fetchall()
        return {"engine":ENGINE_VERSION,"sessions":[dict(zip(["review_date","total","success","fail","not_activated","ambiguous"],r)) for r in rows]}


def حفظ_توصيات_اليوم(التوصيات, تاريخ_الجلسة, تاريخ_المراجعة, db_path="qv_recommendation_review.sqlite3"):
    """واجهة عربية لإدخال توصيات QV المجمدة قبل الجلسة التالية."""
    normalized=[]
    for x in التوصيات:
        x=dict(x)
        x["session_date"]=تاريخ_الجلسة; x["review_date"]=تاريخ_المراجعة
        normalized.append(x)
    return QVRecommendationReviewEngine(db_path).freeze_recommendations(normalized)


def مراجعة_جلسة_الغد(تاريخ_المراجعة, بيانات_السوق, بيانات_لحظية=None, db_path="qv_recommendation_review.sqlite3"):
    return QVRecommendationReviewEngine(db_path).review_session(تاريخ_المراجعة, بيانات_السوق, بيانات_لحظية)

def تجميد_من_جدول_التوصيات(df, تاريخ_الجلسة, تاريخ_المراجعة, db_path="qv_recommendation_review.sqlite3"):
    """يحفظ توصيات DataFrame كما صدرت؛ لا يخترع مستويات غير موجودة."""
    if df is None or len(df) == 0:
        return {"engine":ENGINE_VERSION,"inserted":0,"warning":"جدول التوصيات فارغ"}
    def pick(row, names):
        for n in names:
            if n in row and row[n] not in (None, "", "nan"):
                return row[n]
        return None
    rows=[]
    for _, row in df.iterrows():
        symbol=pick(row,["الرمز","symbol","Symbol"])
        if not symbol: continue
        rows.append({
            "session_date":تاريخ_الجلسة,"review_date":تاريخ_المراجعة,"symbol":str(symbol).upper(),
            "direction":pick(row,["الاتجاه","اتجاه التوصية","direction","side"]) or "NEUTRAL",
            "entry_low":pick(row,["دخول منخفض","entry_low","entry_min","منطقة الدخول من"]),
            "entry_high":pick(row,["دخول مرتفع","entry_high","entry_max","منطقة الدخول إلى"]),
            "target1":pick(row,["الهدف الأول","target1","target","هدف سعري"]),
            "target2":pick(row,["الهدف الثاني","target2"]),
            "stop":pick(row,["وقف الخسارة","stop","stop_loss"]),
            "reference_price":pick(row,["السعر المرجعي","السعر","reference_price","close"]),
            "qv_grade":pick(row,["تصنيف QV","QV grade","الدرجة"]),
            "qv_score":pick(row,["درجة QV","QV score"]),
            "neffus_score":pick(row,["درجة Neffus","Neffus score"]),
            "source":"Quantum Victory",
            "notes":str(pick(row,["ملاحظات","notes"]) or "")
        })
    return QVRecommendationReviewEngine(db_path).freeze_recommendations(rows)
