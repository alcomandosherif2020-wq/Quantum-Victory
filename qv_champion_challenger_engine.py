# -*- coding: utf-8 -*-
"""Quantum Victory Champion/Challenger — OOS-only comparison layer.

Design rules:
- Candidate decisions are frozen at decision time.
- Outcomes are attached only after the actual review session.
- Comparisons use the same frozen cases (paired evaluation) whenever possible.
- Ambiguous/unresolved cases are excluded from binary execution success metrics.
- No automatic promotion: the engine recommends a challenger; an independent gate must approve promotion.
"""
from __future__ import annotations
import hashlib, json, sqlite3, math
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Iterable

ENGINE_VERSION = "QV-CHAMPION-CHALLENGER-1.0"

class QVChampionChallengerEngine:
    def __init__(self, db_path="data/qv_recommendation_review.sqlite3", min_oos=30):
        self.db_path=str(db_path); self.min_oos=int(min_oos)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self):
        c=sqlite3.connect(self.db_path); c.row_factory=sqlite3.Row; return c

    def _init_db(self):
        with self._connect() as c:
            c.executescript("""
            CREATE TABLE IF NOT EXISTS qv_cc_candidates (
                candidate_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                version TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('CHAMPION','CHALLENGER')),
                frozen_at TEXT NOT NULL,
                active INTEGER NOT NULL DEFAULT 1,
                fingerprint TEXT NOT NULL UNIQUE
            );
            CREATE TABLE IF NOT EXISTS qv_cc_cases (
                case_id TEXT PRIMARY KEY,
                candidate_id TEXT NOT NULL REFERENCES qv_cc_candidates(candidate_id),
                recommendation_id TEXT,
                session_date TEXT NOT NULL,
                review_date TEXT NOT NULL,
                symbol TEXT NOT NULL,
                score REAL,
                outcome TEXT,
                pnl_pct REAL,
                r_multiple REAL,
                outcome_at TEXT,
                frozen_at TEXT NOT NULL,
                UNIQUE(candidate_id, recommendation_id)
            );
            CREATE TABLE IF NOT EXISTS qv_cc_decisions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                evaluated_at TEXT NOT NULL,
                champion_id TEXT NOT NULL,
                challenger_id TEXT NOT NULL,
                as_of_session TEXT,
                decision TEXT NOT NULL,
                reason TEXT NOT NULL,
                metrics_json TEXT NOT NULL
            );
            """)

    @staticmethod
    def _fp(payload):
        return hashlib.sha256(json.dumps(payload,ensure_ascii=False,sort_keys=True,default=str).encode()).hexdigest()

    def register_candidate(self, name, version, role="CHALLENGER", candidate_id=None):
        role=str(role).upper()
        if role not in {"CHAMPION","CHALLENGER"}: raise ValueError("role must be CHAMPION or CHALLENGER")
        now=datetime.now(timezone.utc).isoformat()
        cid=candidate_id or self._fp({"name":name,"version":version,"frozen_at":now})[:24]
        payload={"candidate_id":cid,"name":str(name),"version":str(version),"role":role,"frozen_at":now}
        with self._connect() as c:
            if role=="CHAMPION":
                c.execute("UPDATE qv_cc_candidates SET role='CHALLENGER' WHERE role='CHAMPION' AND active=1")
            c.execute("INSERT OR IGNORE INTO qv_cc_candidates(candidate_id,name,version,role,frozen_at,active,fingerprint) VALUES(?,?,?,?,?,?,?)",
                      (cid,str(name),str(version),role,now,1,self._fp(payload)))
        return payload

    def freeze_cases(self, candidate_id, cases: Iterable[dict]):
        now=datetime.now(timezone.utc).isoformat(); count=0
        with self._connect() as c:
            cand=c.execute("SELECT candidate_id FROM qv_cc_candidates WHERE candidate_id=? AND active=1",(candidate_id,)).fetchone()
            if not cand: raise ValueError("unknown/inactive candidate")
            for x in cases:
                required=["session_date","review_date","symbol"]
                if any(not x.get(k) for k in required): raise ValueError("case requires session_date, review_date, symbol")
                case_id=str(x.get("case_id") or self._fp({"candidate_id":candidate_id,**x})[:32])
                c.execute("""INSERT OR IGNORE INTO qv_cc_cases(case_id,candidate_id,recommendation_id,session_date,review_date,symbol,score,outcome,pnl_pct,r_multiple,outcome_at,frozen_at)
                             VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                          (case_id,candidate_id,x.get("recommendation_id"),str(x["session_date"]),str(x["review_date"]),str(x["symbol"]).upper(),x.get("score"),None,None,None,None,now))
                count+=1
        return {"candidate_id":candidate_id,"frozen":count,"frozen_at":now}

    def record_outcome(self, candidate_id, recommendation_id, outcome, pnl_pct=None, r_multiple=None, outcome_at=None):
        outcome=str(outcome).upper()
        if outcome not in {"SUCCESS","FAIL","AMBIGUOUS","UNRESOLVED","DIRECTIONAL_HIT","DIRECTIONAL_MISS"}:
            raise ValueError("invalid outcome")
        with self._connect() as c:
            c.execute("""UPDATE qv_cc_cases SET outcome=?,pnl_pct=?,r_multiple=?,outcome_at=?
                         WHERE candidate_id=? AND recommendation_id=?""",
                      (outcome,pnl_pct,r_multiple,outcome_at or datetime.now(timezone.utc).isoformat(),candidate_id,recommendation_id))
            if c.total_changes==0: raise ValueError("case not found")
        return {"candidate_id":candidate_id,"recommendation_id":recommendation_id,"outcome":outcome}

    @staticmethod
    def _max_drawdown(rs):
        eq=0.0; peak=0.0; mdd=0.0
        for r in rs:
            eq += float(r or 0.0); peak=max(peak,eq); mdd=min(mdd,eq-peak)
        return round(abs(mdd),6)

    def _metrics(self, rows):
        valid=[dict(r) for r in rows if r["outcome"] in ("SUCCESS","FAIL")]
        wins=sum(r["outcome"]=="SUCCESS" for r in valid); n=len(valid)
        pnls=[float(r["pnl_pct"]) for r in valid if r["pnl_pct"] is not None]
        rs=[float(r["r_multiple"]) for r in valid if r["r_multiple"] is not None]
        gross_w=sum(x for x in pnls if x>0); gross_l=abs(sum(x for x in pnls if x<0))
        return {"sample":n,"success_rate_pct":round(wins/n*100,2) if n else None,
                "avg_pnl_pct":round(sum(pnls)/len(pnls),4) if pnls else None,
                "avg_r":round(sum(rs)/len(rs),4) if rs else None,
                "profit_factor":round(gross_w/gross_l,4) if gross_l else (None if not gross_w else math.inf),
                "max_drawdown_pct":self._max_drawdown(pnls) if pnls else None}

    def compare(self, champion_id, challenger_id, as_of_session=None, require_paired=True):
        with self._connect() as c:
            where=" AND date(c.review_date)<=date(?)" if as_of_session else ""
            champs_params=(champion_id,)+(as_of_session,) if as_of_session else (champion_id,)
            chall_params=(challenger_id,)+(as_of_session,) if as_of_session else (challenger_id,)
            champs=[dict(r) for r in c.execute("SELECT * FROM qv_cc_cases c WHERE c.candidate_id=? AND c.outcome IS NOT NULL"+where,champs_params).fetchall()]
            challs=[dict(r) for r in c.execute("SELECT * FROM qv_cc_cases c WHERE c.candidate_id=? AND c.outcome IS NOT NULL"+where,chall_params).fetchall()]
        paired=[]
        cm={r.get("recommendation_id") or r["case_id"]:r for r in champs}; xm={r.get("recommendation_id") or r["case_id"]:r for r in challs}
        for k in sorted(set(cm)&set(xm)):
            a,b=cm[k],xm[k]
            if a["outcome"] in ("SUCCESS","FAIL") and b["outcome"] in ("SUCCESS","FAIL"):
                paired.append((a,b))
        cmet=self._metrics(champs); xmet=self._metrics(challs)
        paired_wins=sum(b["outcome"]=="SUCCESS" and a["outcome"]=="FAIL" for a,b in paired)
        paired_losses=sum(b["outcome"]=="FAIL" and a["outcome"]=="SUCCESS" for a,b in paired)
        n=min(cmet["sample"],xmet["sample"]) if require_paired else min(cmet["sample"],xmet["sample"])
        sufficient=n>=self.min_oos
        improvement=(xmet["success_rate_pct"] is not None and cmet["success_rate_pct"] is not None and xmet["success_rate_pct"]>cmet["success_rate_pct"])
        avg_r_ok=(xmet["avg_r"] is None or cmet["avg_r"] is None or xmet["avg_r"]>=cmet["avg_r"])
        dd_ok=(xmet["max_drawdown_pct"] is None or cmet["max_drawdown_pct"] is None or xmet["max_drawdown_pct"]<=cmet["max_drawdown_pct"])
        decision="QUALIFIED_CHALLENGER" if sufficient and improvement and avg_r_ok and dd_ok else "RETAIN_CHAMPION"
        reason=("العينة OOS كافية، والتحسن في النجاح مع عدم تدهور R/السحب الأقصى؛ يلزم اعتماد مستقل قبل أي ترقية." if decision=="QUALIFIED_CHALLENGER"
                else "لم يجتز المتحدي بوابات المقارنة الحالية؛ يبقى الـChampion دون ترقية تلقائية.")
        out={"engine":ENGINE_VERSION,"champion_id":champion_id,"challenger_id":challenger_id,"as_of_session":as_of_session,
             "decision":decision,"reason":reason,"champion":cmet,"challenger":xmet,
             "paired_sample":len(paired),"paired_challenger_wins":paired_wins,"paired_challenger_losses":paired_losses,
             "minimum_oos":self.min_oos,"oos_gate":sufficient,"automatic_promotion":False}
        with self._connect() as c:
            c.execute("INSERT INTO qv_cc_decisions(evaluated_at,champion_id,challenger_id,as_of_session,decision,reason,metrics_json) VALUES(?,?,?,?,?,?,?)",
                      (datetime.now(timezone.utc).isoformat(),champion_id,challenger_id,as_of_session,decision,reason,json.dumps(out,ensure_ascii=False,sort_keys=True)))
        return out

    def status(self):
        with self._connect() as c:
            candidates=[dict(r) for r in c.execute("SELECT * FROM qv_cc_candidates WHERE active=1 ORDER BY role,name").fetchall()]
            latest=c.execute("SELECT * FROM qv_cc_decisions ORDER BY id DESC LIMIT 1").fetchone()
        return {"engine":ENGINE_VERSION,"candidates":candidates,"latest_decision":dict(latest) if latest else None,
                "promotion":"محجوبة — لا ترقية تلقائية"}
