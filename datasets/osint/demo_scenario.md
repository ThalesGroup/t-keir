# C2 Demonstration Scenario — RAG + Ontology System
## "Operation RED HORIZON" — MT RED SEA EAGLE

**Simulated classification:** SECRET // REL TO COALITION TF
**Time window:** 28 June → 28 July 2026
**Scenario pivot:** MT RED SEA EAGLE (IMO 9238117, Barbados flag, Products Tanker, HIGH risk profile)

---

## Narrative context

A tanker under a flag of convenience — MT RED SEA EAGLE — has been operating for thirty days across the maritime space between Bab-el-Mandeb, the Strait of Hormuz and the Fujairah OPL anchorage. Five distinct anomalies touch it in the generic dataset. Twenty-one records track it in the J2 analyst index.

The scenario follows that thread. **Act 0** builds the shared knowledge base that every user will query. **Act 1** is the trigger. The four persona views that follow each surface a different capability of the system.

---

# ACT 0 — Corpus preparation (Administrator)

**Actor:** System administrator, Keycloak role `c2-admin`
**Scope:** Data **global to all users** — the generic index, read-only for every persona
**Features demonstrated:** **Source selection · pre-ingestion description · document ingestion · merged ontology graph**

> This act is what makes everything after it defensible. The generic corpus is the shared evidence base: every persona queries it, but each sees a different slice of it depending on clearance. Getting the description stage wrong here silently breaks every downstream report.

---

## Stage 1 — Source selection

The administrator opens the **Corpus Indexation Workbench** and browses the server-side corpus directory.

```
/dataset/osing/
├── c2_middle_east_multi_source_1000_v3_en.json      2.9 MB   [not indexed]
├── c2_middle_east_business_ontology.yaml             44 KB   [not indexed]
```


## Stage 2 — Ingestion execution

Three ingestion units are committed. Progress streams per document.


# ACT 1 — Trigger (28 June, 13:34Z)

**Triggering event:** alert `C2-202606-0048` lands in the generic feed.

```
MARITIME ANALYTICS ALERT (DARK_ACTIVITY_AIS_OFF):
MT RED SEA EAGLE (IMO 9238117, flag Barbados, Products Tanker)
exhibited critical behavioural anomaly near Beirut Port Approach.
AIS transmitter disabled for 18.4 hours.
Cross-referenced via SAR and RF emitter triangulation.
Evaluation: B1 — PRIORITY
```

The vessel drops off the COP for 18h24. That single fact activates three PIRs simultaneously in the generic index: PIR-01 (maritime interdiction), PIR-02 (sanctions evasion), PIR-05 (weapons transhipment). The ontology resolves automatically: `DARK_ACTIVITY` → `AIS_ANOMALY` → `AIS` → `SITUATIONAL_AWARENESS` → `C4ISR`.

---

# VIEW 1 — J2 Intelligence Analyst

**Profile:** J2 Intelligence Analyst
**Indexes:** Generic (maritime, HUMINT, OSINT) + Personal (ENTITY_TRACK, ASSESSMENT, COLLATERAL)
**Feature demonstrated:** **Multi-index RAG + ontological reasoning**

### User query
> *""Tell me everything the system knows about MT RED SEA EAGLE.*

### What the system does (visible on screen)

**Step 1 — Query expansion via ontology**

The engine translates the query into a concept graph:

```
"MT RED SEA EAGLE" (surface_form of VESSEL)
  → concept_ids: VESSEL, SHADOW_FLEET, SANCTIONS_EXPOSURE
  → pir_refs:    PIR-02, PIR-05
  → related:     DARK_ACTIVITY, STS_TRANSFER, AIS_ANOMALY
```

Expansion climbs automatically to `VESSEL_RISK` → `VESSEL` → `SITUATIONAL_AWARENESS`.

**Step 2 — Dual-index retrieval**

