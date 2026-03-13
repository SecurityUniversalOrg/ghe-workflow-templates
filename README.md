# platform-workflow-templates

Organization-wide **workflow templates** for GitHub Actions.
Place these in a repo named `platform-workflow-templates` and enable **Workflow templates** in your org so teams can pick them via **Actions → New workflow → Configure**.

Each template lives under `.github/workflow-templates/` and includes a matching `*.properties.json` file to drive the UI form fields and help text.

## Contents

- **Container supply chain**
  - `container-build-scan-sign-push.yml` – standard container pipeline (daemon or OCI dir)
  - `container-cascade-rebuilds.yml` – dependency-based rebuilds + repo_dispatch
- **Infrastructure as Code**
  - `iac-plan-apply-aws.yml`, `iac-plan-apply-azure.yml`, `iac-plan-apply-gcp.yml`
- **ARC operations**
  - `arc-runner-set-deploy.yml` – install ARC runner sets via Helm/Helmfile
- **Security**
  - `security-gate.yml` – Trivy (vuln+secret), Syft SBOM, Cosign sign/attest
- **Events**
  - `repo-dispatch-receiver.yml` – echo incoming `repository_dispatch`
- **Release / tagging**
  - `release-semver-tag.yml` – version bump & tag (protected by required checks)


## User Guides
[Add Runner Groups to Repo](.github/workflow-templates/user_guides/Add_Runner_Groups_to_Repo.md)

[Create Enterprise Repository](.github/workflow-templates/user_guides/Create_Enterprise_Repository.md)

[Request Commercial to Federal Sync](.github/workflow-templates/user_guides/Request_Commercial_to_Federal_Sync.md)