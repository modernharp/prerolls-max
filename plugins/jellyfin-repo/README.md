# Prerolls Max Intros plugin catalog (Jellyfin)

Jellyfin can install and update Prerolls Max Intros from a plugin repository.
The release workflow (`.github/workflows/release.yml`) publishes the catalogs
to the repository's GitHub Pages site (the `gh-pages` branch):

- Jellyfin 12: `https://<owner>.github.io/<repo>/jellyfin/manifest.json`
- Jellyfin 10.11: `https://<owner>.github.io/<repo>/jellyfin/manifest-10.11.json`

Add the one for your server under **Dashboard > Plugins > Repositories**. Use
only the one that matches your server; when you upgrade Jellyfin from 10.11 to
12, switch the repository and install the 12 build.

`update_repository.py` reads a published GitHub release, checks that it holds
exactly one `PrerollsMax.Jellyfin-12-<v>.zip` and one
`PrerollsMax.Jellyfin-10.11-<v>.zip` (DLL, meta.json and thumbnail, with the
plugin's id and version), uploads `-repository.zip` copies with automatic
updates on, and adds them to the catalogs with their MD5 checksums. Versions
already in a catalog are never rewritten, so a release that doesn't change the
plugin version leaves the catalogs as they are.

```sh
# with the gh-pages branch checked out in ./site and GH_TOKEN set
python update_repository.py --repository OWNER/REPO --tag v1.0.0 --output site/jellyfin
python -m unittest test_repository   # the tests (CI runs them)
```
