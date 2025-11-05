# GitHub Secrets Configuration

This document describes the GitHub repository secrets required for automatic deployment of the VPS Monitoring Stack.

## Required Secrets

Configure these secrets in your GitHub repository:
**Settings → Secrets and variables → Actions → Repository secrets**

### Portainer Deployment Webhook

| Secret Name | Description | Example Value |
|------------|-------------|---------------|
| `PORTAINER_MONITORING_WEBHOOK` | Portainer webhook for monitoring stack deployment | `http://57.129.41.248:9000/api/stacks/webhooks/7b485017-1319-4a75-b851-a09b12f6b047` |

## How to Configure

### 1. Get Webhook URL from Portainer

1. Navigate to **Portainer** → **Stacks**
2. Select the `monitoring` stack (or create it if it doesn't exist)
3. Click **Webhooks** tab
4. Click **Add webhook** (if no webhook exists)
5. Copy the webhook URL

**Note:** The webhook URL format is:
```
http://<portainer-host>:<port>/api/stacks/webhooks/<webhook-id>
```

**Example:**
```
http://57.129.41.248:9000/api/stacks/webhooks/7b485017-1319-4a75-b851-a09b12f6b047
```

### 2. Add Secret to GitHub

1. Go to your GitHub repository
2. Click **Settings** → **Secrets and variables** → **Actions**
3. Click **New repository secret**
4. Add the secret:
   - **Name**: `PORTAINER_MONITORING_WEBHOOK`
   - **Secret**: Your webhook URL from Portainer
   
   **Example value:**
   ```
   http://57.129.41.248:9000/api/stacks/webhooks/7b485017-1319-4a75-b851-a09b12f6b047
   ```
   
5. Click **Add secret**

**Important:** 
- Copy the entire webhook URL exactly as shown in Portainer
- The format is: `http://<host>:<port>/api/stacks/webhooks/<webhook-id>`
- Do NOT add any trailing slashes or extra characters
- The webhook ID is unique for each stack

### 3. Verify Configuration

After adding the secret, trigger a deployment:

```bash
# Make a change to docker-compose.yml or config files
git checkout main
git commit --allow-empty -m "test: Trigger monitoring deployment"
git push origin main

# Check GitHub Actions logs
# You should see: ✅ Portainer webhook triggered successfully
```

## Workflow Architecture

The CI/CD pipeline uses two workflows:

```
.github/workflows/
├── validate.yml    # Validation workflow (runs on PRs)
└── deploy.yml      # Deployment workflow (runs on push to main)
```

### Validation Workflow (`validate.yml`)

**Trigger:** Pull requests to `main` branch

**Jobs:**
- **validate**: Validates all configuration files
  - Checks docker-compose.yml syntax
  - Verifies required files exist
  - Validates Prometheus, Loki, Grafana configurations
  - Checks dashboard templates

**Purpose:** Catch configuration errors before merging to main

### Deployment Workflow (`deploy.yml`)

**Trigger:** Push to `main` branch (only when files in stack change)

**Jobs:**
- **validate**: Same validation as PR workflow
- **deploy**: Triggers Portainer webhook to update stack

**Purpose:** Automatically deploy validated changes to Portainer

## Workflow Behavior

### Pull Request (Validation Only)

- **Trigger**: Pull request to `main` branch
- **Validates**: All configuration files
- **No Deployment**: Only validates, doesn't deploy
- **Non-blocking**: Warnings don't fail the workflow

### Push to Main (Deployment)

- **Trigger**: Push to `main` branch
- **Validates**: All configuration files
- **Deploys**: Triggers Portainer webhook
- **Non-blocking**: Webhook failure doesn't fail workflow (logs warning)

### Paths Watched

Workflows only run when these files change:
- `docker-compose.yml`
- `config/**` (any file in config directory)
- `.github/workflows/**` (workflow files)

This prevents unnecessary runs when only documentation changes.

## Portainer Stack Setup

### Initial Stack Creation

Before using the webhook, you need to create the stack in Portainer:

1. **Navigate to Portainer** → **Stacks**
2. **Click "Add stack"**
3. **Choose "Docker Swarm"**
4. **Select "Repository" method**
5. **Configure:**
   - **Name**: `monitoring`
   - **Repository URL**: Your GitHub repository URL
   - **Repository reference**: `main` (or your branch)
   - **Compose path**: `docker-compose.yml`
   - **Auto-update**: Enable (optional, webhook is better)

6. **Add environment variables** (if using `.env` file):
   - `GRAFANA_ADMIN_PASSWORD`
   - `MONITORING_HOST`
   - etc.

7. **Deploy the stack**

### Webhook Configuration

After stack is created:

1. **Go to stack** → **Webhooks** tab
2. **Click "Add webhook"**
3. **Copy the webhook URL**
4. **Add to GitHub Secrets** as `PORTAINER_MONITORING_WEBHOOK`

### Stack Update Process

When you push to `main`:

1. GitHub Actions validates the stack
2. If validation passes, triggers Portainer webhook
3. Portainer fetches latest `docker-compose.yml` from repository
4. Portainer updates the stack with new configuration
5. Services are redeployed if configuration changed

## Security Notes

- Webhooks are stored as encrypted secrets in GitHub
- Never commit webhook URLs to repository code
- Webhooks are only accessible during GitHub Actions workflow execution
- Use HTTPS webhooks when possible (consider Traefik reverse proxy)

## Troubleshooting

### Webhook not triggering?

**Check if secret exists:**
1. Go to repository **Settings** → **Secrets and variables** → **Actions**
2. Verify the secret name matches exactly: `PORTAINER_MONITORING_WEBHOOK` (case-sensitive)

**Check workflow logs:**
1. Go to **Actions** tab in repository
2. Click on the workflow run
3. Expand the webhook step to see error details

**Test webhook manually:**
```bash
curl -X POST http://57.129.41.248:9000/api/stacks/webhooks/7b485017-1319-4a75-b851-a09b12f6b047
```

Or with your webhook URL:
```bash
curl -X POST http://your-portainer-host:9000/api/stacks/webhooks/your-webhook-id
```

### Build succeeds but stack not updating?

**Verify webhook URL:**
- Test webhook manually (see above)
- Check Portainer logs
- Verify stack exists in Portainer

**Check Portainer stack configuration:**
- Stack should be set to "Repository" method
- Repository URL should point to your GitHub repository
- Repository reference should be `main` (or your branch)
- Compose path should be `docker-compose.yml`

### Validation errors?

**Common issues:**
- Missing required files in `config/` directory
- YAML syntax errors in configuration files
- Missing required services in docker-compose.yml

**Fix:**
- Check the validation error in GitHub Actions logs
- Fix the configuration file
- Push changes again

### Stack update fails in Portainer?

**Check Portainer logs:**
1. Go to Portainer → Stacks
2. Click on `monitoring` stack
3. Check **Logs** tab for errors

**Common issues:**
- Network `traefik-public` doesn't exist (create it first)
- Volume conflicts (check if volumes exist)
- Resource constraints (check Docker Swarm resources)

## Example: Complete Setup

```bash
# 1. Create Portainer stack
# - Name: monitoring
# - Repository: https://github.com/your-org/vps-monitoring
# - Branch: main
# - Compose path: docker-compose.yml

# 2. Get webhook URL from Portainer
WEBHOOK="http://57.129.41.248:9000/api/stacks/webhooks/7b485017-1319-4a75-b851-a09b12f6b047"

# 3. Add to GitHub Secrets (via web UI)
# PORTAINER_MONITORING_WEBHOOK = $WEBHOOK

# 4. Deploy (via push to main branch)
git checkout main
git commit --allow-empty -m "test: Trigger monitoring deployment"
git push origin main

# 5. Check GitHub Actions - should see webhook triggered
# 6. Check Portainer - stack should update automatically
```

## Related Documentation

- [GitHub Actions Secrets](https://docs.github.com/en/actions/security-guides/encrypted-secrets)
- [Portainer Webhooks](https://docs.portainer.io/user/docker/stacks/webhooks)
- [Repository README](README.md)
- [Deployment Guide](docs/DEPLOYMENT.md)


