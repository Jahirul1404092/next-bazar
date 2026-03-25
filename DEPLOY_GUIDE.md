# Next Bazar — Deployment Guide

## Quick Deploy (5 minutes)

### Prerequisites
- [Git](https://git-scm.com/downloads) installed
- [GitHub CLI](https://cli.github.com/) installed and authenticated (`gh auth login`)
- A GitHub account

### Step 1: Deploy with one command

```bash
cd bajar_project
python deploy_github.py --repo YOUR_USERNAME/bajar-price-prediction
```

This will:
- Create a GitHub repository
- Push all code and data
- Trigger the first build

### Step 2: Enable GitHub Pages

1. Go to your repo: `https://github.com/YOUR_USERNAME/bajar-price-prediction`
2. Click **Settings** → **Pages**
3. Under "Source", select **Deploy from a branch**
4. Select branch: **gh-pages**, folder: **/ (root)**
5. Click **Save**

### Step 3: Access your dashboard

Your dashboard will be live at:
```
https://YOUR_USERNAME.github.io/bajar-price-prediction/
```

---

## How It Works

### Daily Auto-Update (GitHub Actions)

Every day at **9:00 AM BDT** (3:00 AM UTC), a GitHub Actions workflow automatically:

1. **Scrapes** new price data from tcb.gov.bd
2. **Processes** the data (clean + feature engineering)
3. **Retrains** ML models (XGBoost, LightGBM, Prophet)
4. **Generates** fresh `dashboard_data.js` with new predictions
5. **Deploys** the updated dashboard to GitHub Pages

The workflow file is at `.github/workflows/daily_update.yml`.

### Manual Trigger

To trigger an update manually:
- Go to **Actions** tab → **Daily Price Update & Deploy** → **Run workflow**
- Or from CLI: `gh workflow run daily_update.yml`

---

## Manual Deploy (without GitHub CLI)

If you don't have `gh` CLI:

```bash
cd bajar_project

# Initialize git
git init
git branch -M main

# Add all files
git add -A
git commit -m "Initial commit: Next Bazar Price Prediction Dashboard"

# Create repo on github.com manually, then:
git remote add origin https://github.com/YOUR_USERNAME/bajar-price-prediction.git
git push -u origin main
```

Then enable GitHub Pages as described in Step 2 above.

---

## Architecture

```
GitHub Repository (main branch)
├── scraper.py              # Scrapes TCB data
├── process_data.py         # Cleans + feature engineering
├── model.py                # Trains XGBoost/LightGBM/Prophet
├── generate_dashboard_data.py  # Creates dashboard_data.js
├── dashboard.html          # Interactive dashboard
├── data/raw_daily/         # Daily price CSVs (incremental)
├── data/all_prices_*.csv   # Merged + cleaned data
└── .github/workflows/      # Daily auto-update workflow

GitHub Pages (gh-pages branch)  ← PUBLIC
├── index.html              # Dashboard (copied from dashboard.html)
└── dashboard_data.js       # Real data + ML predictions
```

---

## Cost

- **GitHub Pages**: Free (100GB bandwidth/month — handles 10K+ users/day)
- **GitHub Actions**: Free (2,000 minutes/month — pipeline uses ~10 min/day)
- **Total**: $0/month

---

## Troubleshooting

### Workflow failed
- Check **Actions** tab for error logs
- Common issue: TCB website down on weekends/holidays (workflow handles this gracefully)

### Dashboard not loading
- Ensure gh-pages branch exists (created after first workflow run)
- Check Settings → Pages → Source is set to `gh-pages`

### Data not updating
- TCB doesn't publish on Fridays (Bangladesh weekend) and holidays
- Check scraper.log for network errors
