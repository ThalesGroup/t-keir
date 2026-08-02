# Enterprise Intelligence Platform — Demo Scenario
## "Project MERIDIAN" — NEXUS ENERGY HOLDINGS Investigation

**Classification:** CONFIDENTIAL — C-SUITE  
**Window:** 28 June → 28 July 2026  
**Focal entity:** NEXUS ENERGY HOLDINGS (NEH) — commodity trading conglomerate, Cayman Islands  
**Real case grounding:** Glencore DOJ 2022 · Vitol DOJ 2020 · 1MDB DOJ 2016–23 · Wirecard BaFin 2020 · FinCEN Files ICIJ 2020

---

## The Premise

NEXUS ENERGY HOLDINGS is a mid-size commodity trading house headquartered in Geneva, with subsidiaries in Dubai, Singapore, and Lagos. Over thirty days, five independent anomalies have surfaced across trade monitoring systems, open sources, and confidential human sources — all touching NEH or entities in its counterparty network.

The platform must let four C-suite executives query that corpus from their own perspective, with their own personal index, without each having to read everything.

---

## Persona Architecture

| Persona | Role | Personal Index | Primary Output |
|---|---|---|---|
| **CTO** | Platform Engineering — corpus prep & ontology governance | — | Ingestion + ontology graph |
| **CDO** | Chief Data Officer — multi-source intelligence fusion | Entity tracks, risk assessments, source evaluations | RISK_SUMMARY |
| **CEO** | Chief Executive Officer — board-level situational awareness | Dashboard logs, due diligence reports, entity contacts | BOARD_SITREP |
| **CISO** | Chief Information Security Officer — confidential source management | Source tasking, access evaluations, field reports | FIELD_REPORT |
| **CFO** | Chief Financial Officer — decision authority | Decision logs, CCIR, policy cards, capital exposure | CFO_DECISION_BRIEFING |

---

## KRI Register (Key Risk Indicators)

| KRI | Definition | Real-world anchor |
|---|---|---|
| **KRI-01** | Financial fraud & asset concealment | Wirecard €1.9B phantom receivables (2020) |
| **KRI-02** | Sanctions evasion — reporting gaps, entity obfuscation | Vitol OFAC DPA — Iranian crude re-documented as Iraqi (2020) |
| **KRI-03** | Bribery & corruption — improper payments to officials | Glencore $180M+ across Nigeria, DRC, Venezuela (2022) |
| **KRI-04** | AML layering — multi-jurisdiction fund movement | FinCEN Files — SWIFT MT202COV misuse (2020) |
| **KRI-05** | Commodity misreporting — cargo document falsification | Vitol false origin certificates; Unaoil cargo fraud |
| **KRI-06** | Market manipulation — round-trip trades, benchmark fixing | Glencore CFTC fuel oil derivatives, $341M settlement (2022) |

---

# ACT 0 — Corpus Preparation (CTO)

**Actor:** CTO — Platform Engineering  
**Feature:** Source selection · pre-ingestion description · document ingestion · merged ontology graph

The CTO opens the Corpus Indexation Workbench and stages three ingestion units:

```
/enterprise/corpus/
├── enterprise_intelligence_corpus.json    ~8 MB   [not indexed]
│     ↳ 1,000 records across 3 domains and 3 access tiers
├── enterprise_ontology.yaml               46 KB   [not indexed]
│     ↳ 68 concepts, spine: FINANCIAL_RISK / COMPLIANCE / OPERATIONS
└── legacy_taxonomy.yaml                   12 KB   [not indexed]
     ↳ 18 concepts from prior enterprise risk taxonomy
```

**Access-tier split on ingest:**

```
enterprise_intelligence_corpus.json
  → 289 records: PUBLIC — OPEN SOURCE  (OSINT, social media, court filings, regulatory orders)
  → 380 records: INTERNAL — RESTRICTED (TMS alerts, trade surveillance, internal audit)
  → 331 records: CONFIDENTIAL — C-SUITE (whistleblower reports, informant debriefs, field reports)
```

**Ontology merge — 2 conflicts resolved live:**

