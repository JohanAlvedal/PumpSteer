# PumpSteer Documentation

This folder contains the source for the [PumpSteer GitHub Pages site](https://johanalvedal.github.io/PumpSteer/).

Built with [Jekyll](https://jekyllrb.com/) and the [Just the Docs](https://just-the-docs.com/) theme.

---

## File structure

```
docs/
├── _config.yml           ← Jekyll + Just the Docs configuration
├── Gemfile               ← Ruby dependencies
├── index.md              ← Landing page
└── docs/
    ├── INSTALLATION.md
    ├── Configuration.md
    ├── DASHBOARD.md
    ├── ARCHITECTURE.md
    ├── TUNING.md
    ├── ROADMAP.md
    ├── TROUBLESHOOTING.md
    ├── CHANGELOG.md
    └── DECISIONS.md

.github/workflows/
└── deploy-pages.yml      ← Auto-deploys on push to main
```

---

## Local preview

```bash
cd docs
bundle install
bundle exec jekyll serve
# → http://localhost:4000/PumpSteer/
```

Requires Ruby 3.x and Bundler.

---

## Deployment

The GitHub Actions workflow in `.github/workflows/deploy-pages.yml` builds and
deploys the site automatically on every push to `main`.

To enable GitHub Pages:
1. Go to **Settings → Pages** in your repository
2. Set **Source** to **GitHub Actions**
3. Push to `main` — the workflow handles the rest

---

## Keeping docs up to date

When releasing a new version:

1. Update `CHANGELOG.md` — add a new `## [x.y.z]` section at the top
2. Update `ROADMAP.md` — move delivered items to the relevant version section
3. Update any changed settings in `Configuration.md`
4. Push to `main` — site rebuilds automatically

Version numbers in the docs use `x.y.z` format. Do not hardcode specific versions
in prose — reference "current version" and link to the Changelog instead.
