# Natural State — Senior Data Scientist Take-Home Assessment

This repository contains my work for the Natural State Senior Data Scientist take-home project, covering two independent challenges:

1. **Bird Challenge** — Validating BirdNET acoustic predictions using calibration modelling and species-level thresholds
2. **Vegetation Challenge** — Building a QC/QA tool for herbaceous vegetation survey data collected via ODK

---

## Repository Structure

```
NS-Data-Science-Assessments/
├── bird_challenge/          # BirdNET calibration analysis and API
│   ├── bird_challenge.ipynb # Main analysis notebook
│   ├── requirements.txt     # Python dependencies
│   └── outputs/             # Summary CSVs and diagnostic plots
└── veg_qaqc_tool/           # Vegetation QC/QA full-stack tool
    ├── backend/             # FastAPI backend
    └── frontend/            # React/Vite frontend
```

---

## Bird Challenge

I built a calibration pipeline to assess whether BirdNET confidence scores can be reliably used as detection probabilities, and to derive per-species thresholds at 99% precision.

See [`bird_challenge/`](./bird_challenge/) for the full notebook and outputs.

## Vegetation Challenge

I built a full-stack QC/QA tool for vegetation plot survey data, implementing 14 automated checks across survey, plot, quadrat, and species levels.

See [`veg_qaqc_tool/`](./veg_qaqc_tool/) for the backend and frontend.
