const API = require("../../utils/api");

const TOKEN_KEY = "userToken";
const DEVICE_KEY = "userDeviceId";

const defaultProfile = {
  is_logged_in: false,
  nickname: "未登录用户",
  subtitle: "登录后可使用收藏、历史和偏好",
  avatar: "",
  initial: "我",
  stats: {
    favorites: 0,
    visited: 0,
    guides: 0
  },
  features: {
    favorites: false,
    history: false,
    preferences: false
  }
};

Page({
  data: {
    profile: defaultProfile,
    loading: false,
    loggingIn: false,
    favoriteStores: [],
    favoritesOpen: false,
    favoritesLoading: false
  },

  onLoad() {
    this.ensureDeviceId();
    this.loadProfile();
  },

  onShow() {
    this.loadProfile();
  },

  ensureDeviceId() {
    let deviceId = wx.getStorageSync(DEVICE_KEY);
    if (!deviceId) {
      deviceId = `mp-${Date.now()}-${Math.random().toString(16).slice(2)}`;
      wx.setStorageSync(DEVICE_KEY, deviceId);
    }
    return deviceId;
  },

  async loadProfile() {
    if (this.data.loading) return;
    this.setData({ loading: true });
    try {
      const profile = await API.getUserProfile();
      this.applyProfile(profile);
    } catch (err) {
      this.setData({ profile: defaultProfile });
    } finally {
      this.setData({ loading: false });
    }
  },

  async onLoginTap() {
    if (this.data.profile.is_logged_in) {
      this.onLogoutTap();
      return;
    }
    if (this.data.loggingIn) return;
    this.setData({ loggingIn: true });
    try {
      const loginRes = await wxLogin();
      const profile = await API.loginUser({
        provider: "wechat",
        code: loginRes.code,
        device_id: this.ensureDeviceId()
      });
      if (profile.token) {
        wx.setStorageSync(TOKEN_KEY, profile.token);
      }
      this.applyProfile(profile);
      wx.showToast({ title: "登录成功", icon: "success" });
    } catch (err) {
      wx.showToast({ title: err.message || "登录失败", icon: "none" });
    } finally {
      this.setData({ loggingIn: false });
    }
  },

  async onLogoutTap() {
    try {
      await API.logoutUser();
    } catch (err) {
      // Local logout should still happen if the network request fails.
    }
    wx.removeStorageSync(TOKEN_KEY);
    this.setData({ profile: defaultProfile, favoriteStores: [], favoritesOpen: false });
    wx.showToast({ title: "已退出登录", icon: "none" });
  },

  onProtectedTap(event) {
    const name = event.currentTarget.dataset.name || "该功能";
    if (!this.data.profile.is_logged_in) {
      wx.showToast({ title: "请先登录", icon: "none" });
      return;
    }
    if (event.currentTarget.dataset.action === "favorites") {
      this.loadFavorites();
      return;
    }
    wx.showToast({ title: `${name}即将开放`, icon: "none" });
  },

  async loadFavorites() {
    if (this.data.favoritesLoading) return;
    this.setData({ favoritesLoading: true, favoritesOpen: true });
    try {
      const stores = await API.getUserFavorites();
      this.setData({ favoriteStores: (stores || []).map(normalizeFavoriteStore) });
    } catch (err) {
      wx.showToast({ title: err.message || "收藏加载失败", icon: "none" });
    } finally {
      this.setData({ favoritesLoading: false });
    }
  },

  closeFavoritesDrawer() {
    this.setData({ favoritesOpen: false });
  },

  openFavoriteStore(event) {
    const id = Number(event.currentTarget.dataset.id || 0);
    if (!id) return;
    this.closeFavoritesDrawer();
    wx.setStorageSync("pendingStoreId", id);
    wx.setStorageSync("pendingStoreFocus", true);
    wx.switchTab({ url: "/pages/index/index" });
  },

  applyProfile(profile) {
    const normalized = normalizeProfile(profile);
    if (normalized.token) {
      wx.setStorageSync(TOKEN_KEY, normalized.token);
    }
    this.setData({ profile: normalized });
  }
});

function wxLogin() {
  return new Promise((resolve, reject) => {
    wx.login({
      success(res) {
        if (res.code) {
          resolve(res);
          return;
        }
        reject(new Error("微信登录凭证为空"));
      },
      fail(err) {
        reject(new Error((err && err.errMsg) || "微信登录失败"));
      }
    });
  });
}

function normalizeFavoriteStore(store) {
  return {
    ...store,
    priceText: store.avg_price ? `¥${store.avg_price}/人` : "人均未知",
    categoryText: store.category || "未分类"
  };
}

function normalizeProfile(profile) {
  const data = Object.assign({}, defaultProfile, profile || {});
  data.stats = Object.assign({}, defaultProfile.stats, data.stats || {});
  data.features = Object.assign({}, defaultProfile.features, data.features || {});
  data.initial = data.nickname ? String(data.nickname).slice(0, 1) : "我";
  data.subtitle = data.is_logged_in ? "欢迎回来，继续发现值得吃的店" : defaultProfile.subtitle;
  return data;
}
