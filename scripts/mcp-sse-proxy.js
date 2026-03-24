#!/usr/bin/env node
// scripts/mcp-sse-proxy.js
// Proxies stdio to an MCP SSE server.

const { EventSource } = require('eventsource');
const axios = require('axios');

const sseUrl = process.argv[2] || 'http://localhost:10888/sse';
const eventSource = new EventSource(sseUrl);

eventSource.on('message', (event) => {
  const message = JSON.parse(event.data);
  process.stdout.write(JSON.stringify(message) + '\n');
});

process.stdin.on('data', async (data) => {
  const messages = data.toString().split('\n').filter(l => l.trim());
  for (const msg of messages) {
    try {
      const payload = JSON.parse(msg);
      await axios.post(sseUrl, payload);
    } catch (e) {
      console.error('Error posting message to SSE:', e.message);
    }
  }
});