| Index | Hits | Breakdown |
|---|---|---|
| Generic | 6 | 1× DARK_ACTIVITY, 2× STS_TRANSFER, 2× SPEED_ANOMALY, 1× ROUTE_DEVIATION |
| Personal (J2A) | 21 | 12× ENTITY_TRACK, 9× ASSESSMENT |

**Step 3 — Fusion and INTSUM generation**

The local LLM receives the 27 relevant chunks plus the ontological context:

```
INTSUM — MT RED SEA EAGLE (IMO 9238117)
Period: 28 Jun – 26 Jul 2026 | Consolidated evaluation: B2

SITUATION: Vessel has accumulated 5 distinct AIS anomaly types over 30 days
(dark activity ×1, STS suspected ×2, loitering ×2, route deviation ×1).
Pattern consistent with TTP of SHADOW FLEET COORDINATOR ALPHA network.

ENTITY TRACKING: Associated with entities EOI-005, EOI-014, EOI-019, EOI-016.
Latest J2A assessment HIGH CONFIDENCE (J2A-202607-0086, 19 Jul).

RECOMMENDATION: Classify PRIORITY for active surveillance. Suggested CCIR:
"Has MT RED SEA EAGLE conducted an STS transfer in the last 48 hours?"
```

**Key feature demonstrated:** the LLM does not invent — every assertion in the INTSUM traces back to a source `doc_id` displayed in the side panel. The ontology retrieved records tagged `SHADOW_FLEET` without the user ever typing that phrase.

> The `ENTITY` concept merged in during Act 0 is what anchors the EOI tracking line. Without that merge, entity tracks would have no ontological path.

---

# VIEW 2 — MOC Watch Officer

**Profile:** MOC Watch Officer
**Indexes:** Generic (real-time maritime alerts) + Personal (UNIT_POSITION, PATROL_REPORT, VESSEL_CONTACT, BOARDING_REPORT)
**Feature demonstrated:** **Geospatial retrieval + COP aggregation**

### Context
17 July 2026, 07:57Z — WARSHIP CYGNET detects MT RED SEA EAGLE in the Gulf of Aden Corridor and files `MOC-202607-0063`: a boarding report with finding **CARGO MANIFEST DISCREPANCY**.

### What the system does

**Watch officer query:**
> *"Summarise the Gulf of Aden situation for the 08:00 SITREP."*

**Step 1 — Geospatial retrieval**

The generic index is filtered on `location_refs ∈ {Gulf of Aden Corridor, Bab-el-Mandeb Strait, Southern Red Sea}` over the window T-6h to now.

Retrieved:
- `C2-202607-0978` — STS_TRANSFER_SUSPECTED on MT RED SEA EAGLE / Gulf of Aden Corridor (B3, ROUTINE) ← **generic**
- `MOC-202607-0063` — BOARDING_REPORT / CARGO MANIFEST DISCREPANCY ← **personal**
- `MOC-202607-0110` — VESSEL_CONTACT / WARSHIP CYGNET / BOARDING TEAM DISPATCHED ← **personal**

**Step 2 — PIR expansion via ontology**

`CARGO MANIFEST DISCREPANCY` maps to `ILLICIT_CARGO_TRANSFER`, which links to `PIR_WEAPONS_TRANSHIPMENT` and `PIR_SANCTIONS_EVASION`. The interface highlights the activated PIRs in the sidebar automatically.

**Step 3 — SITREP generation**

```
SECTOR SITREP — Gulf of Aden / Bab-el-Mandeb | 280800ZJUL26

SITUATION: Elevated activity on contact MT RED SEA EAGLE (IMO 9238117).
  → D-1 17:57Z: Boarding by WARSHIP CYGNET — CARGO MANIFEST DISCREPANCY.
  → D-0 01:58Z: Alert STS_TRANSFER_SUSPECTED / Gulf of Aden Corridor (B3).
  → 27 Jul 16:57Z: New contact WARSHIP CYGNET — BOARDING TEAM DISPATCHED.

UNITS IN SECTOR: WARSHIP CYGNET (P-211, UK, OPV), WARSHIP AJAX (F-301, FR, Frigate).
CYGNET FUEL STATE: To be confirmed (last POSREP T-4h).

PIRs ACTIVATED: PIR-02 (sanctions evasion), PIR-05 (weapons transhipment).
RECOMMENDED ACTION: Escalate to J2 — CCIR threshold met.
```

