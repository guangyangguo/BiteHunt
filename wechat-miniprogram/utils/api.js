const config = require("./config");

function request(path, data = {}, options = {}) {
  return new Promise((resolve, reject) => {
    const method = options.method || "GET";
    const url = `${config.apiBase}${path}`;
    const token = wx.getStorageSync("userToken") || "";
    const header = Object.assign(
      method === "POST" ? { "Content-Type": "application/json" } : {},
      options.header || {}
    );
    if (token) {
      header.Authorization = `Bearer ${token}`;
    }
    wx.request({
      url,
      method,
      data,
      header,
      timeout: options.timeout || 15000,
      success(res) {
        const body = res.data || {};
        if (res.statusCode >= 200 && res.statusCode < 300 && body.code === 0) {
          resolve(body.data);
          return;
        }
        reject(new Error(`${body.error || `HTTP ${res.statusCode}`} @ ${url}`));
      },
      fail(err) {
        reject(new Error(`${err.errMsg || "网络请求失败"} @ ${url}`));
      }
    });
  });
}

function getStores(category) {
  const data = category && category !== "all" ? { category } : {};
  return request("/stores", data);
}

function getStats() {
  return request("/stats");
}

function getUserProfile() {
  return request("/user/profile");
}

function loginUser(payload = {}) {
  return request("/user/login", payload, { method: "POST" });
}

function logoutUser() {
  return request("/user/logout", {}, { method: "POST" });
}

function getUserFavorites() {
  return request("/user/favorites");
}

function favoriteStore(storeId) {
  return request(`/stores/${storeId}/favorite`, {}, { method: "POST" });
}

function unfavoriteStore(storeId) {
  return request(`/stores/${storeId}/favorite`, {}, { method: "DELETE" });
}

function guideRecommend(query, location) {
  return request("/guide/recommend", { query, location }, { method: "POST", timeout: 60000 });
}

function guideChat(messages, location) {
  return request("/guide/chat", { messages, location }, { method: "POST", timeout: 60000 });
}

function guideChatStream(messages, location, handlers = {}) {
  let pending = "";
  const decoder = createDecoder();
  const task = wx.request({
    url: `${config.apiBase}/guide/chat/stream`,
    method: "POST",
    data: { messages, location },
    header: { "Content-Type": "application/json" },
    timeout: 60000,
    enableChunked: true,
    success(res) {
      if (res.statusCode < 200 || res.statusCode >= 300) {
        handlers.onError && handlers.onError(new Error(`HTTP ${res.statusCode}`));
      }
    },
    fail(err) {
      if (err && String(err.errMsg || "").includes("abort")) {
        handlers.onAbort && handlers.onAbort();
        return;
      }
      handlers.onError && handlers.onError(new Error((err && err.errMsg) || "网络请求失败"));
    },
    complete() {
      flushStreamBuffer();
      handlers.onComplete && handlers.onComplete();
    }
  });

  if (task && task.onChunkReceived) {
    task.onChunkReceived(res => {
      pending += decoder.decode(res.data);
      flushStreamBuffer();
    });
  }

  function flushStreamBuffer() {
    let lineBreak = pending.indexOf("\n");
    while (lineBreak >= 0) {
      const line = pending.slice(0, lineBreak).trim();
      pending = pending.slice(lineBreak + 1);
      if (line) {
        try {
          handlers.onEvent && handlers.onEvent(JSON.parse(line));
        } catch (err) {
          handlers.onError && handlers.onError(new Error("AI向导流式响应解析失败"));
        }
      }
      lineBreak = pending.indexOf("\n");
    }
  }

  return task;
}

function createDecoder() {
  if (typeof TextDecoder !== "undefined") {
    const decoder = new TextDecoder("utf-8");
    return { decode: buffer => decoder.decode(buffer, { stream: true }) };
  }
  return {
    decode(buffer) {
      const bytes = new Uint8Array(buffer);
      let binary = "";
      for (let i = 0; i < bytes.length; i += 1) {
        binary += String.fromCharCode(bytes[i]);
      }
      try {
        return decodeURIComponent(escape(binary));
      } catch (err) {
        return binary;
      }
    }
  };
}

module.exports = {
  getStores,
  getStats,
  getUserProfile,
  loginUser,
  logoutUser,
  getUserFavorites,
  favoriteStore,
  unfavoriteStore,
  guideRecommend,
  guideChat,
  guideChatStream
};
