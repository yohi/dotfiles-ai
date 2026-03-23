#!/usr/bin/env node

/**
 * MCP SSE Session Proxy
 *
 * Listens on port 10889 and forwards requests to http://localhost:10888/sse.
 * Automatically captures the dynamic sessionid from the GET /sse stream
 * and appends it to subsequent POST requests.
 */

const http = require('http');
const { URL } = require('url');

const PROXY_PORT = 10889;
const TARGET_URL = 'http://localhost:10888/sse';
const AUTH_TOKEN = process.env.MCP_GATEWAY_AUTH_TOKEN;

let storedSessionId = null;

const server = http.createServer((req, res) => {
  const target = new URL(TARGET_URL);
  
  // Prepare request options for the target Gateway
  const options = {
    hostname: target.hostname,
    port: target.port,
    path: target.pathname + target.search,
    method: req.method,
    headers: {
      ...req.headers,
    }
  };

  // Use MCP_GATEWAY_AUTH_TOKEN for Authorization if available
  if (AUTH_TOKEN) {
    options.headers['Authorization'] = `Bearer ${AUTH_TOKEN}`;
  }

  // Remove host header to avoid host mismatch with target server
  delete options.headers['host'];

  // Handle SSE connection (GET /sse)
  if (req.method === 'GET' && req.url.startsWith('/sse')) {
    console.log(`[Proxy] Intercepting GET ${req.url} -> ${TARGET_URL}`);
    
    const proxyReq = http.request(options, (proxyRes) => {
      // Forward response headers and status
      res.writeHead(proxyRes.statusCode, proxyRes.headers);

      proxyRes.on('data', (chunk) => {
        const data = chunk.toString();
        // Look for sessionid in the SSE data stream
        // Usually sent as part of a URI: data: /sse?sessionid=...
        const sessionMatch = data.match(/sessionid=([a-zA-Z0-9\-_]+)/);
        if (sessionMatch) {
          storedSessionId = sessionMatch[1];
          console.log(`[Proxy] Captured sessionid: ${storedSessionId}`);
        }
        res.write(chunk);
      });

      proxyRes.on('end', () => {
        res.end();
      });
    });

    proxyReq.on('error', (err) => {
      console.error(`[Proxy] GET target error: ${err.message}`);
      res.writeHead(502);
      res.end('Bad Gateway: Target server unreachable');
    });

    proxyReq.end();

  } 
  // Handle JSON-RPC messages (POST)
  else if (req.method === 'POST') {
    // Automatically append stored sessionid as a query parameter
    if (storedSessionId) {
      const sep = target.search ? '&' : '?';
      options.path = `${target.pathname}${target.search}${sep}sessionid=${storedSessionId}`;
    }

    console.log(`[Proxy] Forwarding POST to ${options.path}`);

    const proxyReq = http.request(options, (proxyRes) => {
      res.writeHead(proxyRes.statusCode, proxyRes.headers);
      proxyRes.pipe(res, { end: true });
    });

    req.pipe(proxyReq, { end: true });

    proxyReq.on('error', (err) => {
      console.error(`[Proxy] POST target error: ${err.message}`);
      res.writeHead(502);
      res.end('Bad Gateway: Target server unreachable');
    });
  } 
  // Fallback for other methods or paths
  else {
    const proxyReq = http.request(options, (proxyRes) => {
      res.writeHead(proxyRes.statusCode, proxyRes.headers);
      proxyRes.pipe(res, { end: true });
    });

    req.pipe(proxyReq, { end: true });

    proxyReq.on('error', (err) => {
      console.error(`[Proxy] Proxy error: ${err.message}`);
      res.writeHead(502);
      res.end('Bad Gateway');
    });
  }
});

server.listen(PROXY_PORT, () => {
  console.log(`[Proxy] MCP SSE Proxy listening on port ${PROXY_PORT}`);
  console.log(`[Proxy] Target Gateway: ${TARGET_URL}`);
  if (AUTH_TOKEN) {
    console.log('[Proxy] Using Authorization token from MCP_GATEWAY_AUTH_TOKEN');
  } else {
    console.warn('[Proxy] WARNING: MCP_GATEWAY_AUTH_TOKEN not set');
  }
});
