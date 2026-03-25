#!/usr/bin/env node
// scripts/mcp-sse-proxy.js
// Proxies stdio to an MCP SSE server.

const { EventSource } = require('eventsource');
const axios = require('axios');

const sseUrl = process.argv[2] || 'http://localhost:10888/sse';
const token = process.env.MCP_GATEWAY_AUTH_TOKEN;

if (!token) {
  console.error('Error: MCP_GATEWAY_AUTH_TOKEN is not set in environment.');
  // We continue as it might be an open server, but we log the error as requested.
}

let eventSource = null;

function cleanup() {
  if (eventSource) {
    eventSource.close();
    eventSource = null;
  }
}

process.on('SIGINT', () => { cleanup(); process.exit(0); });
process.on('SIGTERM', () => { cleanup(); process.exit(0); });

eventSource = new EventSource(sseUrl, {
  headers: token ? { Authorization: `Bearer ${token}` } : {}
});

let postUrl = null;
const messageQueue = [];

async function sendPost(payload) {
  if (!postUrl) {
    messageQueue.push(payload);
    return;
  }
  try {
    await axios.post(postUrl, payload, {
      headers: token ? { Authorization: `Bearer ${token}` } : {}
    });
  } catch (e) {
    console.error('Error posting message to SSE:', e.message);
  }
}

async function flushQueue() {
  while (messageQueue.length > 0 && postUrl) {
    const msg = messageQueue.shift();
    await sendPost(msg);
  }
}

// Handle endpoint event to discover the POST target URL
eventSource.addEventListener('endpoint', async (event) => {
  try {
    const data = JSON.parse(event.data);
    postUrl = data.endpoint || event.data;
  } catch (e) {
    postUrl = event.data;
  }

  // Resolve relative URL if necessary
  if (postUrl && !postUrl.startsWith('http')) {
    const base = new URL(sseUrl);
    postUrl = new URL(postUrl, base).toString();
  }

  // Flush queued messages
  await flushQueue();
});

eventSource.onmessage = (event) => {
  process.stdout.write(event.data + '\n');
};

eventSource.onerror = (event) => {
  console.error('EventSource connection failed:', event.message || event);
  cleanup();
  process.exit(1);
};

let stdinBuffer = '';
process.stdin.on('data', async (data) => {
  stdinBuffer += data.toString();
  const lines = stdinBuffer.split('\n');
  stdinBuffer = lines.pop(); // keep partial line or empty string if ends with \n

  for (const line of lines) {
    if (!line.trim()) continue;
    try {
      const payload = JSON.parse(line);
      await sendPost(payload);
    } catch (e) {
      // Ignore non-JSON lines
    }
  }
});

process.stdin.on('end', async () => {
  if (stdinBuffer.trim()) {
    try {
      const payload = JSON.parse(stdinBuffer);
      await sendPost(payload);
    } catch (e) {}
  }
});
