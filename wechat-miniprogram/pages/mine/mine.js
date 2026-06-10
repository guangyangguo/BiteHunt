const API = require("../../utils/api");

const defaultProfile = {
  is_logged_in: false,
  nickname: "未登录用户",
  subtitle: "登录后可保存收藏、偏好和探店记录",
  avatar: "",
  initial: "我",
  stats: {
    favorites: 0,
    visited: 0,
    guides: 0
  }
};

Page({
  data: {
    profile: defaultProfile,
    loading: false
  },

  onLoad() {
    this.loadProfile();
  },

  onShow() {
    this.loadProfile();
  },

  async loadProfile() {
    if (this.data.loading) return;
    this.setData({ loading: true });
    try {
      const profile = await API.getUserProfile();
      this.setData({ profile: normalizeProfile(profile) });
    } catch (err) {
      this.setData({ profile: defaultProfile });
    } finally {
      this.setData({ loading: false });
    }
  },

  async onLoginTap() {
    try {
      const profile = await API.loginUser({ provider: "wechat_placeholder" });
      this.setData({ profile: normalizeProfile(profile) });
      wx.showToast({ title: "登录接口已预留", icon: "none" });
    } catch (err) {
      wx.showToast({ title: err.message || "登录暂未接入", icon: "none" });
    }
  },

  onPlaceholderTap(event) {
    const name = event.currentTarget.dataset.name || "该功能";
    wx.showToast({ title: `${name}待接入`, icon: "none" });
  }
});

function normalizeProfile(profile) {
  const data = Object.assign({}, defaultProfile, profile || {});
  data.stats = Object.assign({}, defaultProfile.stats, data.stats || {});
  data.initial = data.nickname ? String(data.nickname).slice(0, 1) : "我";
  data.subtitle = data.is_logged_in ? "欢迎回来，继续发现值得吃的店" : defaultProfile.subtitle;
  return data;
}
