# Data warehouse (DWM Module 1)

The portal's **WAREHOUSE** tab shows every Module 1 topic (Introduction to Data
Warehouse and ETL Process) on the project's own data. It's a separate analysis copy:
the detection model and the analysts never read it, so nothing here can change a detection.

| File | Role |
|---|---|
| `data/ids.db` | Operational database (OLTP): the portal's alerts, decisions, users, models |
| `data/warehouse.db` | The data warehouse (OLAP), built by the ETL job |
| `src/ids/warehouse.py` | Schema (DDL) + ETL: extract, transform, load, full and incremental |
| `src/ids/olap.py` | Cube definitions, OLAP query builder, comparisons, factless queries |
| `src/ids/api/routers/warehouse.py` | `/api/dw/*` endpoints (analyst + admin; only admin runs ETL) |
| `frontend/src/pages/warehouse/` | The three tabs: Overview, Schemas, OLAP cube (with the 3-D cube, `Cube3D.jsx`) |

It is already built. To rebuild it (about 25 s): if the warehouse file is missing, the WAREHOUSE page shows a
**Run full load** button for the admin. Or from a terminal (the portal doesn't need to be running):

```
.venv/Scripts/python -c "import yaml; from ids.warehouse import full_load; c=yaml.safe_load(open('configs/app.yaml')); full_load('data/warehouse.db','data/processed','data/raw','data/ids.db',c['severity'])"
```

## Showing or hiding the warehouse

The WAREHOUSE tab is **off by default**, for the practicals that don't cover DWM.

| Start with | Warehouse |
|---|---|
| `start_portal.bat` | hidden: no tab, `/warehouse` redirects to About, `/api/dw/*` returns 404, its audit entries are not listed |
| `start_portal_dwm.bat` | shown (sets `IDS_WAREHOUSE=1`) |

**On/Off switch in the portal:** ADMINISTRATION → Overview → System health → *Warehouse tab* [On | Off] (admin only). It takes effect immediately and lasts until the portal restarts; each start begins in the mode of its start file. Switching it is audited as `warehouse.switch`, which is also hidden while the warehouse is off.

**Graphs next to text:** while the switch is On, the portal also shows graphs beside the matching text and tables:
About (traffic handled automatically vs by the analyst), Analyst dashboard (where scored flows went, open items by
severity), alert detail (z-score bars for "What stands out"), Admin Evaluation (attacks caught and referral rate per
source), Models (macro-F1 per version), Retraining (base vs candidate), Warehouse Overview (flows per day, attack
flows by category), Schemas (star vs snowflake query time) and the OLAP cube (3-D cube + chart of the result).
With the switch Off none of these appear.

Nothing is deleted when it is hidden. `warehouse.db` and the audit rows stay, so switching back needs no rebuild.
The default can also be set with `warehouse_enabled` in `configs/app.yaml`; `IDS_WAREHOUSE` overrides it.

## Syllabus topic → where to show it

| Syllabus topic | Tab | What you see |
|---|---|---|
| Introduction to DW, DW architecture | Overview | Sources → ETL/staging → warehouse → marts → OLAP diagram |
| Star schema | Schemas → Star | `fact_flow` + `dim_time`, `dim_attack`, `dim_service`, `dim_protocol`, `dim_split` |
| Snowflake schema | Schemas → Snowflake | `dim_attack_sf → dim_category`, `dim_time_sf → dim_date`; timed vs star |
| Fact constellation | Schemas → Fact constellation | `fact_alert` + `fact_review` share time, attack, model |
| Data cube | OLAP cube → The cube | A real 3-D cube: X = columns, Y = rows, Z = depth; one block per cell, colour = value |
| OLAP operations | OLAP cube | Roll-up, drill-down, slice, dice and pivot buttons; the 3-D cube changes with each (slice/dice light up their part), plus a chart of the result |
| ETL process | Overview (architecture diagram) | Sources → ETL + staging → warehouse; the ETL itself runs in `src/ids/warehouse.py` |

## Five-minute demo for the professor

1. **Overview**: the architecture diagram, then the two charts (flows per day, attack flows by category).
2. **Schemas → Star**: click `fact_flow` to show real rows. Switch to Snowflake and press **Run both queries**:
   same answer, the snowflake needs more joins.
3. **OLAP cube**: press the example buttons in order: start → drill-down → roll-up →
   slice → dice → pivot. Point at "Operations applied".
   Click a day name to drill into it. Watch **The cube** change with every step: drill-down adds blocks,
   a slice lights up one layer, a dice a smaller block, pivot turns the cube.

## Numbers from the current build

- `fact_flow` 1,714,812 rows (grain: one flow). Every row matched its raw timestamp.
- `dim_time` 2,454 minutes (3–7 July 2017), `dim_service` 4,447 ports, 13 attack classes in 9 categories.
- Full load 25 s. An incremental load with nothing new takes 0.3 s.
- `agg_flow_hour` 606 rows (hour × attack × protocol × split). Day × attack question: about 2.3 s on `fact_flow`
  vs 0.3 ms on `agg_flow_hour` (same answer). The 3-D cube over time, attack and protocol takes about 1 ms.
- Star 2,046 ms vs snowflake 2,312 ms for the same question.

## Notes

- The warehouse uses the dataset's true labels to describe historical traffic. That is
  descriptive analysis only: it never feeds training, tuning, prediction or the
  analyst's decision. In `fact_alert`, "attack" is the model's predicted class.
- `fact_flow` has no foreign-key indexes on purpose: OLAP queries read most of the table,
  and one sequential scan is about 4× faster in SQLite than 1.7 million index lookups.
- Resetting the portal (`reset_portal.bat`) doesn't touch the warehouse. The next
  incremental load detects the reset and reloads the portal facts.
