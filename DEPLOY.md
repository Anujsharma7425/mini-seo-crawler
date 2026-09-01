# Deployment Guide

Where to put this project so people can actually see it.

**The short version:** GitHub holds the code, Streamlit Community Cloud runs the live tool,
and Netlify (if you want it) hosts a project page that links to both.

---

## Why not Netlify for the crawler itself

Netlify hosts static files and short serverless functions. This crawler is neither:

- Netlify Functions run JavaScript, Go and Rust — not Python.
- Functions time out at 10 seconds (26 on Pro). A 100-page crawl takes 40–90 seconds.
- A crawler makes hundreds of outbound requests per run, which is not what a function is for.

So Netlify gets the **landing page** in `landing/`, and the working tool goes somewhere that
runs Python properly. Both are already set up in this repo.

---

## Step 1 — GitHub (do this first, it matters most)

This is the link that goes on your resume. Recruiters open the repo, not the demo.

```bash
cd mini-seo-crawler
git init
git add .
git commit -m "Mini SEO Crawler v1"
git branch -M main
git remote add origin https://github.com/YOUR-USERNAME/mini-seo-crawler.git
git push -u origin main
```

Then on the repo page:
- Add the description: *A Python crawler that audits a website's technical SEO and exports a severity-scored CSV/Excel report.*
- Add topics: `seo`, `python`, `web-crawler`, `technical-seo`, `beautifulsoup`, `pandas`
- Pin the repo on your GitHub profile
- Paste a screenshot of the console summary into the README

---

## Step 2 — Streamlit Community Cloud (the live demo)

Free, Python-native, connects straight to your GitHub repo. Takes about five minutes.

1. Go to [share.streamlit.io](https://share.streamlit.io) and sign in with GitHub.
2. **New app** → pick your repo → branch `main` → main file `app.py`.
3. Open **Advanced settings** and set the requirements file to `requirements-web.txt`.
4. Under **Secrets**, add:
   ```toml
   HOSTED = "1"
   ```
   This caps public crawls at 50 pages, forces a 0.3s delay and always respects robots.txt.
5. Deploy. You get a URL like `https://mini-seo-crawler.streamlit.app`.

Test it locally first:

```bash
pip install -r requirements-web.txt
streamlit run app.py
```

---

## Alternative — Hugging Face Spaces

Also free, and it never sleeps the way some free tiers do.

1. [huggingface.co/new-space](https://huggingface.co/new-space) → SDK: **Streamlit**.
2. Push this repo to the Space, or upload the files.
3. Rename `requirements-web.txt` to `requirements.txt` in the Space (Spaces looks for that name),
   or add a `requirements.txt` containing `streamlit` plus the existing lines.
4. Add `HOSTED=1` under Settings → Variables.

---

## Alternative — Render / Railway (if you want a real server)

`Procfile` and `runtime.txt` are already in the repo.

- **Render:** New → Web Service → connect the repo → Build command `pip install -r requirements-web.txt`,
  Start command `streamlit run app.py --server.port $PORT --server.address 0.0.0.0`.
- **Railway:** connect the repo; it reads the `Procfile` automatically.

Free tiers sleep after inactivity, so the first load can take 30 seconds.

---

## Step 3 — Netlify (the project page)

`landing/index.html` is a single static page that presents the project: what it does, a real
sample of the report, how the pipeline works, and links out to GitHub and the demo.

**Before deploying, open `landing/index.html` and replace:**

| Placeholder | Replace with |
|---|---|
| `YOUR-GITHUB-URL` | your repo URL |
| `YOUR-DEMO-URL` | your Streamlit / Spaces URL |
| `YOUR NAME` | your name, in the footer |
| `YOUR-NETLIFY-SITE` | your Netlify subdomain, in the canonical tag |

Also update the redirect URL in `netlify.toml`.

**Deploy, option A — drag and drop:**
Go to [app.netlify.com/drop](https://app.netlify.com/drop) and drag the `landing` folder in.
Live in about ten seconds, no account needed to start.

**Deploy, option B — from GitHub (better, auto-deploys on every push):**
1. Netlify → **Add new site** → **Import an existing project** → pick your repo.
2. Build command: leave empty. Publish directory: `landing`.
   (`netlify.toml` already sets this, so Netlify should fill it in for you.)
3. Deploy.

Then **Site configuration → Change site name** to something like `mini-seo-crawler`, so the URL
is `mini-seo-crawler.netlify.app` rather than a random string.

Since you own the domain side of this: the page already has a title, meta description, canonical
tag and Open Graph tags. Add your own analytics if you want them.

---

## Step 4 — GitHub Pages instead of Netlify

If you would rather not add another account, GitHub Pages hosts the same folder:

```bash
git subtree push --prefix landing origin gh-pages
```

Then Settings → Pages → source `gh-pages` branch → root. You get
`https://YOUR-USERNAME.github.io/mini-seo-crawler/`.

---

## Where this ends up on your resume

```
Mini SEO Crawler — Python
github.com/YOUR-USERNAME/mini-seo-crawler · mini-seo-crawler.streamlit.app
```

Two links: the code and something they can click and use. That combination is what makes a
project read as real rather than as a tutorial follow-along.

---

## A note on the public demo

Anyone with the link can point the hosted app at any website. The `HOSTED=1` caps keep that
polite — 50 pages maximum, a forced delay, robots.txt always respected, and a named User-Agent
so site owners can identify the traffic. Do not remove those caps on a public deployment.