**Key feature demonstrated:** the SITREP fuses both indexes in real time with no manual cross-referencing. Ontological resolution turns a free-text finding ("cargo manifest discrepancy") into a structured PIR activation.

> Note the clearance effect from Act 0: this officer holds FOUO clearance. The 331 SECRET HUMINT records are excluded server-side, and the banner says so. The SITREP is built entirely from material they are cleared to hold.

---

# VIEW 3 — J2X HUMINT Operator

**Profile:** J2X HUMINT Operator
**Indexes:** Generic (HUMINT_SPOTREP, OSINT) + Personal (TASKING_ORDER, RAW_REPORT, ACCESS_EVAL)
**Feature demonstrated:** **Collection-gap reasoning + tasking recommendation**

### Context
WARSHIP CYGNET's boarding found a manifest discrepancy but no direct evidence. The J2 analyst has raised a CCIR: *"Has MT RED SEA EAGLE conducted an STS in the last 48 hours?"* J2X must decide which source to activate.

### What the system does

**J2X operator query:**
> *"Which sources can I task on Fujairah OPL to cover PIR-02?"*

**Step 1 — Gap-analysis retrieval**

The system queries both indexes simultaneously:

- **Generic index** — HUMINT covering `Fujairah OPL Anchorage` + `PIR-02`
  - `C2-202606-0118` : B3, port access restriction (berths 4–5 cleared, armed guard)
  - `C2-202606-0133` : B2, port access restriction (berths 6–10 cleared)
  - `C2-202606-0192` : B3, personnel movement (individuals boarding at night)
- **Personal J2X index** — `J2X-202606-0015`, ACCESS_EVAL for SRC-102 covering Fujairah OPL

**Step 2 — Ontological reasoning over coverage**

```
"Fujairah OPL" → TERRITORIAL_WATERS → MARITIME_ZONE
"PIR-02"       → PIR_SANCTIONS_EVASION → PIR → INTELLIGENCE
SRC-102        → RECRUITED_ASSET → SOURCE_CATEGORY → HUMINT
```

SRC-102 holds documented access to Fujairah OPL (ACCESS_EVAL), reliability grade B confirmed within the last 30 days, and three corroborated reports on nocturnal personnel movement in the area.

**Step 3 — Enriched SPOTREP + tasking recommendation**

```
COVERAGE ANALYSIS — PIR-02 / Fujairah OPL Anchorage

GAP IDENTIFIED: No direct observation of an STS involving MT RED SEA EAGLE.
3 HUMINT reports (B2–B3) confirm nocturnal activity at the OPL (D-29 to D-27).

RECOMMENDED SOURCE: SRC-102
  → Access:     DIRECT, Fujairah OPL (ACCESS_EVAL validated)
  → Reliability: B — "Usually reliable"
  → Last corroborated report: 27 days
  → Status:     ACTIVE

SUGGESTED TASKING:
  Confirm presence and activity of IMO 9238117 at Fujairah OPL.
  Deadline: 24h | Priority: IMMEDIATE | PIR: PIR-02

[Button] → Generate J2X tasking order
```

**Key feature demonstrated:** the system reasons about the **gap** between what sources have already covered (generic index) and what available sources *could* cover (personal index). The chain `SOURCE_CATEGORY → ACCESS_EVAL → TASKING_ORDER` is an ontological inference, not a keyword match.

---

# VIEW 4 — CTF Commander

**Profile:** CTF Commander
**Indexes:** Generic (multi-domain, all PIRs) + Personal (ROE_CARD, FORCE_STATUS, DECISION_LOG, CCIR, COMMANDER_ASSESSMENT)
**Feature demonstrated:** **Strategic multi-index aggregation + briefing generation**

