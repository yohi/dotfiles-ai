#!/usr/bin/env node
// scripts/mcp-sse-proxy.js
// Proxies stdio to an MCP SSE server.

const { EventSource } = require('eventsource');
const axios = require('axios');

const sseUrl = process.argv[2] || 'http://localhost:10888/sse';
const eventSource = new EventSource(sseUrl);

let postUrl = null;
const messageQueue = [];

// Handle endpoint event to discover the POST target URL
eventSource.addEventListener('endpoint', (event) => {
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
  while (messageQueue.length > 0 && postUrl) {
    const msg = messageQueue.shift();
    sendPost(msg);
  }
});

eventSource.onmessage = (event) => {
  process.stdout.write(event.data + '\n');
};

eventSource.onerror = (event) => {
  console.error('EventSource connection failed:', event.message || event);
  process.exit(1);
};

async function sendPost(payload) {
  if (!postUrl) {
    messageQueue.push(payload);
    return;
  }
  try {
    await axios.post(postUrl, payload);
  } catch (e) {
    console.error('Error posting message to SSE:', e.message);
  }
}

process.stdin.on('data', (data) => {
  const messages = data.toString().split('\n').filter(l => l.trim());
  for (const msg of messages) {
    try {
      const payload = JSON.parse(msg);
      sendPost(payload);
    } catch (e) {
      // Ignore non-JSON lines
    }
  }
});