```
Conflict 1: "REPORTING_GAP"
  → Under TRADE_REPORTING (financial control view) OR TRANSACTION_ANOMALY (fraud view)?
  Resolve: TRADE_REPORTING → primary; TRANSACTION_ANOMALY → related edge
  Rationale: A gap is first a filing failure; manipulation is an inference.

Conflict 2: "SPV"
  → Under ENTITY_TYPE (structural) OR ACTIVITY_TYPE (misuse)?
  Resolve: ENTITY_TYPE → primary; ACTIVITY_TYPE → related edge
  Rationale: The vehicle is neutral; the abuse is an attribute of use, not type.
```

**CTO closing line:** *"The platform refused to guess. That refusal is what makes the audit trail defensible."*

---

# ACT 1 — Trigger (28 June, 13:34 UTC)

```
TRANSACTION MONITORING ALERT (REPORTING_GAP):
NEXUS ENERGY HOLDINGS — Geneva desk (NEH-G)
Trade reporting to DTCC repository suspended for 18 hours 24 minutes.
Cross-referenced via independent market data: 5 trades executed during gap.
Evaluation: A1 — PRIORITY
```

One event. Three KRIs activated simultaneously:

- **KRI-01** (financial fraud / asset concealment)
- **KRI-02** (sanctions evasion — counterparty screening gap during blackout)  
- **KRI-05** (commodity misreporting — trades unattributable during gap)

Ontology resolves: `REPORTING_GAP → TRADE_REPORTING → MARKET_SURVEILLANCE → FINANCIAL_RISK`

---

# VIEW 1 — CDO (Chief Data Officer)
**Dual-index RAG + ontological entity reasoning**

### Query
> *"Tell me everything the platform knows about Nexus Energy Holdings."*

### Step 1 — Ontology expansion
```
"Nexus Energy Holdings" → surface form of TRADING_HOUSE
  concept_ids: TRADING_HOUSE, SHADOW_NETWORK (?), SANCTIONS_NEXUS (?)
  kri_refs:    KRI-01, KRI-02, KRI-05
  related:     REPORTING_GAP, ROUND_TRIP_TRADE, UNDISCLOSED_TRANSFER
```
Expansion climbs: `COUNTERPARTY_RISK → COUNTERPARTY → MARKET_SURVEILLANCE → FINANCIAL_RISK`

### Step 2 — Dual-index retrieval
| Index | Hits | Breakdown |
|---|---|---|
| Enterprise corpus | 6 | 1× REPORTING_GAP, 2× ROUND_TRIP_TRADE, 2× VELOCITY_SPIKE, 1× COMMODITY_MISMATCH |
| CDO personal index | 21 | 12× ENTITY_TRACK, 9× RISK_ASSESSMENT |

### Step 3 — RISK_SUMMARY generation
```
RISK SUMMARY — NEXUS ENERGY HOLDINGS
Period: 28 Jun – 26 Jul 2026 | Consolidated evaluation: HIGH / CREDIBLE

SITUATION: NEH has accumulated 5 distinct anomaly types over 30 days
(reporting gap ×1, round-trip trade ×2, velocity spike ×2, commodity 
mismatch ×1). Pattern consistent with TTP of SHADOW LEDGER COORDINATOR 
ALPHA network (Glencore-type intermediary bribery structure).

ENTITY TRACKING: Associated entities EOI-005, EOI-014, EOI-019, EOI-016.
Latest CDO assessment: HIGH CONFIDENCE (CDO-202607-0086, 19 Jul).

RECOMMENDATION: KRI-01 and KRI-02 thresholds met. Escalate to CFO.
Suggested CCIR: "Has NEH Geneva executed an undisclosed transfer in 
the last 48 hours?"
```

*Key feature: the LLM does not know — it reads. Every assertion cites a doc_id. The ontology retrieved SHADOW_LEDGER_COORDINATOR_ALPHA without the CDO typing that phrase.*

---

# VIEW 2 — CEO (Chief Executive Officer)
**Jurisdictional retrieval + board briefing aggregation**

### Context
17 July 2026, 07:57 UTC — Compliance Team BRAVO files `CEO-202607-0063`: a due diligence report with finding **COMMODITY_MISMATCH** (SGS inspection certificate inconsistent with Basrah Light specification — consistent with Kharg Island / Iranian crude).

### Query
> *"Summarise the Geneva and Dubai exposure for the 08:00 board brief."*

**Step 1 — Jurisdictional retrieval**  
Filter: `location_refs ∈ {Geneva Trading Hub, Dubai Free Zone, Cayman Islands}` over T-6h to now.

