This is a Flask application for a website for ice hockey or football predictions, based on this [blog](https://blog.miguelgrinberg.com/post/the-flask-mega-tutorial-part-i-hello-world)

- [HTML basics](https://en.wikipedia.org/wiki/HTML#Markup)

- Deployed with [Render](https://dashboard.render.com/)

- Tickets on [Clickup](https://app.clickup.com/9004043647/v/b/4-90040090140-2)

- [Readme markups](https://docs.github.com/en/get-started/writing-on-github/getting-started-with-writing-and-formatting-on-github/basic-writing-and-formatting-syntax)

### To run it on dev

To switch between the ice hockey and football modes, go to _config.py_ file and change the **SPORT** variable accordingly.

While in the top directory and using an Ubuntu (wsl) terminal on VSCode, first install venv (if this is the first time you run it) ````python3 -m venv venv````, then activate it with ````source venv/bin/activate```` and install the requirements ````pip install -r requirements.txt```` (needed only the first time). Finally, just run ````flask run````.

The app requires `SECRET_KEY` to be set in `.env` or in the shell before startup. It is used to sign sessions and password-reset tokens.

### Git hooks

After cloning the repo, run `scripts/setup-git-hooks.sh` once. It sets `core.hooksPath` to the repo-local `.githooks` directory so Git uses the shared hooks in this project instead of your global `~/.git/hooks`.

The `.githooks/pre-push` hook runs automatically before every `git push` and blocks the push if any step fails:

1. **Tests** — runs the full suite with `python -m unittest tests` (uses `venv/bin/python` when present, otherwise `python3`).
2. **Dependency audit** — runs `pip-audit -r requirements.txt` to check for known vulnerabilities in pinned requirements (uses `venv/bin/pip-audit` when present, otherwise `pip-audit` on your `PATH`).

Make sure the virtualenv is created and dependencies are installed (`pip install -r requirements.txt`) before pushing, so both checks can run. To run the hook manually without pushing: `.githooks/pre-push`.

### Initial user setup

The first account to register on an empty database is promoted to admin automatically (the register route sets `is_admin=True` when the new user gets `id == 1`). Register that account through the website after running the database migrations.

Additional admins can be added or removed through the website by an existing admin. If you need to grant admin access on a database that already has users, set `is_admin=True` manually in the database for the account you want.

### Dev database setup

Initially, to create the database, run ````flask db init````, ````flask db migrate -m "Initial migration"````, ````flask db upgrade````.
For any subsequent change, run only ````flask db migrate -m "your change"```` and ````flask db upgrade````.
