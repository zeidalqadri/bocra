# BOCRA UI - Cloudflare Pages Deployment Guide

This guide explains how to set up CI/CD deployment for the BOCRA UI application using GitHub Actions and Cloudflare Pages.

## Overview

The deployment pipeline automatically:
- Builds the React application on every push to `main`
- Runs TypeScript checks and linting
- Deploys to Cloudflare Pages
- Creates preview deployments for pull requests
- Comments deployment URLs on PRs

## Setup Instructions

### 1. Cloudflare Account Setup

1. **Create a Cloudflare account** at [cloudflare.com](https://cloudflare.com) if you don't have one
2. **Get your Account ID**:
   - Go to the Cloudflare dashboard
   - Copy your Account ID from the right sidebar

### 2. Generate Cloudflare API Token

1. Go to [Cloudflare API Tokens](https://dash.cloudflare.com/profile/api-tokens)
2. Click "Create Token"
3. Use the "Custom token" template with these permissions:
   - **Account** - `Cloudflare Pages:Edit`
   - **Zone Resources** - `Include All zones` (or specific zones if preferred)
   - **Account Resources** - `Include All accounts` (or your specific account)

### 3. Configure GitHub Secrets

In your GitHub repository, go to **Settings > Secrets and variables > Actions** and add:

| Secret Name | Description | How to Get |
|-------------|-------------|------------|
| `CLOUDFLARE_API_TOKEN` | API token for Cloudflare | From step 2 above |
| `CLOUDFLARE_ACCOUNT_ID` | Your Cloudflare account ID | From Cloudflare dashboard |

### 4. Create Cloudflare Pages Project (Optional)

You can either:

**Option A: Let GitHub Actions create the project automatically**
- The workflow will create the project on first deployment

**Option B: Create manually via Cloudflare Dashboard**
- Go to Cloudflare Dashboard > Pages
- Click "Create a project"
- Connect to your GitHub repository
- Set project name: `bocra-ui`
- Build settings:
  - Build command: `cd bocra-ui && npm run build`
  - Build output directory: `bocra-ui/dist`
  - Root directory: `/`

## Deployment Workflow

### Automatic Deployments

- **Production**: Pushes to `main` branch deploy to production
- **Preview**: Pull requests create preview deployments
- **Comments**: Preview URLs are automatically commented on PRs

### Manual Deployment (Local)

Install Wrangler CLI:
```bash
npm install -g wrangler
```

Deploy manually:
```bash
# Production deployment
cd bocra-ui
npm run deploy

# Staging deployment
npm run deploy:staging

# Test deployment locally
npm run pages:dev
```

## Build Configuration

### Environment Variables

If your application needs environment variables, add them in:

1. **Cloudflare Dashboard**: Pages project > Settings > Environment variables
2. **GitHub Actions**: Repository secrets (for build-time variables)

### Build Settings

The build process:
1. Installs dependencies with `npm ci`
2. Runs TypeScript compilation check
3. Runs ESLint for code quality
4. Builds the application with Vite
5. Deploys the `dist` folder to Cloudflare Pages

## Troubleshooting

### Common Issues

**1. Build Failures**
- Check the Actions tab in GitHub for detailed error logs
- Ensure all dependencies are listed in `package.json`
- Verify TypeScript compilation passes locally

**2. Deployment Permission Errors**
- Verify `CLOUDFLARE_API_TOKEN` has correct permissions
- Check `CLOUDFLARE_ACCOUNT_ID` is correct
- Ensure token hasn't expired

**3. Project Not Found**
- The first deployment creates the project automatically
- If manually created, ensure project name matches `projectName` in workflow

### Workflow File Location

The GitHub Actions workflow is located at:
```
.github/workflows/deploy.yml
```

### Logs and Monitoring

- **GitHub Actions**: Check the Actions tab for build logs
- **Cloudflare**: Pages dashboard shows deployment history and logs
- **Preview URLs**: Automatically commented on pull requests

## Additional Features

### Custom Domains

1. Go to Cloudflare Pages > Your Project > Custom domains
2. Add your domain
3. Configure DNS records as instructed

### Analytics

Cloudflare Pages provides built-in analytics:
- Page views and unique visitors
- Geographic distribution
- Performance metrics

### Security Headers

Configure security headers in `wrangler.toml`:
```toml
[env.production.headers]
"X-Frame-Options" = "DENY"
"X-Content-Type-Options" = "nosniff"
"Referrer-Policy" = "strict-origin-when-cross-origin"
```

## Support

For issues with:
- **GitHub Actions**: Check repository Actions tab
- **Cloudflare Pages**: Check Cloudflare dashboard logs
- **Build Problems**: Run `npm run build` locally first

## URLs

After successful deployment:
- **Production**: `https://bocra-ui.pages.dev`
- **Custom Domain**: Configure in Cloudflare Pages settings