Retrieved:
- `ENT-202607-0978` — ROUND_TRIP_TRADE on NEH-Geneva / Geneva (B2, PRIORITY) ← **corpus**
- `CEO-202607-0063` — DUE_DILIGENCE_REPORT / COMMODITY_MISMATCH ← **personal**
- `CEO-202607-0110` — ENTITY_CONTACT / COMPLIANCE TEAM DISPATCHED ← **personal**

**Step 2 — KRI resolution via ontology**  
`COMMODITY_MISMATCH → ILLICIT_COMMODITY_TRANSFER` links to `KRI_COMMODITY_MISREPORTING` and `KRI_SANCTIONS_EVASION`.

**Board SITREP generated:**
```
BOARD SITREP — GENEVA / DUBAI EXPOSURE | 280800ZJUL26

SITUATION: Elevated risk on NEH (NEH-7742).
  → D-1 17:57Z: Due diligence — COMMODITY_MISMATCH confirmed.
  → D-0 01:58Z: Alert ROUND_TRIP_TRADE / Geneva Trading Hub (B2).
  → 27 Jul 16:57Z: New contact — COMPLIANCE TEAM DISPATCHED.

ENTITIES IN SCOPE: NEH Geneva Trading SA, NEH Dubai Commodities DMCC.
LEGAL EXPOSURE: General Counsel opinion pending (last update T-4h).

KRIs ACTIVATED: KRI-02 (sanctions evasion), KRI-05 (commodity misreporting).
RECOMMENDED ACTION: Escalate to CFO — KRI threshold met.
```

*Key feature: 331 CONFIDENTIAL records withheld server-side (CEO clearance level). The banner says so — the Act 0 classification split is visible and auditable.*

---

# VIEW 3 — CISO (Chief Information Security Officer)
**Collection-gap reasoning + source activation**

### Context
The commodity mismatch is confirmed but no direct proof of sanctioned-crude origin exists. CDO has raised a CCIR: *"Has NEH engaged an OFAC-listed counterparty during the reporting gap?"* CISO must decide which source to activate.

### Query
> *"Which sources can I task on Dubai Free Zone to cover KRI-02?"*

**Step 1 — Gap analysis**

Enterprise corpus — field intelligence covering `Dubai Free Zone` + `KRI-02`:
- `ENT-202606-0118` : B3 — facility access restriction (warehouse complex under access control)
- `ENT-202606-0133` : B2 — facility access restriction (third-party logistics hub cleared)
- `ENT-202606-0192` : B3 — personnel movement (individuals accessing site at night)

CISO personal index — `CISO-202606-0015`, ACCESS_EVALUATION for SRC-202 covering Dubai Free Zone.

**Step 2 — Ontological source reasoning**
```
"Dubai Free Zone"  → FREE_TRADE_ZONE → REGULATED_TERRITORY
"KRI-02"           → KRI_SANCTIONS_EVASION → KRI → COMPLIANCE
SRC-202            → FORMER_EMPLOYEE → SOURCE_CATEGORY → HUMINT_CORPORATE
```

SRC-202 holds documented access to Dubai Free Zone (ACCESS_EVALUATION), reliability grade B, three corroborated reports on nocturnal facility access patterns.

**Sourcing recommendation generated:**
```
COVERAGE ANALYSIS — KRI-02 / Dubai Free Zone

GAP: No direct observation of sanctioned counterparty contact during gap.
3 field reports (B2–B3) confirm nocturnal activity at Dubai FZ (D-29 to D-27).

RECOMMENDED SOURCE: SRC-202
  → Category:   FORMER_EMPLOYEE — ex-NEH Dubai head of structured finance
  → Access:     DIRECT, Dubai Free Zone (ACCESS_EVALUATION validated)
  → Reliability: B — "Usually reliable"
  → Last corroborated report: 27 days
  → Status:     ACTIVE

SUGGESTED TASKING:
  Confirm counterparty identity and commodity origin for NEH-Dubai cargo.
  Deadline: 24h | Priority: IMMEDIATE | KRI: KRI-02

[Button] → Generate CISO tasking order
```

*Key feature: the platform reasons about what it does NOT know — the gap between existing coverage and the question being asked. The chain SOURCE_CATEGORY → ACCESS_EVALUATION → TASKING_ORDER is an ontological inference, not a keyword match.*

