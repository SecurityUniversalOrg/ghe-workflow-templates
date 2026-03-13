# Request Commercial-to-Federal Repository Sync - User Guide

This document explains how to use the **Request commercial-to-federal repo sync** GitHub Actions workflow to request synchronization of a repository from a **commercial GitHub organization** to a **federal GitHub organization**.

This workflow is designed to support controlled repository promotion into a **federal environment**, ensuring that requests are validated, documented, and approved before any manual or automated synchronization activities occur.

---

# Overview

The **Request commercial-to-federal repo sync** workflow allows users to submit a request to synchronize a repository from a **commercial GitHub organization** into a **federal GitHub organization**.

This process ensures:

- proper request validation
- justification documentation
- approval before implementation
- auditable request records
- consistent sync request documentation

This workflow **does not automatically perform the sync**.  
Instead, it creates a **validated and approved request** and prints **manual implementation instructions** for the responsible platform team.

---

# Workflow Name

Request commercial-to-federal repo sync


---

# Trigger

This workflow is triggered manually using **workflow_dispatch**.

Users must provide required inputs when starting the workflow.

---

# What This Workflow Does

The workflow executes in two phases:

## Phase 1 — Submit Sync Request

The first job:

- validates the request
- verifies repository information
- validates the justification
- builds a standardized request summary
- prints the request summary with status **PENDING**

This phase creates the **audit record of the request**.

---

## Phase 2 — Approval Gate

The second job:

- requires approval via a protected environment
- prints the approved request summary
- outputs **manual implementation instructions**

This ensures repository synchronization is controlled and compliant with enterprise and federal governance requirements.

---

# Required Permissions

The workflow requires only minimal permissions:

