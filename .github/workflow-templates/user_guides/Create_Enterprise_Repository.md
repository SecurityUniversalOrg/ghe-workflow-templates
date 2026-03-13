# Create Enterprise Repository - User Guide

This document explains how to use the **Create enterprise repository** GitHub Actions workflow to provision and configure a new repository in the `SecurityUniversalOrg` GitHub organization.

---

## Overview

The **Create enterprise repository** workflow is a manually triggered GitHub Actions workflow that standardizes the creation of new repositories across the enterprise. It validates the request, builds a configuration plan, displays the planned settings for review, and then creates and configures the repository with the required enterprise controls.

This workflow helps ensure that every new repository is created consistently with:

* approved repository naming and type validation
* enterprise templates
* baseline repository settings
* team-based access assignments
* organization ruleset enrollment
* runner group assignment
* repository environment creation
* auditable summary output

---

## Workflow Name

`Create enterprise repository`

---

## Trigger

This workflow is started manually using `workflow_dispatch`.

You must provide the required inputs when launching the workflow from the GitHub Actions UI.

---

## What This Workflow Does

The workflow runs in two major phases:

### 1. Validate and Build Request

The first job validates the request and generates the complete enterprise configuration plan for the new repository.

This phase:

* validates the repository name, type, and visibility
* normalizes the requested repository type
* builds the enterprise creation plan
* determines the template repository
* determines default branch settings
* determines topics, teams, rulesets, runner groups, and environments
* prints the plan for review before creation

### 2. Create and Configure Repository

The second job creates the repository and applies the enterprise baseline configuration.

This phase:

* creates the repository from the selected template
* configures baseline repository settings
* assigns admin, write, and read teams
* enrolls the repository into organization rulesets
* adds the repository to runner groups
* creates repository environments
* prints a final audit summary

---

## Required Permissions

The workflow itself uses:

```yaml
permissions:
  contents: read
```

However, several steps require GitHub tokens stored as repository or organization secrets.

### Required Secrets

The following secrets must be available to the workflow:

* `ORG_ADMIN_TOKEN`
* `RULESET_ADMIN_TOKEN`
* `RUNNER_GROUP_ADMIN_TOKEN`

These tokens are used to perform administrative actions such as:

* creating repositories
* configuring repository settings
* assigning teams
* adding repositories to organization rulesets
* assigning runner group access
* creating repository environments

---

## Organization and Host Settings

This workflow uses the following environment values:

```yaml
env:
  GITHUB_HOST: github.com
  GITHUB_ORG: SecurityUniversalOrg
```

This means the repository will be created in:

* **GitHub host:** `github.com`
* **Organization:** `SecurityUniversalOrg`

---

## Supported Inputs

The workflow accepts the following manual inputs.

### `repo_name`

The name of the new repository.

* **Required:** Yes
* **Type:** `string`

Example:

```text
my-new-app
```

---

### `description`

The repository description.

* **Required:** No
* **Default:** `""`
* **Type:** `string`

Example:

```text
Enterprise application for managing internal requests
```

---

### `type`

The repository type. This determines which enterprise plan is built and what template, teams, rulesets, runner groups, and environments are applied.

* **Required:** Yes
* **Default:** `app`
* **Type:** `choice`

Supported values:

* `app`
* `library`
* `terraform`
* `image`
* `docker`
* `helm`
* `configuration`
* `cicd`

---

### `visibility`

The repository visibility.

* **Required:** Yes
* **Default:** `private`
* **Type:** `choice`

Supported values:

* `private`
* `internal`

---

## How to Run the Workflow

1. Open the repository that contains this workflow.
2. Go to the **Actions** tab.
3. Select **Create enterprise repository**.
4. Click **Run workflow**.
5. Enter the required values:

   * `repo_name`
   * `description` if needed
   * `type`
   * `visibility`
6. Start the workflow.
7. Review the output of the first job to confirm the generated repository creation plan.
8. If environment protections are configured for `repo-create-prod`, complete the required approval steps.
9. Allow the second job to create and configure the repository.

---

## Example Request

Example manual workflow input:

```text
repo_name: tf-network-core
description: Terraform for core network resources
type: terraform
visibility: private
```

---

## Jobs