---

# VIEW 4 — CFO (Chief Financial Officer)
**Strategic multi-index aggregation + decision briefing**

### Context
25 July 2026, 01:29 UTC — the CFO opens the daily assessment (`CFO-202607-0101`). Five personal index records touch NEH. Six enterprise corpus alerts. Twenty-one CDO entries. The CFO does not read the detail — they want the decision synthesis.

### Query
> *"Brief me — NEH situation, decisions outstanding."*

**Step 1 — Full cross-index retrieval**
| Source | Records | Relevance |
|---|---|---|
| Enterprise corpus — market data | 6 alerts | Anomaly chronology |
| Enterprise corpus — field intel | 6 field reports (Dubai) | KRI-02 corroboration |
| CDO personal | 21 entity tracks + assessments | Analytical thread |
| CFO personal | 5 (DECISION_LOG ×3, CCIR ×2) | Prior decisions |

**Step 2 — Policy resolution via ontology**  
`CCIR CFO-202607-0091` asks: *"Has NEH Geneva executed an undisclosed transfer in the last 48h?"*  
Ontology resolves: `SHADOW_LEDGER → ENTITY_RISK → UNDISCLOSED_TRANSFER → LAYERING → KRI_AML_LAYERING`  
Active policies (Policy 451 — Asset Freeze; Policy 471 — Third-Party Audit Authority) attach via `concept_ids: [CFO_RISK_DESK, COMPLIANCE]`.

**CFO Decision Briefing:**
```
CFO DECISION BRIEFING — 250130ZJUL26
CONFIDENTIAL — C-SUITE DISTRIBUTION ONLY

═══ SITUATION ═══
NEXUS ENERGY HOLDINGS (NEH): 30 days of anomalous activity.
Timeline: REPORTING_GAP (28 Jun) → ROUND_TRIP_TRADE ×2 (29 Jun, 22 Jul) 
          → VELOCITY_SPIKE ×2 → COMMODITY_MISMATCH.
CDO assessment: HIGH CONFIDENCE link to SHADOW LEDGER COORDINATOR ALPHA.
Grounding: pattern consistent with Glencore/Vitol intermediary structure.
Due diligence 17 Jul: COMMODITY_MISMATCH — no legal hold applied.
Active contact: Compliance team dispatching audit team (27 Jul 16:57Z).

═══ KRI STATUS ═══
KRI-01 (financial fraud/concealment) : THRESHOLD MET ✓
KRI-02 (sanctions evasion)           : THRESHOLD MET ✓
KRI-05 (commodity misreporting)      : AT THRESHOLD
CCIR CFO-202607-0091                 : OPEN — CDO response in progress

═══ PRIOR DECISIONS ═══
17 Jul: Due diligence authorised → mismatch found, no hold applied.
18 Jul: CDO tasked against KRI-02 / Dubai.
23 Jul: Surveillance reinforced, Geneva desk.

═══ DECISIONS REQUIRED NOW ═══
① Invoke asset freeze under Policy 451 + 471?
   → Basis: KRI-01 + KRI-02 threshold + CCIR + field intel B2 corroboration
② Instruct voluntary OFAC disclosure?
   → Basis: KRI-02 threshold; Vitol precedent — early disclosure = reduced penalty
③ Engage forensic accountants on BVI SPV structures?
   → Basis: CDO EOI track — 3 SPVs with no consolidation in audited accounts

═══ LEGAL CONSTRAINTS ═══
Policy 451 active | Policy 471 active
General Counsel: freeze authority confirmed
Exposure: ~$240M across 4 entities
```

*Key feature: every assertion is traced to a doc_id. The CFO clicks any line to reveal the chunks. RAG (retrieval) + ontology (KRI/policy resolution) + LLM (decision synthesis) — in fifteen seconds.*

---

## Feature Matrix

