# GitHub API Proxy Server

A simple Express.js server that proxies GitHub API requests to handle the 404 error on `localhost:8082`.

## Problem

Your application was trying to access:
```
http://localhost:8082/api/github/user/repos?per_page=50
```

But this endpoint doesn't exist on the existing server running on port 8082.

## Solution

This proxy server provides the missing GitHub API endpoints and forwards requests to the real GitHub API.

## Setup

### 1. Install Dependencies

```bash
cd github-proxy-server
npm install
```

### 2. Configure GitHub Token (Optional but Recommended)

Create a `.env` file:
```bash
cp .env.example .env
```

Edit `.env` and add your GitHub Personal Access Token:
```env
GITHUB_TOKEN=ghp_your_token_here
PORT=8083
```

To create a GitHub token:
1. Go to https://github.com/settings/tokens
2. Click "Generate new token (classic)"
3. Select scopes: `repo` or `public_repo`
4. Copy the token to your `.env` file

### 3. Start the Server

```bash
npm start
```

The server will run on port 8083 by default (to avoid conflict with the existing service on 8082).

## Usage

### Available Endpoints

- `GET /health` - Health check
- `GET /api/github/user` - Get authenticated user info  
- `GET /api/github/user/repos` - Get user repositories
- `GET /api/github/*` - Proxy any GitHub API endpoint

### Example Requests

```bash
# Health check
curl http://localhost:8083/health

# Get repositories (with authentication)
curl -H "Authorization: Bearer YOUR_GITHUB_TOKEN" \
     http://localhost:8083/api/github/user/repos?per_page=10

# Get repositories (using environment token)
curl http://localhost:8083/api/github/user/repos?per_page=10
```

## Fixing the Original Issue

If your application is hardcoded to use port 8082, you have a few options:

### Option 1: Change Your Application
Update your application to use port 8083:
```javascript
const apiUrl = 'http://localhost:8083/api/github/user/repos';
```

### Option 2: Use a Different Port for This Proxy
Stop the existing service on 8082 and run this proxy there:
```bash
PORT=8082 npm start
```

### Option 3: Add GitHub Endpoint to Existing Server
If you have access to the existing FastAPI server on 8082, add this endpoint:

```python
@app.get("/api/github/user/repos")
async def github_user_repos(per_page: int = 30):
    import httpx
    
    async with httpx.AsyncClient() as client:
        response = await client.get(
            "https://api.github.com/user/repos",
            params={"per_page": per_page},
            headers={
                "Authorization": f"token {GITHUB_TOKEN}",
                "Accept": "application/vnd.github.v3+json"
            }
        )
        return response.json()
```

## Features

- ✅ **CORS enabled** - Works with browser applications
- ✅ **Authentication handling** - Supports GitHub tokens
- ✅ **Error handling** - Proper HTTP status codes and error messages
- ✅ **Rate limiting aware** - Handles GitHub API rate limits
- ✅ **Flexible token auth** - Via header or environment variable
- ✅ **Request logging** - See what's being proxied
- ✅ **Health check** - Monitor server status

## Security Notes

- Keep your GitHub token private
- Don't commit `.env` file to version control
- Use environment variables in production
- Consider IP restrictions for production use

## Development

```bash
# Run with auto-restart on file changes
npm run dev
```