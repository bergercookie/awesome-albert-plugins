# Dockge - Albert plugin

## Description

Control the docker stacks of a running [Dockge](https://github.com/louislam/dockge)
server without leaving the keyboard.

Type `dockge ` and you get one result per stack, showing the state of its
containers. The first result is the one ENTER opens, so `dockge home` plus ENTER
takes you straight to that stack's page in the Dockge web UI. Everything else is
an action on the selected item.

## Usage

Type `dockge ` and you get one result per stack, showing the state of its
containers. Filter as you type - `dockge medi` narrows the list down to `media`.
The match is fuzzy, so `dockge mcs` still finds `my-compose-stack`, and a typo
still finds the stack you meant.

Every result carries these actions, which you reach with the usual Albert
<kbd>ALT</kbd>/<kbd>CTRL</kbd>/<kbd>SHIFT</kbd> + <kbd>ENTER</kbd> combinations:

| Action               | What it does                                            |
| -------------------- | ------------------------------------------------------- |
| `Open in browser`    | Opens the stack in the Dockge web UI                     |
| `Restart <stack>`    | Restarts the stack                                       |
| `Update <stack>`     | Pulls new images and recreates the stack                 |
| `Start <stack>`      | Starts the stack                                         |
| `Stop <stack>`       | Stops the stack                                          |
| `Refresh the stack list` | Asks Dockge for a fresh list                       |

So `dockge home` plus <kbd>ENTER</kbd> takes you straight to that stack's page in
the Dockge web UI.

If the search matches nothing, the result says so and <kbd>ENTER</kbd> brings the
full list back.

### Stacks served by another Dockge agent

If the Dockge you point the plugin at has other Dockge instances configured as
agents, their stacks show up too. Those results carry the serving agent in their
subtext, and their **Open in browser** action links to
`/compose/<stack>/<agent>`, which is the route Dockge needs to reach a stack that
does not live on the instance you are talking to. The search covers the agent
name as well, so `dockge xf85` lists everything that one agent is serving.

The icon and the subtext of a result tell you the state of the stack: `RUNNING`,
`UNHEALTHY`, `EXITED`, `DRAFT`, and so on, followed by the individual containers
of that stack, e.g. `UNHEALTHY | core: UNHEALTHY, addon: RUNNING`. The most
informative container wins, so a single unhealthy container is what you see.

Every action you trigger pops up an Albert notification when it is done. If the
server cannot be reached, the result is the error itself, with actions to retry it
or copy it to the clipboard.

## Configuration

Open the plugin's configuration window from the Albert settings and fill in:

| Setting             | Meaning                                                                   |
| ------------------- | ------------------------------------------------------------------------- |
| `server_url`        | The URL of your Dockge instance, e.g. `http://localhost:5001`              |
| `username`          | Your Dockge username - only if Dockge has authentication enabled           |
| `password`          | Your Dockge password - only if Dockge has authentication enabled           |
| `password_rbw_entry`| Name of a [rbw](https://github.com/doy/rbw) entry holding the password      |

### Keeping the password out of the config

If `password_rbw_entry` is set, it wins over `password` and the plugin asks
[rbw](https://github.com/doy/rbw) for the password instead, so the plaintext one
can be left empty. The entry name is what you would type in `rbw list`, and the
password is the entry's password field:

```bash
rbw add 'dockge' --username <your-dockge-username>
```

`rbw` is fetched from the password it returns, so it needs to be unlocked
(`rbw unlock`) in the session Albert runs in.

### Dockge without authentication

If your Dockge instance runs with authentication disabled you can leave the
username and password empty - the plugin then works with the session Dockge
hands out on connect.

## Notes

- Dockge has no REST API; the whole protocol is a socket.io conversation, so the
  plugin depends on [`python-socketio`](https://pypi.org/project/python-socketio/).
- That protocol is private and unpinned, so a Dockge upgrade can break the plugin
  with no changelog to warn you. It also does not send its events under their own
  names: everything arrives wrapped as `socket.emit("agent", <event>, ...)`, and
  the stack list only ever comes that way. Subscribing to a top-level
  `stackList` event yields a plugin that connects, logs in, and then silently
  shows nothing.
- The plugin keeps one connection open in the background and refreshes the list
  every 10 seconds, so the first query after a restart takes a moment and every
  query after that is instant.
- Whatever the URL is, it is contacted over plain HTTP. Put Dockge behind TLS (or
  a reverse proxy) if it is not on localhost.

## Installation instructions

Refer to the parent project: [Awesome albert plugins](https://github.com/bergercookie/awesome-albert-plugins)

## Self Promotion

If you find this tool useful, please [star it on Github](https://github.com/bergercookie/awesome-albert-plugins)

## TODO List

See [ISSUES list](https://github.com/bergercookie/awesome-albert-plugins/issues)
for the things that I'm currently either working on or interested in
implementing in the near future. In case there's something you're interested
in working on, don't hesitate to either ask for clarifications or just do it and
directly make a PR.
