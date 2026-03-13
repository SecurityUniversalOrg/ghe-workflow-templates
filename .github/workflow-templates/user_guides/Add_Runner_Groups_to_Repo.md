# Add Runner Groups to Repository - User Guide

This document explains how to use the **Add runner groups to repository** GitHub Actions workflow to assign approved **GitHub Actions runner groups** to a repository within the `SecurityUniversalOrg` organization.

This workflow ensures that access to **self-hosted GitHub Actions runners** is controlled, validated, and approved before changes are applied.

---

# Overview

The **Add runner groups to repository** workflow allows authorized users to request that a repository be granted access to one or more **GitHub Actions runner groups**.

Runner groups control **which repositories are allowed to use specific self-hosted runners**. This workflow enforces enterprise governance by:

- validating the repository exists
- validating the runner group request
- generating a request summary
- requiring approval before applying changes
- assigning the repository to the selected runner group

This design provides:

- controlled runner access
- governance and auditability
- separation between request and approval
- standardized configuration

---

# Workflow Name

Add runner groups to repository

---

# Trigger

This workflow is manually triggered using **workflow_dispatch**.

Users must provide required inputs when launching the workflow.

---

# What This Workflow Does

The workflow runs in two phases.

---

## Phase 1 — Validate Request

The first job:

- builds a JSON representation of the requested runner group
- validates the repository
- validates the runner group request
- confirms runner group IDs exist
- prints a request summary

This phase ensures the request is valid before any change is made.

---

## Phase 2 — Approval and Apply

The second job:

- requires approval through a protected environment
- prints the approved request summary
- assigns the repository to the requested runner group(s)

This phase applies the configuration change after approval.

---

# Required Permissions

The workflow itself requires minimal permissions:

```yaml
permissions:
  contents: read
````

However, the final step requires an administrative token.

---

# Required Secrets

The following secret must exist:

```
RUNNER_GROUP_ADMIN_TOKEN
```

This token must have sufficient permissions to manage **organization runner groups**.

It is used to:

* assign repositories to runner groups

---

# Organization Configuration

The workflow uses the following environment configuration:

```yaml
env:
  GITHUB_HOST: github.com
  GITHUB_ORG: SecurityUniversalOrg