```yaml
permissions:
  contents: read
````

Administrative actions are **not performed by this workflow**, which is why elevated permissions are not required.

---

# Workflow Inputs

The workflow requires the following inputs when manually triggered.

---

## `repo_name`

The name of the repository that exists in the **commercial GitHub organization**.

**Required:** Yes
**Type:** `string`

Example:

```
terraform-network-core
```

---

## `repo_type`

The classification of the repository.

This helps determine the appropriate governance, scanning requirements, and review procedures.

**Required:** Yes
**Type:** `choice`

Supported values:

```
app
library
terraform
image
docker
helm
configuration
cicd
```

---

## `commercial_org`

The GitHub organization where the **source repository currently exists**.

**Required:** Yes
**Default:**

```
SecurityUniversalOrg
```

Example:

```
SecurityUniversalOrg
```

---

## `federal_org`

The GitHub organization where the repository will be synchronized.

This typically represents a **FedRAMP or government-controlled GitHub environment**.

**Required:** Yes
**Default:**

```
SecurityUniversalOrg-Federal
```

Example:

```
SecurityUniversalOrg-Federal
```

---

## `justification`

A written explanation describing **why the repository must be synchronized into the federal environment**.

This field is used for **audit and compliance documentation**.

**Required:** Yes
**Type:** `string`

Example:

```
Repository contains Terraform modules required for deployment of federal infrastructure.
```

---

# How to Run the Workflow

1. Navigate to the repository containing this workflow.
2. Open the **Actions** tab.
3. Select **Request commercial-to-federal repo sync**.
4. Click **Run workflow**.
5. Enter the required values:

   * `repo_name`
   * `repo_type`
   * `commercial_org`
   * `federal_org`
   * `justification`
6. Start the workflow.
7. Review the generated **sync request summary**.
8. Wait for an authorized approver to approve the request.
9. After approval, follow the **manual implementation instructions**.

---

# Example Request

Example manual workflow input:

```
repo_name: terraform-network-core
repo_type: terraform
commercial_org: SecurityUniversalOrg
federal_org: SecurityUniversalOrg-Federal
justification: Terraform modules required for deployment of federal cloud networking infrastructure.
```

---

# Jobs

---

# Job 1 — `request`

**Name:** `Submit sync request`
**Runner:** `federal`

This job validates the request and creates a formal sync request record.

---

## Steps

### Checkout

Checks out the workflow repository.

```
SecurityUniversalOrg/ghe-actions/actions/checkout@v1
```

---

### Validate sync request

This step validates:

* repository name
* repository type
* commercial organization
* federal organization
* justification text

Action used:

```
SecurityUniversalOrg/ghe-actions/actions/validate-commercial-to-federal-sync-request@v1
```

Inputs validated:

* `repo_name`
* `repo_type`
* `commercial_org`
* `federal_org`
* `justification`

The validation step ensures:

* required fields are present
* repository naming standards are met
* organizations are valid
* justification text exists

---

### Build sync request summary

This step generates a structured summary of the request.

Action used:

```
SecurityUniversalOrg/ghe-actions/actions/build-commercial-to-federal-sync-summary@v1
```

The output includes a JSON summary containing:

* repository name
* repository type
* source organization
* target organization
* justification
* request metadata

---

### Print request summary

This step prints the request summary in the workflow logs.

Action used:

```
SecurityUniversalOrg/ghe-actions/actions/print-commercial-to-federal-sync-summary@v1
```

The request is displayed with the status:

```
PENDING
```

This allows reviewers to verify the request before approval.

---

# Job 2 — `approval`

**Name:** `Approval required`
**Runner:** `federal`

This job requires approval before proceeding.

---

## Protected Environment

The job runs within the environment:

```
repo-sync-federal-approval
```

If environment protection rules are enabled, this step may require:

* manual approval
* restricted reviewers
* compliance validation
* change management approval

This environment acts as the **control gate** for repository promotion into the federal environment.

---

## Steps

---

### Checkout

Checks out the workflow repository.

```
SecurityUniversalOrg/ghe-actions/actions/checkout@v1
```

---

### Print approved request summary

Once approved, the workflow prints the request summary again.

Action used:

```
SecurityUniversalOrg/ghe-actions/actions/print-commercial-to-federal-sync-summary@v1
```

The status is displayed as:

```
APPROVED
```

This provides a clear audit trail that the request has been authorized.

---

### Print manual implementation instructions

The final step prints the instructions required to perform the synchronization.

Action used:

```
SecurityUniversalOrg/ghe-actions/actions/print-commercial-to-federal-manual-next-steps@v1
```

These instructions typically include guidance such as:

* how to create the federal repository
* how to mirror the commercial repository
* how to sanitize or filter sensitive content
* how to configure federal repository controls
* how to verify the sync

The exact instructions depend on the implementation of the action.

---

# Workflow Outputs

The `request` job passes the following outputs to the approval job:

```
repo_name
repo_type
commercial_org
federal_org
justification
request_summary_json
```

These outputs ensure the approval phase uses the **exact validated request data**.

---

# Repository Types

The `repo_type` value provides classification for governance and review processes.

---

## app

Application repositories containing deployable services or software.

---

## library

Reusable shared libraries, SDKs, or internal frameworks.

---

## terraform

Infrastructure-as-Code repositories managing Terraform modules or infrastructure deployments.

---

## image

Repositories used to build VM images or machine images.

---

## docker

Repositories containing Dockerfiles or container image definitions.

---

## helm

Repositories containing Helm charts for Kubernetes deployments.

---

## configuration

Repositories containing configuration files, policy definitions, or operational settings.

---

## cicd

Repositories containing CI/CD pipeline definitions and automation workflows.

---

# Review and Approval Process

The workflow intentionally separates **request submission** from **approval**.

This supports enterprise governance and compliance frameworks by ensuring:

* all sync requests are documented
* approvals are recorded
* changes to federal environments are controlled
* audit records are maintained

---

# Expected End State

After approval, the workflow will:

1. Print the approved request summary.
2. Output the instructions for performing the synchronization.

Actual repository synchronization is then performed by the responsible team.

---

# Common Failure Points

---

## Validation Failure

The workflow may fail if:

* repository name is invalid
* repository type is unsupported
* organization names are incorrect
* justification text is missing

Check logs for:

```
Validate sync request
```

---

## Approval Delay

If the workflow pauses after the request stage, it likely requires approval for the environment:

```
repo-sync-federal-approval
```

An authorized reviewer must approve the request.

---

# Operational Guidance

---

## Before Running the Workflow

Ensure the following:

* the repository exists in the commercial organization
* the repository is eligible for federal synchronization
* sensitive or non-compliant code has been reviewed
* justification clearly explains the need for synchronization

---

## During Review

Reviewers should verify:

* repository name
* repository type
* justification validity
* commercial organization
* federal organization

Approval should only be granted if the repository is appropriate for the federal environment.

---

## After Approval

The responsible team should:

1. Follow the printed instructions.
2. Perform the repository synchronization.
3. Validate repository configuration in the federal organization.
4. Apply any required federal controls.

---

# Example Workflow Execution

Typical request lifecycle:

1. Developer submits a repository sync request.
2. Workflow validates request inputs.
3. Request summary is printed with **PENDING** status.
4. Approver reviews request.
5. Approver approves the protected environment.
6. Workflow prints **APPROVED** summary.
7. Workflow prints manual synchronization instructions.
8. Platform team performs the repository sync.

---

# Related Enterprise Actions

This workflow uses the following reusable actions:

```
SecurityUniversalOrg/ghe-actions/actions/checkout@v1
SecurityUniversalOrg/ghe-actions/actions/validate-commercial-to-federal-sync-request@v1
SecurityUniversalOrg/ghe-actions/actions/build-commercial-to-federal-sync-summary@v1
SecurityUniversalOrg/ghe-actions/actions/print-commercial-to-federal-sync-summary@v1
SecurityUniversalOrg/ghe-actions/actions/print-commercial-to-federal-manual-next-steps@v1
```

---

# Suggested File Location

Recommended documentation location:

```
docs/commercial-to-federal-repo-sync-user-guide.md
```

or

```
README.md
```

---

# Notes

This workflow is designed to support **controlled repository promotion into federal environments**, enabling compliance with governance frameworks such as:

* FedRAMP
* NIST 800-53
* CMMC
* enterprise change management policies

```
```
