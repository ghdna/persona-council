/**
 * API client for the Persona Council backend.
 */

// Use the current host for API requests so it works from any hostname/IP
const API_BASE = `http://${window.location.hostname}:8001`;

export const api = {
  /**
   * Get available providers and models based on configured API keys.
   */
  async getProviders() {
    const response = await fetch(`${API_BASE}/api/providers`);
    if (!response.ok) {
      throw new Error('Failed to load providers');
    }
    return response.json();
  },

  /**
   * List all conversations.
   */
  async listConversations() {
    const response = await fetch(`${API_BASE}/api/conversations`);
    if (!response.ok) {
      throw new Error('Failed to list conversations');
    }
    return response.json();
  },

  /**
   * Create a new conversation.
   */
  async createConversation() {
    const response = await fetch(`${API_BASE}/api/conversations`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({}),
    });
    if (!response.ok) {
      throw new Error('Failed to create conversation');
    }
    return response.json();
  },

  /**
   * Get a specific conversation.
   */
  async getConversation(conversationId) {
    const response = await fetch(`${API_BASE}/api/conversations/${conversationId}`);
    if (!response.ok) {
      throw new Error('Failed to get conversation');
    }
    return response.json();
  },

  /**
   * Send a message in a conversation.
   * @param {string} conversationId
   * @param {string} content
   * @param {string|null} mode - "model" | "persona" | "hybrid" | null
   * @param {string|null} model - per-request model override
   */
  async sendMessage(conversationId, content, mode = null, model = null) {
    const response = await fetch(
      `${API_BASE}/api/conversations/${conversationId}/message`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content, mode, model }),
      }
    );
    if (!response.ok) {
      throw new Error('Failed to send message');
    }
    return response.json();
  },

  /**
   * Send a message and receive streaming updates.
   * @param {string} conversationId
   * @param {string} content
   * @param {string|null} mode
   * @param {string|null} model - per-request model override
   * @param {function} onEvent - Callback: (eventType, data) => void
   */
  async sendMessageStream(conversationId, content, mode, model, onEvent) {
    const response = await fetch(
      `${API_BASE}/api/conversations/${conversationId}/message/stream`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content, mode, model }),
      }
    );

    if (!response.ok) {
      throw new Error('Failed to send message');
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();

    // Network chunks are not aligned to SSE event boundaries: a single
    // `data: {...}` line can be split across two reads (most likely for large
    // events like stage2_complete). Buffer across reads and only parse complete
    // events, which the backend delimits with a blank line ("\n\n").
    let buffer = '';

    const dispatchEvent = (rawEvent) => {
      const data = rawEvent
        .split('\n')
        .filter((line) => line.startsWith('data: '))
        .map((line) => line.slice(6))
        .join('\n');
      if (!data) return;
      try {
        const event = JSON.parse(data);
        onEvent(event.type, event);
      } catch (e) {
        console.error('Failed to parse SSE event:', e, data);
      }
    };

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      // { stream: true } keeps multi-byte UTF-8 chars intact across chunks.
      buffer += decoder.decode(value, { stream: true });

      let sepIndex;
      while ((sepIndex = buffer.indexOf('\n\n')) !== -1) {
        const rawEvent = buffer.slice(0, sepIndex);
        buffer = buffer.slice(sepIndex + 2);
        dispatchEvent(rawEvent);
      }
    }

    // Flush any trailing event that wasn't terminated by a blank line.
    buffer += decoder.decode();
    if (buffer.trim()) {
      dispatchEvent(buffer);
    }
  },
};
