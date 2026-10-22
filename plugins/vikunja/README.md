# Vikunja plugin for Albert launcher

Query, filter, complete and quickly add [Vikunja](https://vikunja.io) tasks from
[Albert launcher](https://albertlauncher.github.io/), using Vikunja's REST API
(`/api/v1` — there is no "v2" API, so use your instance's normal base URL).

## Install

1. Copy the `vikunja` folder (this one) into Albert's Python plugin directory:

   ```
   ~/.local/share/albert/python/plugins/vikunja
   ```

   so that `~/.local/share/albert/python/plugins/vikunja/__init__.py` exists.

2. In Albert, open **Settings → Plugins**, make sure the built-in **Python**
   plugin is enabled, then enable **Vikunja** in the list underneath it.

3. Click **Vikunja** in the plugin list to open its settings and fill in:
   - **Vikunja base URL** — e.g. `https://vikunja.example.com` (just the
     instance URL; the plugin appends `/api/v1` itself).
   - **API token** — create one in Vikunja under **Settings → API Tokens**.
     Grant it read/write on tasks, projects and labels.
   - **Default project** — which project new tasks go into when you don't
     specify one with `+project`.
   - **Verify TLS certificate** — turn off only if your instance uses a
     self-signed certificate.

No `metadata.json` is needed — plugin metadata lives in the `md_*` variables
at the top of `__init__.py`.

## Usage

Type `v ` (the trigger, with a trailing space) to start.

**Predefined filters** — shown as a menu when you just type `v `, or jump
straight to one:

- `v today` — tasks due today
- `v overdue` — open tasks past their due date
- `v all` — all open (not-done) tasks

Press **Tab** on a menu entry to drop its keyword into the query, or **Enter**
to open the equivalent view in your browser.

**Fuzzy search** — anything else you type is matched against both the title
and the description of your open tasks, e.g. `v invoice` or a partial/typo'd
word. When nothing matches, the result turns into an add-task preview instead:
**Enter** creates the task with what you typed as its title (the Quick Add
Magic below still applies), rather than opening Vikunja.

**Adding tasks** — type `v add ` followed by the task text, using Vikunja's
Quick Add Magic syntax:

- `+Project` — put the task in a project (quote multi-word names: `+"Home Move"`)
- `*label` — attach a label, repeatable (`*urgent *home`); labels that don't
  exist yet are created automatically, same as in the Vikunja web app
- `!1`–`!5` — priority (5 = DO NOW)
- natural-language due dates: `today`, `tomorrow`, `tonight`, `next monday`,
  `friday`, `this weekend`, `next week`, `next month`, `end of month`,
  `in 3 days`, `in 2 hours`, `in 30 minutes`, explicit dates
  (`23/12/2026`, `23.12.2026`, `2026-12-23`), plus an optional `at 5pm` /
  `at 17:30` time
- wrap the whole text in quotes to turn off all of the above and use it
  literally as the title

As you type, the top result previews exactly what will be created (project,
labels, priority, due date). Press **Enter** on it to create the task; Albert
shows a desktop notification once it's done (or if something went wrong).

If no `+project` is given, the task goes into your configured default
project.

**Acting on a task** — select any task (from a filter or a search) to get:

- **Mark as done** / **Mark as not done** (toggles)
- **Open in Vikunja** — opens the task in your browser
- **Delete task** — Vikunja soft-deletes for 30 days, so this is recoverable
  from the trash on the server if you change your mind

## Notes and limitations

- "Today" and "overdue" use Vikunja's server-side filter query
  (`due_date`/`now/d` date math), evaluated in the server's own timezone — if
  tasks near midnight look off by an hour or two, that's a timezone mismatch
  between the server and where you are; there's no per-request override wired
  up here.
- Search fetches your open (not-done) tasks and fuzzy-matches them locally,
  so it also matches on description text, not just the title.
- "in 3 months" / "in 2 years" use a flat 30-/365-day approximation rather
  than true calendar months/years.
- Marking a task done/not-done re-fetches the task first and sends the whole
  object back — Vikunja's update endpoint replaces the record wholesale, so
  a partial `{"done": true}` body would otherwise wipe the title and other
  fields.