```

This means the workflow will operate within:

* **GitHub host:** `github.com`
* **Organization:** `SecurityUniversalOrg`

---

# Workflow Inputs

The workflow requires the following inputs when manually triggered.

---

## `repo_name`

The repository name that should be granted access to the runner group.

Do **not** include the organization prefix.

**Required:** Yes
**Type:** `string`

Example:

```
terraform-network-core
```

The workflow will resolve this to:

```
SecurityUniversalOrg/terraform-network-core
```

---

## `runner_group`

The runner group that should be assigned to the repository.

**Required:** Yes
**Type:** `choice`

Supported values:

```
sec-scan
fed-testing
container-build
iac-build-deploy
k8s-deploy
lang-runtime
```

Each runner group represents a specific class of workloads and compute environments.

---

# Runner Group Descriptions

## `sec-scan`

Used for **security scanning workloads**.

Typical workloads include:

* SAST scanning
* SCA dependency analysis
* container vulnerability scanning
* secret scanning
* policy enforcement

---

## `fed-testing`

Used for **federal testing pipelines**.

Typical workloads include:

* compliance testing
* integration testing
* validation against federal environments
* regression testing for regulated workloads

---

## `container-build`

Used for **container image builds**.

Typical workloads include:

* Docker builds
* OCI image creation
* image signing
* container vulnerability scanning
* artifact publishing

---

## `iac-build-deploy`

Used for **Infrastructure-as-Code pipelines**.

Typical workloads include:

* Terraform validation
* Terraform plan
* Terraform apply
* infrastructure drift detection

---

## `k8s-deploy`

Used for **Kubernetes deployments**.

Typical workloads include:

* Helm deployments
* Kubernetes manifest deployments
* cluster configuration updates
* GitOps workflows

---

## `lang-runtime`

Used for **language runtime builds and testing**.

Typical workloads include:

* Java builds
* Python pipelines
* Node.js builds
* Go compilation
* application testing

---

# How to Run the Workflow

1. Open the repository containing this workflow.
2. Navigate to the **Actions** tab.
3. Select **Add runner groups to repository**.
4. Click **Run workflow**.
5. Enter the required inputs:

   * `repo_name`
   * `runner_group`
6. Start the workflow.
7. Review the request summary printed by the first job.
8. Wait for an authorized approver to approve the change.
9. After approval, the runner group assignment will be applied.

---

# Example Request

Example workflow input:

```
repo_name: terraform-network-core
runner_group: iac-build-deploy
```

This would grant the repository access to runners capable of executing **Terraform pipelines**.

---

# Jobs

---

# Job 1 — `request`

**Name:** `Validate request`
**Runner:** `federal`

This job validates the request and generates the runner group configuration plan.

---

## Steps

---

### Checkout

Checks out the repository containing the workflow.

Action used:

```
SecurityUniversalOrg/ghe-actions/actions/checkout@v1
```

---

### Build runner group JSON

This step converts the selected runner group input into a JSON structure used by later steps.

Action used:

```
SecurityUniversalOrg/ghe-actions/actions/build-runner-group-json@v1
```

Example output:

```json
["iac-build-deploy"]
```

---

### Validate runner group request

This step validates:

* the repository exists
* the organization exists
* the runner group exists
* the runner group ID can be resolved

Action used:

```
SecurityUniversalOrg/ghe-actions/actions/validate-runner-group-request@v1
```

Inputs validated:

* GitHub host
* organization
* repository name
* runner group names

Outputs include:

* validated repository name
* runner group IDs
* normalized runner group names

---

### Print request summary

This step prints the requested change before approval.

Action used:

```
SecurityUniversalOrg/ghe-actions/actions/print-runner-group-request-summary@v1
```

The summary typically includes:

* GitHub host
* organization
* repository name
* runner group names

This allows reviewers to confirm the request before approval.

---

# Job 2 — `apply`

**Name:** `Approve and add runner groups`
**Runner:** `federal`

This job applies the configuration after approval.

---

## Protected Environment

This job runs in the protected environment:

```
runner-group-admin-prod
```

If environment protection rules are enabled, this job may require:

* manual approval
* restricted reviewers
* change management authorization
* audit logging

This environment acts as the **governance gate** for runner group access.

---

## Steps

---

### Checkout

Checks out the repository containing the workflow.

```
SecurityUniversalOrg/ghe-actions/actions/checkout@v1
```

---

### Print approved request

After approval, the workflow prints the request summary again.

Action used:

```
SecurityUniversalOrg/ghe-actions/actions/print-runner-group-request-summary@v1
```

This provides a clear audit trail showing that the request was approved.

---

### Add repository to runner groups

This step assigns the repository to the requested runner group.

Action used:

```
SecurityUniversalOrg/ghe-actions/actions/gh-add-repo-to-runner-groups@v1
```

Inputs include:

* GitHub host
* organization
* repository name
* runner group names
* administrative GitHub token

The repository will then be allowed to run workflows using runners from that group.

---

# Workflow Outputs

The `request` job passes the following outputs to the `apply` job:

```
github_host
org
repo_name
runner_group_names_json
runner_group_ids_json
```

These outputs ensure that the apply phase uses **validated request data**.

---

# Review and Approval Model

This workflow separates **request validation** from **administrative execution**.

Benefits include:

* controlled access to runner infrastructure
* governance of compute resources
* security oversight
* auditability

Runner groups often represent **sensitive infrastructure**, so approval is required before repositories are granted access.

---

# Expected End State

After successful completion:

* the repository will be added to the requested runner group
* the repository will be allowed to use runners in that group
* the workflow logs will contain a full audit trail of the change

---

# Common Failure Points

---

## Repository Not Found

The workflow will fail if the repository does not exist.

Verify the repository name and organization.

---

## Runner Group Not Found

The workflow will fail if the selected runner group does not exist.

Check the list of supported runner groups.

---

## Approval Pending

If the workflow pauses, approval is required for the environment:

```
runner-group-admin-prod
```

An authorized reviewer must approve the request.

---

## Insufficient Token Permissions

If the workflow fails during assignment, the token may not have sufficient permissions.

Ensure:

```
RUNNER_GROUP_ADMIN_TOKEN
```

has appropriate organization permissions.

---

# Operational Guidance

---

## Before Running

Confirm:

* the repository exists
* the repository requires access to the runner group
* the correct runner group is selected

---

## During Review

Reviewers should verify:

* repository name
* organization
* runner group requested
* justification or operational need

---

## After Completion

Verify:

* the repository can access the assigned runner group
* workflows can execute using runners in that group
* no unintended access has been granted

---

# Example Execution Flow

1. Developer requests runner group access.
2. Workflow validates the request.
3. Request summary is printed.
4. Approver reviews request.
5. Approver approves the protected environment.
6. Workflow assigns the repository to the runner group.
7. Audit logs capture the configuration change.

---

# Related Enterprise Actions

This workflow uses the following reusable actions:

```
SecurityUniversalOrg/ghe-actions/actions/checkout@v1
SecurityUniversalOrg/ghe-actions/actions/build-runner-group-json@v1
SecurityUniversalOrg/ghe-actions/actions/validate-runner-group-request@v1
SecurityUniversalOrg/ghe-actions/actions/print-runner-group-request-summary@v1
SecurityUniversalOrg/ghe-actions/actions/gh-add-repo-to-runner-groups@v1
```

---

# Suggested Documentation Location

This guide can be stored as:

```
docs/add-runner-groups-to-repository.md
```

or included directly in:

```
README.md
```

depending on your repository documentation structure.

```
```
