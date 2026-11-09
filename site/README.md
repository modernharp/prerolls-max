# Website source

The Prerolls Max website (GitHub Pages) is built from this folder by
`scripts/build_site.py`. The release workflow runs it, through
`scripts/render_templates.py`, and publishes the result to the `gh-pages` branch.

- `site.css`, `site.js`: the stylesheet and the small script (copy buttons, mobile menu).
- `assets/fonts`: Oswald, Lora and JetBrains Mono, subset to Latin as WOFF2. Their licences are in `assets/fonts/licenses`.
- `assets/img`: the screenshots (the same files as `docs/images`), `social-preview.png`, and the app icons in `assets/icons`.
- The pages are written in `scripts/build_site.py`. The documentation pages are rendered from
  `frontend/src/help/*.md` (the in-app help) and `docs/features/*.md`, so they never drift from the app.

Preview locally, in a folder named like the repository so the paths match GitHub Pages:

    python scripts/build_site.py --repository owner/prerolls-max --out preview/prerolls-max
    python -m http.server 8000 --directory preview
    # open http://127.0.0.1:8000/prerolls-max/