## Job 1: `request`

**Name:** `Validate and build request`

**Runner:** `federal`

This job validates the request and builds the enterprise repository plan.

### Steps

#### Checkout

Uses the enterprise checkout action:

```yaml
uses: SecurityUniversalOrg/ghe-actions/actions/checkout@v1
```

#### Validate request

Validates:

* repository name
* repository type
* visibility

Action used:

```yaml
uses: SecurityUniversalOrg/ghe-actions/actions/repo-request-validate@v1
```

Inputs:

* `repo_name`
* `repo_type`
* `visibility`

Expected outputs include:

* validated repository name
* normalized repository type

#### Build enterprise plan

Builds the full configuration plan for the repository.

Action used:

```yaml
uses: SecurityUniversalOrg/ghe-actions/actions/repo-request-build-enterprise-plan@v1
```

Inputs:

* validated repository name
* normalized repository type
* visibility
* description

This step determines items such as:

* final description
* visibility
* template repository
* default branch
* auto initialization behavior
* repository topics
* admin, write, and read teams
* organization ruleset memberships
* runner group memberships
* repository environments
* security feature flags

#### Review - Repository Creation Plan

Prints the calculated plan for human review before any changes are made.

Action used:

```yaml
uses: SecurityUniversalOrg/ghe-actions/actions/repo-request-print-enterprise-plan@v1
```

This is the primary step to review before approval and apply.

---

## Job 2: `approve-and-apply`

**Name:** `Create and configure repository`

**Runner:** `federal`

**Depends on:** `request`

**Environment:** `repo-create-prod`

**Timeout:** `45` minutes

This job creates the repository and applies all required configuration.

### Why the Environment Matters

This job runs under the `repo-create-prod` environment. If environment protection rules are enabled, this may require:

* manual approval
* restricted reviewers
* deployment controls
* audit trail of approval

This is an important control point for enterprise governance and change management.

### Steps

#### Checkout

Uses the enterprise checkout action:

```yaml
uses: SecurityUniversalOrg/ghe-actions/actions/checkout@v1
```

---

#### Create repository from template

Creates the repository using the template selected in the enterprise plan.

Action used:

```yaml
uses: SecurityUniversalOrg/ghe-actions/actions/gh-create-repo-from-template@v1
```

Inputs include:

* GitHub host
* organization
* repository name
* description
* visibility
* template repository
* default branch
* auto initialization setting
* `ORG_ADMIN_TOKEN`

Output includes the created repository URL.

---

#### Configure baseline repository settings

Applies core baseline settings to the new repository.

Action used:

```yaml
uses: SecurityUniversalOrg/ghe-actions/actions/gh-configure-new-repo@v1
```

Inputs include:

* repository topics
* default branch
* `ORG_ADMIN_TOKEN`

Typical baseline settings may include repository metadata and standard repository configuration required by enterprise policy.

---

#### Assign repository teams

Assigns access to the repository for the enterprise team model.

Action used:

```yaml
uses: SecurityUniversalOrg/ghe-actions/actions/gh-assign-repo-teams@v1
```

Inputs include:

* admin teams
* write teams
* read teams
* `ORG_ADMIN_TOKEN`

This step ensures the correct role-based access model is applied.

---

#### Add repo to org rulesets

Adds the repository to one or more organization rulesets by name.

Action used:

```yaml
uses: SecurityUniversalOrg/ghe-actions/actions/gh-add-repo-to-rulesets-by-name@v1
```

Inputs include:

* ruleset names
* `RULESET_ADMIN_TOKEN`

This step is critical for applying centralized governance controls such as:

* branch protections
* required pull request settings
* required status checks
* naming restrictions
* push restrictions

---

#### Add repo to runner groups

Grants the repository access to the approved GitHub Actions runner groups.

Action used:

```yaml
uses: SecurityUniversalOrg/ghe-actions/actions/gh-add-repo-to-runner-groups@v1
```

Inputs include:

* runner group names
* `RUNNER_GROUP_ADMIN_TOKEN`

This step ensures the repository can only use approved runners aligned with enterprise and compliance requirements.

---

#### Create repository environments

Creates repository environments defined in the enterprise plan.

Action used:

```yaml
uses: SecurityUniversalOrg/ghe-actions/actions/gh-create-repo-environments@v1
```

Inputs include:

* environment definitions JSON
* `RULESET_ADMIN_TOKEN`

Typical examples may include environments such as:

* `dev`
* `test`
* `stage`
* `prod`

Actual environments depend on the plan generated for the selected repository type.

---

#### Print final audit summary

Prints the final repository creation summary after all steps complete.

Action used:

```yaml
uses: SecurityUniversalOrg/ghe-actions/actions/repo-request-print-final-summary@v1
```

This summary typically includes:

* repository name
* repository type
* repository URL
* visibility
* template used
* default branch
* topics
* team assignments
* rulesets
* runner groups
* environments

This output should be retained as part of the operational audit trail.

---

## Workflow Outputs Between Jobs

The `request` job passes the following outputs to the `approve-and-apply` job:

* `repo_name`
* `repo_type`
* `description`
* `visibility`
* `template_repo`
* `default_branch`
* `auto_init`
* `topics_json`
* `admin_teams_json`
* `write_teams_json`
* `read_teams_json`
* `ruleset_names_json`
* `enable_secret_scanning`
* `enable_secret_scanning_push_protection`
* `enable_dependabot_alerts`
* `enable_dependabot_security_updates`
* `enable_private_vulnerability_reporting`
* `runner_group_names_json`
* `environments_json`

These outputs represent the calculated enterprise plan and ensure that the apply phase uses the reviewed values rather than recomputing them.

---

## Repository Type Behavior

The selected `type` drives the enterprise provisioning model.

### `app`

Use for application repositories that contain deployable business applications or services.

### `library`

Use for shared libraries, SDKs, or reusable code packages.

### `terraform`

Use for infrastructure-as-code repositories managing Terraform modules or deployments.

### `image`

Use for repositories focused on VM image creation or image build logic.

### `docker`

Use for repositories focused on container image definitions and build pipelines.

### `helm`

Use for repositories containing Helm charts and Kubernetes deployment packages.

### `configuration`

Use for repositories that primarily manage configuration, policy, or operational settings.

### `cicd`

Use for repositories that contain reusable CI/CD workflows, pipeline logic, or automation assets.

The exact template, access model, and control set depend on how the enterprise plan action is implemented for each type.

---

## Review and Approval Model

This workflow is intentionally split into a planning phase and an apply phase.

### Why This Matters

This design supports enterprise control objectives by separating:

* request validation
* configuration planning
* protected application of changes

Because the second job uses the `repo-create-prod` environment, organizations can enforce approval before repository creation occurs.

This is especially useful for:

* regulated environments
* change-controlled organizations
* enterprise platform governance
* auditability requirements

---

## Expected End State

If the workflow completes successfully, the new repository should exist in `SecurityUniversalOrg` with:

* the approved name
* the selected visibility
* the correct template content
* baseline configuration applied
* required team access assigned
* organization rulesets attached
* runner group access configured
* repository environments created
* final summary logged in the workflow output

---

## Common Failure Points

## Validation Failure

The workflow may fail during the validation step if:

* the repository name does not meet naming requirements
* the repository type is invalid
* the visibility selection is invalid
* the repository already exists
* enterprise validation rules reject the request

Review the logs from `Validate request`.

---

## Planning Failure

The workflow may fail while building the enterprise plan if:

* the mapping for the selected repository type is missing
* the template repository is not defined
* required team or ruleset mappings are missing
* plan generation logic rejects the inputs

Review the logs from `Build enterprise plan`.

---

## Approval Block

The workflow may pause before the apply phase if the `repo-create-prod` environment requires approval.

Make sure the required approver completes the approval action in GitHub.

---

## Repository Creation Failure

The repository creation step may fail if:

* `ORG_ADMIN_TOKEN` is missing
* the token lacks sufficient permissions
* the template repository is not accessible
* the repository name is already in use
* the default branch or template settings are invalid

Review the logs from `Create repository from template`.

---

## Ruleset or Runner Group Failure

The workflow may partially succeed but fail later if:

* `RULESET_ADMIN_TOKEN` is missing or underprivileged
* `RUNNER_GROUP_ADMIN_TOKEN` is missing or underprivileged
* referenced rulesets do not exist
* referenced runner groups do not exist
* repository access cannot be updated

