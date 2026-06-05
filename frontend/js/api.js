/**
 * 探店地图 - API 通信层
 * 与后端 Flask 服务通信
 */

const API_BASE = window.API_BASE || '/api';

/**
 * 带超时的 fetch 封装
 * @param {string} url
 * @param {object} options - fetch options
 * @param {number} timeoutMs - 超时毫秒，默认 15 秒
 */
async function apiFetch(url, options = {}, timeoutMs = 15000) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const resp = await fetch(url, { ...options, signal: controller.signal });
    return resp;
  } finally {
    clearTimeout(timer);
  }
}

const API = {
  // ==================== 店铺 ====================

  async getStores(category = null) {
    const params = category && category !== 'all' ? `?category=${encodeURIComponent(category)}` : '';
    const url = `${API_BASE}/stores${params}`;
    console.log('[tandian] getStores URL:', url);
    try {
      const resp = await apiFetch(url);
      const data = await resp.json();
      if (data.code !== 0) throw new Error(data.error);
      return data.data;
    } catch (e) {
      console.error('[tandian] getStores 失败:', e.name, e.message);
      throw e;
    }
  },

  async getStoreDetail(storeId) {
    const resp = await fetch(`${API_BASE}/stores/${storeId}`);
    const data = await resp.json();
    if (data.code !== 0) throw new Error(data.error);
    return data.data;
  },

  async deleteStore(storeId) {
    const resp = await fetch(`${API_BASE}/stores/${storeId}`, { method: 'DELETE' });
    const data = await resp.json();
    return data;
  },

  async updateStore(storeId, updates) {
    const resp = await fetch(`${API_BASE}/stores/${storeId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(updates),
    });
    const data = await resp.json();
    if (data.code !== 0) throw new Error(data.error);
    return data;
  },

  async regeocodeStore(storeId) {
    const resp = await fetch(`${API_BASE}/stores/${storeId}/regeocode`, { method: 'POST' });
    const data = await resp.json();
    if (data.code !== 0) throw new Error(data.error);
    return data;
  },

  // ==================== 博主 ====================

  async getBloggers() {
    const resp = await fetch(`${API_BASE}/bloggers`);
    const data = await resp.json();
    if (data.code !== 0) throw new Error(data.error);
    return data.data;
  },

  async searchBloggers(keyword) {
    const resp = await fetch(`${API_BASE}/bloggers/search?q=${encodeURIComponent(keyword)}`);
    const data = await resp.json();
    if (data.code !== 0) throw new Error(data.error);
    return data.data;
  },

  async addBlogger(bloggerData) {
    const resp = await fetch(`${API_BASE}/bloggers`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(bloggerData),
    });
    const data = await resp.json();
    if (data.code !== 0) throw new Error(data.error);
    return data;
  },

  async deleteBlogger(bloggerId) {
    const resp = await fetch(`${API_BASE}/bloggers/${bloggerId}`, { method: 'DELETE' });
    const data = await resp.json();
    return data;
  },

  async fetchVideos(bloggerId) {
    const resp = await fetch(`${API_BASE}/bloggers/${bloggerId}/fetch`, { method: 'POST' });
    const data = await resp.json();
    if (data.code !== 0) throw new Error(data.error);
    return data;
  },

  // ==================== 视频 ====================

  async addVideoByBV(bv, bloggerId) {
    const resp = await fetch(`${API_BASE}/videos/add`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ bv, blogger_id: bloggerId }),
    });
    const data = await resp.json();
    if (data.code !== 0) throw new Error(data.error);
    return data;
  },

  async getVideos(params = {}) {
    const query = new URLSearchParams(params).toString();
    const resp = await fetch(`${API_BASE}/videos?${query}`);
    const data = await resp.json();
    if (data.code !== 0) throw new Error(data.error);
    return data.data;
  },

  async analyzeVideo(videoId) {
    const resp = await apiFetch(`${API_BASE}/videos/${videoId}/analyze`, { method: 'POST' }, 120000);
    const data = await resp.json();
    if (data.code !== 0) throw new Error(data.error);
    return data;
  },

  /**
   * 流式分析单个视频 — 实时获取步骤级进度
   * @param {number} videoId
   * @param {function} onProgress - 回调: ({step, total, name}) => void
   * @returns {Promise<object>} 分析结果 {success, stores_found, summary, error}
   */
  async analyzeVideoStream(videoId, onProgress) {
    const resp = await apiFetch(`${API_BASE}/videos/${videoId}/analyze/stream`, { method: 'POST' }, 120000);
    if (!resp.ok) {
      const errData = await resp.json().catch(() => ({}));
      throw new Error(errData.error || `HTTP ${resp.status}`);
    }

    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      const lines = buffer.split('\n');
      buffer = lines.pop(); // 最后一个可能是不完整的行

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        try {
          const msg = JSON.parse(line.slice(6));
          if (msg.type === 'progress') {
            onProgress(msg);
          } else if (msg.type === 'done') {
            if (!msg.success) throw new Error(msg.error || '分析失败');
            return msg;
          } else if (msg.type === 'error') {
            throw new Error(msg.error || '分析异常');
          }
          // heartbeat — 忽略
        } catch (e) {
          if (e.message.includes('分析')) throw e; // 业务错误
          // JSON 解析错误 — 可能是心跳或格式问题，跳过
        }
      }
    }

    throw new Error('连接意外关闭');
  },

  async batchAnalyze(videoIds) {
    const resp = await fetch(`${API_BASE}/videos/batch-analyze`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ video_ids: videoIds }),
    });
    const data = await resp.json();
    return data;
  },

  // ==================== 统计 ====================

  async getStats() {
    const resp = await apiFetch(`${API_BASE}/stats`);
    const data = await resp.json();
    if (data.code !== 0) throw new Error(data.error);
    return data.data;
  },

  async deleteVideo(videoId) {
    const resp = await fetch(`${API_BASE}/videos/${videoId}`, { method: 'DELETE' });
    const data = await resp.json();
    if (data.code !== 0) throw new Error(data.error);
    return data;
  },

  // ==================== 健康 ====================

  async healthCheck() {
    try {
      const resp = await fetch(`${API_BASE}/health`);
      return resp.ok;
    } catch {
      return false;
    }
  },
};