### Context
25 July 2026, 01:29Z — the commander opens the daily Commander's Assessment (`CTF-202607-0101`). Five records in the personal index touch MT RED SEA EAGLE, six generic alerts, twenty-one J2A entries. The commander does not read the detail — they want the decision synthesis.

### What the system does

**Commander query:**
> *"Brief me — RED SEA EAGLE situation, decisions outstanding."*

**Step 1 — Full cross-index retrieval**

| Source | Records | Relevance |
|---|---|---|
| Generic maritime | 6 alerts | Anomaly chronology |
| Generic HUMINT | 6 SPOTREPs (Fujairah) | PIR-02 corroboration |
| J2A personal | 21 ENTITY_TRACK + ASSESSMENT | Analytical thread |
| CTF personal | 5 (DECISION_LOG ×3, CCIR ×2) | Prior decisions |

**Step 2 — Ontological resolution of ROE**

CCIR `CTF-202607-0091` asks: *"Has shadow fleet vessel conducted STS in last 48h?"*
The ontology resolves `SHADOW_FLEET` → `VESSEL_RISK` → `VESSEL` → `STS_TRANSFER` → `AIS` → `PIR_SANCTIONS_EVASION`.
Active ROE (451 — Maritime Interception, 471 — Boarding Operations) attach directly via `concept_ids: [OPERATIONS, C4ISR]`.

**Step 3 — Commander's briefing generation**

```
COMMANDER'S BRIEFING — 250130ZJUL26
Classification: SECRET // REL TO COALITION TF

═══ SITUATION ═══
MT RED SEA EAGLE (IMO 9238117): 30 days of anomalous activity.
Timeline: DARK (28 Jun) → STS ×2 (29 Jun, 22 Jul) → LOITERING ×2 → ROUTE DEV.
J2 assessment: HIGH CONFIDENCE link to SHADOW FLEET COORDINATOR ALPHA.
Boarding 17 Jul: CARGO MANIFEST DISCREPANCY — no legal follow-up.
Active contact: WARSHIP CYGNET dispatching boarding team (27 Jul 16:57Z).

═══ PIR STATUS ═══
PIR-02 (sanctions evasion)   : THRESHOLD MET ✓
PIR-05 (weapons transhipment): AT THRESHOLD
CCIR CTF-202607-0091         : OPEN — J2 response in progress

═══ PRIOR DECISIONS ═══
17 Jul: Boarding authorised → discrepancy found, vessel released.
18 Jul: J2 tasked against PIR-02 / Fujairah.
23 Jul: Surveillance reinforced, Gulf of Aden.

═══ DECISIONS REQUIRED NOW ═══
① Authorise re-interdiction under ROE 451 + 471?
   → Basis: PIR-02 threshold + CCIR + HUMINT B2 corroboration (Fujairah)
② Request national asset support (satellite) for a 24h window?
③ Divert WARSHIP FALCON (LPD) in support of boarding?

═══ CONSTRAINTS ═══
ROE 451 active | ROE 471 active
LAO opinion: Legal authority confirmed for boarding
Force: WARSHIP AJAX available, WARSHIP CYGNET on station
```

**Key feature demonstrated:** the briefing is fully **traced** — every assertion carries its source `doc_id`s. The commander can click any line to reveal the chunks that fed that conclusion. RAG (retrieval) + ontology (CCIR and ROE resolution) + LLM (decision synthesis) produce this in seconds.

---

## Feature matrix by persona

