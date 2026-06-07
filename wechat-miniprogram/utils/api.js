const config = require("./config");

function request(path, data = {}) {
  return new Promise((resolve, reject) => {
    wx.request({
      url: `${config.apiBase}${path}`,
      method: "GET",
      data,
      timeout: 15000,
      success(res) {
        const body = res.data || {};
        if (res.statusCode >= 200 && res.statusCode < 300 && body.code === 0) {
          resolve(body.data);
          return;
        }
        reject(new Error(body.error || `HTTP ${res.statusCode}`));
      },
      fail(err) {
        reject(new Error(err.errMsg || "网络请求失败"));
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

module.exports = {
  getStores,
  getStats
};
