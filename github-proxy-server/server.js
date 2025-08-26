import express from 'express';
import cors from 'cors';
import axios from 'axios';
import dotenv from 'dotenv';

dotenv.config();

const app = express();
const PORT = process.env.PORT || 8083; // Use 8083 to avoid conflict with existing service

// Enable CORS for all origins (adjust for production)
app.use(cors());
app.use(express.json());

// GitHub API base URL
const GITHUB_API_BASE = 'https://api.github.com';

// Middleware to add GitHub authentication
const addGitHubAuth = (req, res, next) => {
  // Try to get token from various sources
  const token = req.headers.authorization?.replace('Bearer ', '') || 
                req.headers.authorization?.replace('token ', '') ||
                process.env.GITHUB_TOKEN;
  
  req.githubHeaders = {
    'Accept': 'application/vnd.github.v3+json',
    'User-Agent': 'BOCRA-GitHub-Proxy/1.0'
  };
  
  if (token) {
    req.githubHeaders['Authorization'] = `token ${token}`;
  }
  
  next();
};

// Health check endpoint
app.get('/health', (req, res) => {
  res.json({ status: 'healthy', service: 'GitHub API Proxy' });
});

// GitHub API proxy endpoints
app.get('/api/github/user/repos', addGitHubAuth, async (req, res) => {
  try {
    const { per_page = 30, sort = 'updated', type = 'all' } = req.query;
    
    console.log('Fetching user repositories...');
    
    const response = await axios.get(`${GITHUB_API_BASE}/user/repos`, {
      params: { per_page, sort, type },
      headers: req.githubHeaders,
      timeout: 10000
    });
    
    // Transform the response to include only necessary fields
    const repos = response.data.map(repo => ({
      id: repo.id,
      name: repo.name,
      full_name: repo.full_name,
      private: repo.private,
      description: repo.description,
      fork: repo.fork,
      created_at: repo.created_at,
      updated_at: repo.updated_at,
      pushed_at: repo.pushed_at,
      clone_url: repo.clone_url,
      ssh_url: repo.ssh_url,
      html_url: repo.html_url,
      homepage: repo.homepage,
      size: repo.size,
      stargazers_count: repo.stargazers_count,
      watchers_count: repo.watchers_count,
      language: repo.language,
      forks_count: repo.forks_count,
      topics: repo.topics,
      visibility: repo.visibility,
      default_branch: repo.default_branch
    }));
    
    res.json(repos);
    console.log(`Successfully fetched ${repos.length} repositories`);
    
  } catch (error) {
    console.error('GitHub API Error:', error.response?.data || error.message);
    
    if (error.response?.status === 401) {
      res.status(401).json({ 
        error: 'Unauthorized',
        message: 'GitHub authentication required. Please provide a valid token.',
        hint: 'Add Authorization: Bearer YOUR_TOKEN header or set GITHUB_TOKEN environment variable'
      });
    } else if (error.response?.status === 403) {
      res.status(403).json({ 
        error: 'Rate Limited',
        message: 'GitHub API rate limit exceeded. Try again later.',
        reset_time: error.response.headers['x-ratelimit-reset']
      });
    } else if (error.response?.status === 404) {
      res.status(404).json({ 
        error: 'Not Found',
        message: 'User repositories not found. Check your token permissions.'
      });
    } else {
      res.status(500).json({ 
        error: 'Internal Server Error',
        message: 'Failed to fetch GitHub repositories',
        details: error.message
      });
    }
  }
});

// Get authenticated user info
app.get('/api/github/user', addGitHubAuth, async (req, res) => {
  try {
    console.log('Fetching user info...');
    
    const response = await axios.get(`${GITHUB_API_BASE}/user`, {
      headers: req.githubHeaders,
      timeout: 10000
    });
    
    const user = {
      id: response.data.id,
      login: response.data.login,
      name: response.data.name,
      email: response.data.email,
      avatar_url: response.data.avatar_url,
      html_url: response.data.html_url,
      public_repos: response.data.public_repos,
      followers: response.data.followers,
      following: response.data.following,
      created_at: response.data.created_at,
      updated_at: response.data.updated_at
    };
    
    res.json(user);
    console.log(`Successfully fetched user info for: ${user.login}`);
    
  } catch (error) {
    console.error('GitHub API Error:', error.response?.data || error.message);
    res.status(error.response?.status || 500).json({ 
      error: 'Failed to fetch user information',
      message: error.message
    });
  }
});

// Generic GitHub API proxy (for other endpoints)
app.all('/api/github/*', addGitHubAuth, async (req, res) => {
  try {
    const githubPath = req.path.replace('/api/github', '');
    const url = `${GITHUB_API_BASE}${githubPath}`;
    
    console.log(`Proxying ${req.method} request to: ${url}`);
    
    const response = await axios({
      method: req.method.toLowerCase(),
      url,
      params: req.query,
      data: req.body,
      headers: req.githubHeaders,
      timeout: 15000
    });
    
    res.status(response.status).json(response.data);
    
  } catch (error) {
    console.error('GitHub Proxy Error:', error.response?.data || error.message);
    res.status(error.response?.status || 500).json({ 
      error: 'GitHub API request failed',
      message: error.message,
      path: req.path
    });
  }
});

// 404 handler
app.use('*', (req, res) => {
  res.status(404).json({ 
    error: 'Not Found',
    message: `Endpoint ${req.method} ${req.originalUrl} not found`,
    availableEndpoints: [
      'GET /health',
      'GET /api/github/user',
      'GET /api/github/user/repos',
      'GET /api/github/*'
    ]
  });
});

// Error handler
app.use((error, req, res, next) => {
  console.error('Server Error:', error);
  res.status(500).json({ 
    error: 'Internal Server Error',
    message: error.message
  });
});

app.listen(PORT, () => {
  console.log(`🚀 GitHub Proxy Server running on port ${PORT}`);
  console.log(`📊 Health check: http://localhost:${PORT}/health`);
  console.log(`🐙 GitHub API proxy: http://localhost:${PORT}/api/github/*`);
  
  if (!process.env.GITHUB_TOKEN) {
    console.log(`⚠️  Warning: No GITHUB_TOKEN found in environment variables`);
    console.log(`   Add GITHUB_TOKEN=your_token to .env file for authenticated requests`);
  } else {
    console.log(`✅ GitHub token found - authenticated requests enabled`);
  }
});