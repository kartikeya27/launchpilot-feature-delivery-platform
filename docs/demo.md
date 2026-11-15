# LaunchPilot product demonstration — 90–120 seconds

This demo records the **real Chromium UI** using the existing local Docker/Keycloak/PostgreSQL/Redis/Kafka stack. It is reproducible and uses only synthetic, staging-only data. It does **not** simulate public production traffic.

## Watch the recording on GitHub

1. Open [Product demonstration — browser recording](../.github/workflows/product-demo.yml) in the repository Actions tab.
2. Run the workflow manually (**Run workflow**), or open a successful push/PR run.
3. Under **Artifacts**, download **launchpilot-demo-video**. The ZIP contains `launchpilot-product-demo.webm`.
4. Download **product-demo-evidence** for the Playwright HTML report, screenshots and action/network trace.
5. These artifacts expire after **7 days**. To embed a permanent demo in the README, review the downloaded WebM and host it on a platform you control.

Because the actual recording requires a browser and running containers, the committed source contains the **repeatable recording script** and the GitHub workflow, not a fake or AI-rendered video.

## Demonstration storyboard and optional narration

| Screen | Approx. narration | What the real browser shows |
| --- | --- | --- |
| 0:00–0:15 | "LaunchPilot is a full-stack feature delivery control plane. Operators sign in using real OIDC roles and make targeted rollout decisions without redeploying an application." | Local Keycloak admin login and React overview |
| 0:15–0:35 | "I create an isolated staging checkout feature. It starts disabled. I show a small 10 percent rollout, then increase to 100 percent so this synthetic user is guaranteed to receive the feature in the demonstration." | Create flag, rollout slider 10% → 100%, enable |
| 0:35–0:55 | "Every evaluation uses deterministic SHA-256 bucketing and can apply country or plan rules. The result is stable for the same user and policy. Tracked exposures and conversions are stored in PostgreSQL." | Evaluation Lab, synthetic user, decision JSON, record conversion |
| 0:55–1:15 | "The transactional outbox separates the API transaction from the Kafka publisher. A consumer stores deduplicated receipts. These UI counters are database-based; they do not themselves prove broker uptime." | Operations pending/published/receipt panels |
| 1:15–1:35 | "I can immediately pause the feature through an audited manual rollback. Separately, an opt-in guardrail worker can disable unhealthy flags after enough samples in consecutive completed error or latency windows." | Operations rollback button and disabled state |
| 1:35–1:50 | "The audit trail captures who changed the configuration. The repository also verifies real Keycloak permissions, Kafka failure recovery, dead-letter quarantine, browser accessibility and Terraform syntax in GitHub Actions. This is a tested local architecture, not a public production deployment." | Audit history and final overlay |

The script deliberately **does not claim** the short browser recording triggers an SLO breach, replays a dead letter, tests a production outage, or deploys to GCP. Those behaviors are discussed with separate automated test and architecture evidence.

## Record locally (Mac, including Apple Silicon)

With Docker Desktop running from the repository root:

```bash
docker compose -f compose.production.yaml up --build -d
cd frontend
npm install
npx playwright install chromium
npx playwright test --config=playwright.demo.config.ts --headed
```

Find `video.webm` inside `frontend/test-results/` or open the HTML report. On GitHub, the workflow copies the recording to the clearly named `launchpilot-product-demo.webm` file.

To show detailed browser actions, open the trace:

```bash
npx playwright show-report
# Or use npx playwright show-trace path/to/trace.zip
```

**Recording security:** Only use the hardcoded local demo realm and disposable synthetic data. Traces and videos can expose browser state; do not record a real user's session, production tokens, or private customer information. The GitHub workflow artifact is visible to people who can access this public repository.

## Other demonstration artifacts

- [Architecture and design decisions](architecture.md)
- [Full-stack browser/Keycloak/Kafka CI](../.github/workflows/fullstack.yml)
- [Security checks](../.github/workflows/security.yml)
- [Terraform blueprint validation](../.github/workflows/terraform-validate.yml)
