---
title: Sentinel IDS
emoji: 🛡️
colorFrom: indigo
colorTo: green
sdk: docker
app_port: 7860
pinned: false
short_description: Human-in-the-loop network intrusion detection prototype
---

# Sentinel: Human-in-the-Loop Intrusion Detection

An intrusion detection prototype that knows when to ask a human. A CNN-LSTM classifies each network
flow, an uncertainty router (entropy, embedding distance and a Random Forest second opinion) sends
doubtful flows to a security analyst, analyst decisions are kept in a searchable Knowledge Repository,
and verified feedback improves the model only through controlled, admin-approved retraining.

**Authors:** Jai Chavan, Jeet Mane, Department of Computer Engineering,
Vidyalankar Institute of Technology, Mumbai.

## Using the demo

- Sign in as **admin** or **analyst** (passwords are given by the authors).
- Admin → Overview → **Traffic replay** → *Start replay* streams the held-out CIC-IDS2017 test flows
  through the model; the analyst works the review queue.
- Data is reset whenever the Space restarts.

Dataset: Improved CIC-IDS2017 (Engelen et al.). Runs on CPU.
