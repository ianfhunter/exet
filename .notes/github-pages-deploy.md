# GitHub Pages deploy workflow

Use **Actions → Deploy GitHub Pages → Run workflow** to publish a branch to
your fork's GitHub Pages site.

## Setup (once per fork)

1. **Settings → Pages → Build and deployment → Source:** GitHub Actions
2. Merge `.github/workflows/deploy-github-pages.yml` into your fork's default
   branch (manual workflows only appear from the default branch).

## Deploy

1. Open **Actions → Deploy GitHub Pages**
2. Click **Run workflow**
3. Enter the branch to deploy (for example `most_constrained`)
4. Run

The workflow copies the branch into a staging directory, rewrites Exolve
`href`/`src` paths in the main HTML entry points to load from
`https://viresh-ratnakar.github.io/`, then deploys that staging copy. Source
files in the branch are not modified or committed.