Review the logs from:

* `Add repo to org rulesets`
* `Add repo to runner groups`

---

## Environment Creation Failure

The workflow may fail during environment creation if:

* the environment JSON is malformed
* the token lacks permission
* repository environments already exist in a conflicting form

Review the logs from `Create repository environments`.

---

## Operational Guidance

## Before Running

Before starting the workflow, confirm:

* the repository name follows enterprise naming standards
* the repository type is correct
* the desired visibility is approved
* the correct template category is selected through `type`
* required organizational approvals are already understood
* required tokens and secrets are present

---

## During Review

When reviewing the generated plan, verify:

* repository name is correct
* repository type is correct
* description is accurate
* visibility is appropriate
* template repository is correct
* default branch is correct
* topics are appropriate
* admin, write, and read teams are correct
* rulesets are correct
* runner groups are correct
* environments are correct

Do not approve the apply phase until the plan looks correct.

---

## After Completion

After the workflow finishes, verify:

* the repository exists in the correct organization
* the repository URL is valid
* the correct teams have access
* rulesets are attached as expected
* runner groups are available to the repository
* environments were created correctly
* template content appears as expected

---

## Example User Scenarios

## Create a new application repository

Use:

```text
type: app
visibility: private
```

Use this when creating a standard internal application repository that should inherit the enterprise application template and baseline controls.

---

## Create a new Terraform repository

Use:

```text
type: terraform
visibility: private
```

Use this when creating a Terraform repository that needs infrastructure-specific controls, runner groups, and rulesets.

---

## Create an internal shared library repository

Use:

```text
type: library
visibility: internal
```

Use this when creating a library intended for broader enterprise internal reuse.

---

## Example Workflow Summary

A typical successful execution looks like this:

1. User manually runs the workflow.
2. The request is validated.
3. An enterprise plan is generated.
4. The plan is printed for review.
5. Required approvers approve the protected environment.
6. The repository is created from the correct template.
7. Baseline settings are applied.
8. Teams are assigned.
9. Rulesets are attached.
10. Runner groups are assigned.
11. Repository environments are created.
12. A final audit summary is printed.

---

## Notes for Repository Requesters

* This workflow is intended for standardized enterprise repository creation.
* The selected repository `type` controls much of the downstream configuration.
* You should expect approval gating before the repository is created.
* Final repository controls are applied automatically by the workflow.
* Manual post-creation changes may still require separate governance approval depending on enterprise policy.

---

## Notes for Platform Administrators

This workflow assumes the enterprise composite actions already implement the business rules for:

* repository validation
* enterprise plan generation
* team assignment
* ruleset assignment
* runner group assignment
* environment creation

If enterprise onboarding behavior changes, update those reusable actions rather than changing requester behavior.

---

## Related Actions Used by This Workflow

```text
SecurityUniversalOrg/ghe-actions/actions/checkout@v1
SecurityUniversalOrg/ghe-actions/actions/repo-request-validate@v1
SecurityUniversalOrg/ghe-actions/actions/repo-request-build-enterprise-plan@v1
SecurityUniversalOrg/ghe-actions/actions/repo-request-print-enterprise-plan@v1
SecurityUniversalOrg/ghe-actions/actions/gh-create-repo-from-template@v1
SecurityUniversalOrg/ghe-actions/actions/gh-configure-new-repo@v1
SecurityUniversalOrg/ghe-actions/actions/gh-assign-repo-teams@v1
SecurityUniversalOrg/ghe-actions/actions/gh-add-repo-to-rulesets-by-name@v1
SecurityUniversalOrg/ghe-actions/actions/gh-add-repo-to-runner-groups@v1
SecurityUniversalOrg/ghe-actions/actions/gh-create-repo-environments@v1
SecurityUniversalOrg/ghe-actions/actions/repo-request-print-final-summary@v1
```

---

## Suggested README Placement

This document can be stored as:

```text
README.md
```

or, if you want it specifically as operational documentation:

```text
docs/create-enterprise-repository-user-guide.md
```

---

## Raw Markdown Copy

You can copy everything in this response directly into a GitHub Markdown file as-is.