| Feature | Admin (Act 0) | J2 Analyst | MOC Watch | J2X HUMINT | CTF Commander |
|---|:---:|:---:|:---:|:---:|:---:|
| **Source selection & description** | ✓ primary | | | | |
| **Document ingestion** | ✓ primary | ✓ runtime | ✓ runtime | ✓ runtime | ✓ runtime |
| **Ontology merge & conflict resolution** | ✓ primary | | | | |
| **Merged ontology graph** | ✓ primary | ✓ read | ✓ read | ✓ read | ✓ read |
| **Dual-index RAG** | | ✓ | ✓ | ✓ | ✓ |
| **Ontology query expansion** | | ✓ primary | ✓ secondary | ✓ primary | ✓ secondary |
| **Geospatial retrieval** | | | ✓ primary | ✓ | ✓ |
| **Gap reasoning** | | | | ✓ primary | |
| **PIR resolution** | | ✓ | ✓ | ✓ | ✓ primary |
| **ROE / CCIR resolution** | | | | | ✓ primary |
| **Clearance filtering** | ✓ defines it | ✓ | ✓ visible | ✓ | ✓ |
| **Source attribution (traceability)** | ✓ audit | ✓ INTSUM | ✓ SITREP | ✓ SPOTREP | ✓ Briefing |
| **Structured report generation** | | INTSUM | SITREP | SPOTREP + Tasking | Commander's Briefing |

### Agent workflows (analyse → review → write → compose)

Each persona has a dedicated OTAN agent workflow (Agents HMI defaults to the matching workflow). Steps: **analyser** (dual-index RAG) → **reviewer** (drop uncited / world-knowledge claims) → **writer** (persona voice) → **compose** (OTAN template). Agents refuse shipyard/builder/ownership trivia unless it appears in retrieved chunks.

| Persona | Workflow | Agents | Compose template |
|---|---|---|---|
| Admin (`c2-admin`) | `persona_admin` | `admin_{analyser,reviewer,writer}` | `otan_intsum` |
| J2 Analyst | `persona_j2_analyst` | `j2_analyst_{analyser,reviewer,writer}` | `otan_intsum` |
| MOC Watch | `persona_moc_watch` | `moc_watch_{analyser,reviewer,writer}` | `otan_sitrep` |
| J2X HUMINT | `persona_j2x_humint` | `j2x_humint_{analyser,reviewer,writer}` | `otan_spotrep` |
| CTF Commander | `persona_ctf_commander` | `ctf_commander_{analyser,reviewer,writer}` | `otan_commander_brief` |

Configs live under `datasets/osint/agents/` and `datasets/osint/workflows/`
(discovered automatically by the agent registry alongside core
`tkeir/configs/agents|workflows`).

---

## Live demo runsheet

**Act 0 — Corpus preparation (4 min)**
Open the workbench, select the corpus. Land on Stage 2 and pause on the classification split: *"One file. Three classifications. What happens if we ingest it as one unit?"* Let the audience arrive at the answer. Run the ingestion (1m45s — talk over it, or pre-run and replay). Then the ontology graph: toggle `related` edges on and off to show why hierarchy and association are rendered differently. Finish on the conflict drawer — `SITREP` under SITUATIONAL_AWARENESS or under HUMINT? — and resolve it live. **Closing line:** *"The machine refused to guess. That refusal is the feature."*

**Hook (30 sec)**
Show the empty COP, then drop alert `C2-202606-0048` (dark activity). One line in the feed. Ask: *"In thirty seconds, what does the system know about this vessel?"*

**J2 Analyst view (3 min)**
Type the query. Show ontology expansion in real time (concept graph lighting up), then dual-index retrieval (chunk counter), then the generated INTSUM with `doc_id`s in the sidebar. Emphasise: *"The LLM does not know — it reads."*

**MOC Watch view (2 min)**
Switch persona — different user context, different personal index. Same vessel, different view. The SITREP aggregates both indexes automatically. Point out that WARSHIP CYGNET exists only in the personal index. Show the clearance banner: *"331 records withheld"* — the Act 0 classification split, paying off.

**J2X HUMINT view (3 min)**
Show gap reasoning: *"I am looking for what I do not yet know."* The ontology walks `PIR_SANCTIONS_EVASION → RECRUITED_ASSET → ACCESS_EVAL → SRC-102`. Technically the most striking segment — a system reasoning about its own blind spots.

**CTF Commander view (2 min)**
Four-index aggregation. The briefing renders in fifteen seconds. Click a decision to reveal its sources. Close with: *"The commander does not read thirty-seven documents — they validate a chain of reasoning."*

