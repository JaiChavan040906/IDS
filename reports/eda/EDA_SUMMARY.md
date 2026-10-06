# EDA Summary: Improved CIC-IDS2017

Source: `data/raw/` (5 files, Mon-Fri, 1.15 GB). Script: `scripts/inspect_dataset.py`.
Full console output: `reports/eda_console.txt`. Tables: `reports/eda/*.csv`.

## Size
- 2,099,976 flows, 91 columns, 27 labels.
- 1,836,971 unique flows after removing duplicates (IDs dropped).

## Columns
- Identifiers to drop: id, Flow ID, Src IP, Src Port, Dst IP, Timestamp.
- `Attempted Category` must also be dropped: it is -1 for normal labels and
  0-6 for "Attempted" labels, so keeping it would leak the answer.
- Dst Port: kept, but its effect gets tested separately (shortcut risk).
- No duplicate columns, no constant columns (the corrected release fixed these).
- Negative values in Fwd/Bwd Header Length (a CICFlowMeter quirk). ICMP Code/Type
  use -1 to mean "not ICMP", which is fine.
- About 84 usable features after drops (paper used 46 after selection).

## Data quality
- NaN: none.
- Infinity: 5 rows in Flow Bytes/s and Flow Packets/s (zero-duration flows).
- Exact duplicate rows: 0.
- Duplicates after dropping IDs: 263,005 (12.5%). Nearly all are BENIGN (157k),
  Portscan (68k), Infiltration - Portscan (31k) and Botnet - Attempted (2.9k).
- Same features, different label: 4,375 vectors, almost all
  Portscan vs Infiltration - Portscan. No model can separate these.

## Classes (heavy imbalance: 75.4% BENIGN)
- Large: Portscan 159k, DoS Hulk 158k, DDoS 95k, Infiltration - Portscan 72k.
- Medium: DoS GoldenEye, Slowloris, Slowhttptest, FTP/SSH-Patator, Botnet (0.7k-7.6k).
- Tiny (< 100): Web Attack Brute Force 73, XSS 18, SQL Injection 13,
  Heartbleed 11, Infiltration 36.
- 11 "Attempted" labels (14k rows): attack traffic that did not succeed.

## Decisions needed before preprocessing
1. Attempted labels: merge into their attack class (recommended), or into BENIGN,
   or drop.
2. Infiltration - Portscan: merge with Portscan (recommended; features are identical).
3. Tiny classes: group web attacks into one "Web Attack" class; keep Heartbleed
   and Infiltration but report them separately with caveats.
4. Deduplicate before the train/val/test split, so no copy of a test row
   appears in train.
