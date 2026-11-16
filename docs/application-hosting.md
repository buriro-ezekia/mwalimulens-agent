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

No AWS resource has been created by this preparation. Before provisioning,
confirm the permitted region, EC2 credit eligibility and spending limit. An
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

Visit `http://127.0.0.1:8080` on your laptop. If that local port is occupied,
change the first `8080` in the forwarding specification to `8081` and visit
`http://127.0.0.1:8081`. Leave the remote application port unchanged.

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

The commands use existing application arguments. The SSH tunnel and actual AWS
server remain untested because no host, key, approved region or allocation limit
has been supplied. This guide is deployment preparation, not a deployment result.
