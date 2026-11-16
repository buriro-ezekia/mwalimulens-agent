# Private application hosting

This plan hosts the existing Python teacher workspace on a Linux CPU server.
It does not host Qwen or enable Bedrock inference. The initial hosted experience
uses authored demonstrations: fictional evidence, simulated review, explicit
confirmation and saved demonstration reopening. No GPU is required for this path.

## Deployment boundary

The current application binds to `127.0.0.1` and has a simulated reviewer,
not authenticated teacher accounts. Preserve that binding. Use an SSH tunnel
for a private presentation; do not expose port 8080 to the internet or change
the application to listen on all interfaces. This is a private demonstration,
not a public service or classroom deployment.

This guide does not provision AWS resources. Before provisioning, confirm the
permitted region, EC2 credit eligibility and spending limit. An
AWS login alone does not establish those facts. Select a supported Linux CPU
instance and persistent storage with the organiser; model/GPU hosting is separate.

## Server prerequisites

Use a Linux host with Python 3.11 or later, Node.js 20 or later, npm, Git and
Python venv support already installed. Install these using the operating system
and runtime providers' supported instructions. SSH must be restricted to your
current public IP (a single `/32` for IPv4), using an organiser-approved key.
Allow no inbound application port. Keep the SSH key outside the repository.

From the remote SSH session, prepare a dedicated checkout:

```bash
git clone --branch product-development --single-branch https://github.com/buriro-ezekia/mwalimulens-agent.git
cd mwalimulens-agent
python3 -m venv .venv
.venv/bin/python -m pip install -e .
npm ci --no-audit --no-fund
mkdir -p "$HOME/mwalimulens-hosted-demo"
.venv/bin/python -m mwalimulens.teacher_portal --demo candidate --port 8080 --no-open --output-dir "$HOME/mwalimulens-hosted-demo"
```

Run the final command in a persistent terminal session, such as tmux. It starts
an authored candidate, not a model-generated finding. The demonstration catalogue
also offers an authored error and saved demonstrations. Keep the output directory
on the persistent server volume; do not replace or delete existing cases.
Record the exact source commit with `git rev-parse HEAD` for the presentation.

## Open the private workspace from Windows

In a separate local PowerShell window, replace the three placeholder values
below with the approved SSH key path, operating-system login name and server
address. Keep this tunnel open while presenting:

```powershell
ssh -N -o ExitOnForwardFailure=yes -L 127.0.0.1:8080:127.0.0.1:8080 -i "C:\Keys\YOUR-KEY.pem" SERVER_USER@SERVER_ADDRESS
```

Visit `http://127.0.0.1:8080` on your laptop. This same-port tunnel works with
unchanged host validation: the browser sends `Host: 127.0.0.1:8080`, matching the
application's remote listening port.

### Use a different local port

An SSH tunnel forwards HTTP headers unchanged. A browser opening local port 8081
sends `Host: 127.0.0.1:8081`, even when SSH forwards the connection to remote port
8080. Without explicit configuration, the workspace correctly refuses this as
`403 Invalid local host`.

If local port 8080 is occupied, configure the remote workspace with
`--browser-port 8081` in addition to `--port 8080`. For an already-created case,
use the recovery procedure below. For the first start only, the command is:

```bash
.venv/bin/python -m mwalimulens.teacher_portal --demo candidate --port 8080 --browser-port 8081 --no-open --output-dir "$HOME/mwalimulens-hosted-demo"
```

Then use this tunnel in the laptop's PowerShell window:

```powershell
ssh -N -o ExitOnForwardFailure=yes -L 127.0.0.1:8081:127.0.0.1:8080 -i "C:\Keys\YOUR-KEY.pem" SERVER_USER@SERVER_ADDRESS
```

Visit `http://127.0.0.1:8081`. Keep the tunnel open; it normally prints no output.
The browser-port option permits only that explicit IPv4 loopback host and port;
it does not change the listener, accept arbitrary hosts or open a firewall port.
When an Origin is supplied on a teacher preview or confirmation POST, it must
match the Host used for that request. Existing form-token checks still apply. Use
`127.0.0.1` in the browser URL, as shown.

### Recover an existing 403 case without creating a new demonstration

Keep the existing output directory and saved case records. In the remote SSH
session, update the dedicated checkout and list the saved demonstrations:

```bash
cd "$HOME/mwalimulens-agent"
git pull --ff-only origin product-development
.venv/bin/python - <<'PYTHON'
from pathlib import Path
from mwalimulens.portal_demo import saved_demonstrations
root = Path.home() / "mwalimulens-hosted-demo"
for case in saved_demonstrations(root):
    print(case["run_id"], case["scenario"], case["created_at"])
PYTHON
```

The `demo-*` directory name is the case ID; its `portal_demo.json` manifest and
`state.json` remain unchanged by listing or reopening. Choose the existing case
whose identity and creation time match the demonstration to recover. If more than
one exists, do not infer the intended case solely from alphabetical order.

Replace the placeholder below with that existing `demo-*` case ID. Restart only
the named application session, using `--open-demo` to preserve the original case
and any recorded simulated decision:

```bash
ml_demo_id="demo-REPLACE_WITH_EXISTING_ID"
if tmux has-session -t mwalimulens 2>/dev/null; then
    tmux kill-session -t mwalimulens
fi
tmux new-session -d -s mwalimulens -c "$HOME/mwalimulens-agent" \
  ".venv/bin/python -m mwalimulens.teacher_portal --open-demo $ml_demo_id --port 8080 --browser-port 8081 --no-open --output-dir $HOME/mwalimulens-hosted-demo >>$HOME/mwalimulens-hosted-demo/server.log 2>&1"

curl --retry 8 --retry-connrefused --retry-delay 1 \
  --max-time 5 --retry-max-time 20 \
  -H 'Host: 127.0.0.1:8081' -fsS -o /dev/null -w 'HTTP %{http_code}\n' \
  http://127.0.0.1:8080/
```

Expect `HTTP 200` after startup. Keep or recreate the matching 8081-to-8080 tunnel
on the laptop, then refresh the browser. Reopening must show the same case ID and
preserve its review state. This recovery requires no new candidate, teacher
decision, model request, AWS instance or security-group rule.

## Acceptance and shutdown

Verify the authored label, supporting evidence, counter-evidence and uncertainty.
Preview a revision and return without saving: no decision or note should appear.
Then explicitly confirm one simulated revision and reopen the same saved demo;
its identity, reason, final wording and single profile note must remain intact.
Open a separate error demonstration and confirm it has no review controls.
These actions do not establish model reasoning or qualified teacher moderation.

Stopping the workspace or tunnel does not stop EC2 billing. Follow the organiser's
resource policy to stop or terminate the instance when no longer needed; retained
storage and other AWS resources may continue to incur charges. Export any needed
synthetic case records before deleting their storage.

A public HTTPS URL would require a separately reviewed access-control and
operation plan. Bedrock-generated candidates require the existing bounded
[Bedrock workflow](bedrock-review.md), approved inference access and credit coverage.

## Verification status

The initial hosting guide was preparation rather than a deployment result. The
operator subsequently reported a successful server-side `HTTP 200` and a browser
`403 Invalid local host` through a different local tunnel port. The latter exposed
the missing browser-port configuration in the original instructions.

The application changes have separate automated host/Origin and confirmation-flow
regressions. Actual recovery through the operator's AWS tunnel still requires the
updated server process and an observed browser result; software tests alone do
not establish that live deployment result. Credit eligibility, spending allowance
and real-model quality remain separate matters.
