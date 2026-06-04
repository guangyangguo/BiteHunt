/**
 * 探店地图 - API 通信层
 * 与后端 Flask 服务通信
 */

const API_BASE = window.API_BASE || '/api';

const API = {
  // ==================== 店铺 ====================

  async getStores(category = null) {
    const params = category && category !== 'all' ? `?category=${encodeURIComponent(category)}` : '';
    const resp = await fetch(`${API_BASE}/stores${params}`);
    const data = await resp.json();
    if (data.code !== 0) throw new Error(data.error);
    return data.data;
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
    const resp = await fetch(`${API_BASE}/videos/${videoId}/analyze`, { method: 'POST' });
    const data = await resp.json();
    if (data.code !== 0) throw new Error(data.error);
    return data;
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
    const resp = await fetch(`${API_BASE}/stats`);
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
