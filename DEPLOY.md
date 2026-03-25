# Next Bazar — Deployment Guide

## Option 1: GitHub Pages (Free, Easiest — Static Dashboard)

Best for the current version with sample data. No server needed.

### Steps:
```bash
# 1. Create a GitHub repo
gh repo create tcb-bazardor --public

# 2. Initialize git and push
cd bajar_project
git init
git add dashboard.html
git commit -m "Initial dashboard"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/tcb-bazardor.git
git push -u origin main

# 3. Enable GitHub Pages
#    Go to: Settings → Pages → Source: "main" branch, folder: / (root)
#    Your site will be live at: https://YOUR_USERNAME.github.io/tcb-bazardor/
```

### To update:
```bash
git add dashboard.html
git commit -m "Update dashboard"
git push
```

---

## Option 2: Render.com (Free Tier — Flask Backend)

Best when you have real ML predictions and need an API backend.

### Steps:
```bash
# 1. Create requirements-deploy.txt
echo "flask==3.0.0
gunicorn==21.2.0
pandas==2.2.0" > requirements-deploy.txt

# 2. Create Procfile
echo "web: gunicorn server:app -b 0.0.0.0:\$PORT --workers 2" > Procfile

# 3. Push to GitHub (include server.py, dashboard.html, data/, models/)

# 4. Go to render.com → New Web Service → Connect your repo
#    Build command: pip install -r requirements-deploy.txt
#    Start command: gunicorn server:app -b 0.0.0.0:$PORT --workers 2
```

Free tier: 750 hours/month, auto-sleep after 15min inactivity.

---

## Option 3: Railway.app (Free Tier — Easy Deploy)

```bash
# 1. Install Railway CLI
npm install -g @railway/cli

# 2. Login and deploy
railway login
railway init
railway up

# 3. Set port
railway variables set PORT=5000
```

---

## Option 4: PythonAnywhere (Free — Python Hosting)

1. Sign up at pythonanywhere.com (free account)
2. Upload `server.py`, `dashboard.html`, and `data/` folder
3. Create a new web app → Flask → Python 3.10
4. Set the source code path and WSGI file to point to `server:app`
5. Your site: `https://YOUR_USERNAME.pythonanywhere.com`

---

## Option 5: Local Network (Quick Share)

Share on your local WiFi network immediately:

```bash
# Find your IP
hostname -I   # Linux
ipconfig       # Windows

# Run server
python server.py

# Others on same network open: http://YOUR_IP:5000
```

---

## Option 6: ngrok (Temporary Public URL)

Share instantly with anyone worldwide (temporary):

```bash
# 1. Install ngrok
# Download from ngrok.com or: snap install ngrok

# 2. Run your server
python server.py

# 3. In another terminal, expose it
ngrok http 5000

# You'll get a URL like: https://abc123.ngrok-free.app
# Share this URL — works on any phone or computer!
```

---

## Recommended Path

| Stage | Deploy Method | Cost |
|-------|--------------|------|
| Now (sample data) | **GitHub Pages** | Free |
| After ML models ready | **Render.com** or **PythonAnywhere** | Free |
| Quick demo/sharing | **ngrok** | Free |
| Production scale | VPS (DigitalOcean/AWS) | ~$5/mo |