| Feature | CTO (Act 0) | CDO | CEO | CISO | CFO |
|---|:---:|:---:|:---:|:---:|:---:|
| Source selection & description | ✓ primary | | | | |
| Document ingestion | ✓ primary | ✓ runtime | ✓ runtime | ✓ runtime | ✓ runtime |
| Ontology merge & conflict resolution | ✓ primary | | | | |
| Merged ontology graph | ✓ primary | ✓ read | ✓ read | ✓ read | ✓ read |
| Dual-index RAG | | ✓ | ✓ | ✓ | ✓ |
| Ontology query expansion | | ✓ primary | ✓ secondary | ✓ primary | ✓ secondary |
| Jurisdictional retrieval | | | ✓ primary | ✓ | ✓ |
| Collection-gap reasoning | | | | ✓ primary | |
| KRI resolution | | ✓ | ✓ | ✓ | ✓ primary |
| Policy / CCIR resolution | | | | | ✓ primary |
| Access-tier filtering | ✓ defines it | ✓ | ✓ visible | ✓ | ✓ |
| Source attribution (traceability) | ✓ audit | ✓ RISK_SUMMARY | ✓ BOARD_SITREP | ✓ FIELD_REPORT | ✓ CFO_BRIEFING |

---

## Live Demo Runsheet (~15 minutes)

**Act 0 — Corpus prep (4 min)**  
Open workbench. Pause on access-tier split: *"One file. Three tiers. What happens if you ingest it flat?"* Let the audience answer. Run ingestion (talk over it). Show ontology graph — toggle `related` edges. Resolve the two conflicts live. Close: *"The platform refused to guess. That refusal is auditable."*

**Hook (30 sec)**  
Empty KRI dashboard → drop `ENT-202606-0048` (reporting gap). One alert. Ask: *"In thirty seconds, what does the platform know about this entity?"*

**CDO view (3 min)**  
Type the query. Show concept graph lighting up. Dual-index retrieval counter. Generated RISK_SUMMARY with doc_ids in sidebar. Key line: *"The LLM does not know — it reads."*

**CEO view (2 min)**  
Switch persona — different index, same corpus. Same query on NEH → different output. Show the access-tier banner: *"331 records withheld."* BOARD_SITREP fuses both indexes in real time.

**CISO view (3 min)**  
Show gap reasoning: *"I am looking for what I do not yet know."* The ontology walks `KRI_SANCTIONS_EVASION → FORMER_EMPLOYEE → ACCESS_EVALUATION → SRC-202`. Most technically striking segment.

**CFO view (2 min)**  
Four-index aggregation. Briefing renders in 15 seconds. Click a decision line → sources revealed. Close: *"The CFO does not read 37 documents. They validate a chain of reasoning."*

**Closing question**  
*"What happens if all four personas ask the same question?"* Four different answers — same shared corpus, four different personal indexes. That is the dual-index value proposition in one screen.

---

## Data File Index

| File | Description | Records |
|---|---|---|
| `enterprise_intelligence_corpus.json` | Shared corpus — OSINT, market data, field intel | 1,000 |
| `enterprise_ontology.yaml` | FINANCIAL_RISK / COMPLIANCE / OPERATIONS spine | 68 concepts |
| `user_cdo_analyst.json` | CDO personal index | 110 |
| `user_ceo_watch.json` | CEO personal index | 110 |
| `user_ciso_operator.json` | CISO personal index | 110 |
| `user_cfo_executive.json` | CFO personal index | 110 |

---

## Case Grounding Notes

Every fraud typology in this dataset is grounded in public record. The mechanisms, patterns, and analytical logic are drawn from:

- **Glencore DOJ/SFO 2022:** intermediary bribery via advisory-fee structures across Nigeria, DRC, Venezuela; CFTC round-trip fuel oil derivatives ($341M); total resolution ~$1.5B.
- **Vitol DOJ 2020:** OFAC sanctions evasion via Iranian crude re-documented as Iraqi and Malaysian; deferred prosecution agreement $135M; mirror of COMMODITY_MISMATCH alert typology.
- **1MDB DOJ 2016–2023:** MT202COV payment cover used to route proceeds to BVI shells (Good Star Ltd); off-balance-sheet treatment of SPV participations; $700M+ recovered.
- **Wirecard BaFin/KPMG 2020:** €1.9B in fictitious escrow receivables from non-existent Senjo Group entities; 180-day non-collection pattern; KPMG special audit unable to verify cash.
- **FinCEN Files ICIJ 2020:** SWIFT message analysis revealing layering via MT103/MT202COV through Deutsche Bank, HSBC, Standard Chartered correspondent accounts; Azerbaijani Laundromat methodology.

*Scenario generated 28 Jul 2026 — all companies, individuals, and transactions are fictional. Not real intelligence or financial data.*