**Suggested closing question**
*"What happens if we ask all four personas the same question?"* Show that the identical query on MT RED SEA EAGLE returns four different answers, because the personal index differs while the generic index is shared. That is the dual-index value proposition in one screen.

**Total: ~15 minutes**

---

## Real data used in the scenario

### Act 0 — Corpus and ontology

| Artefact | Content |
|---|---|
| `c2_middle_east_multi_source_1000_v3_en.json` | 2.9 MB, 1000 records, 3 classification tiers, 18 locations, 48 vessels |
| `c2_middle_east_business_ontology.yaml` | 82 concepts, 44 KB, 3 root branches |
| `legacy/business_ontology.yaml` | 16 concepts, contributes ENTITY, OBJECTIVE_ALPHA, SITREP, SALUTE |
| Merged result | 86 concepts, 2 conflicts resolved, 299 edges |

### Generic index (`c2_middle_east_multi_source_1000_v3_en.json`)

| doc_id | Type | Content |
|---|---|---|
| C2-202606-0048 | DARK_ACTIVITY_AIS_OFF | AIS gap 18.4h — Beirut Port Approach — B1 |
| C2-202606-0157 | STS_TRANSFER_SUSPECTED | STS — Suez Gulf Approach — B2 |
| C2-202606-0118 | HUMINT PORT_ACCESS_RESTRICTION | Fujairah OPL berths 4–5 under armed guard — B3 |
| C2-202606-0133 | HUMINT PORT_ACCESS_RESTRICTION | Fujairah OPL berths 6–10 under armed guard — B2 |
| C2-202606-0192 | HUMINT PERSONNEL_MOVEMENT | Individuals boarding at night — Fujairah — B3 |
| C2-202607-0978 | STS_TRANSFER_SUSPECTED | STS — Gulf of Aden Corridor — B3 |
| C2-202606-0006 | OSINT | Loss of navigation signals — Gulf of Aden — C2 |
| C2-202606-0010 | OSINT | Traffic delays — Bab-el-Mandeb — C2 |

### J2 Analyst index (`user_j2_analyst.json`)

| doc_id | Type | Content |
|---|---|---|
| J2A-202607-0010 | ENTITY_TRACK EOI-017 | SHADOW FLEET COORDINATOR ALPHA — MEDIUM CONF |
| J2A-202607-0028 | ENTITY_TRACK EOI-016 | SHADOW FLEET COORDINATOR ALPHA — HIGH CONF |
| J2A-202607-0086 | ENTITY_TRACK EOI-004 | SHADOW FLEET COORDINATOR ALPHA — HIGH CONF |

### MOC Watch index (`user_moc_watch.json`)

| doc_id | Type | Content |
|---|---|---|
| MOC-202607-0063 | BOARDING_REPORT | CARGO MANIFEST DISCREPANCY — WARSHIP CYGNET |
| MOC-202607-0110 | VESSEL_CONTACT | BOARDING TEAM DISPATCHED — WARSHIP CYGNET |
| MOC-202607-0047 | PATROL_REPORT | ELEVATED ACTIVITY |

### CTF Commander index (`user_ctf_commander.json`)

| doc_id | Type | Content |
|---|---|---|
| CTF-202607-0079 | DECISION_LOG | Boarding authorised 17 Jul |
| CTF-202607-0091 | CCIR | "STS in last 48h?" — OPEN |
| CTF-202607-0101 | COMMANDER_ASSESSMENT | Assessment 25 Jul — situation stable/deteriorating |

### J2X HUMINT index (`user_j2x_humint.json`)

| doc_id | Type | Content |
|---|---|---|
| J2X-202606-0015 | ACCESS_EVAL SRC-102 | Fujairah OPL access — B — DIRECT |
| J2X-202607-0035 | TASKING_ORDER SRC-111 | PIR-02 / Bab-el-Mandeb — ROUTINE |

---

*Scenario generated 28 Jul 2026 — simulated data — no real intelligence*