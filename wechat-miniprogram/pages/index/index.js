const api = require("../../utils/api");
const config = require("../../utils/config");

const BASE_CATEGORIES = [
  { key: "all", icon: "⌘", label: "全部" },
  { key: "火锅", icon: "♨", label: "火锅" },
  { key: "川菜", icon: "辣", label: "川菜" },
  { key: "小吃", icon: "食", label: "小吃" },
  { key: "面馆", icon: "面", label: "面馆" },
  { key: "烧烤", icon: "炙", label: "烧烤" },
  { key: "甜品饮品", icon: "甜", label: "甜品" },
  { key: "日料", icon: "和", label: "日料" },
  { key: "西餐", icon: "西", label: "西餐" },
  { key: "其他", icon: "…", label: "其他" }
];

const CATEGORY_COLORS = {
  "火锅": "#e74c3c",
  "川菜": "#e67e22",
  "小吃": "#f39c12",
  "面馆": "#f1c40f",
  "烧烤": "#c0392b",
  "甜品饮品": "#e91e63",
  "日料": "#3498db",
  "西餐": "#1abc9c",
  "其他": "#95a5a6"
};

Page({
  data: {
    loading: true,
    loadError: "",
    stores: [],
    filteredStores: [],
    markers: [],
    categories: BASE_CATEGORIES,
    currentCategory: "all",
    searchQuery: "",
    activeStoreId: null,
    selectedStore: null,
    detailOpen: false,
    sheetExpanded: false,
    mapCenter: config.mapCenter,
    mapScale: 13,
    locating: false,
    toast: ""
  },

  onLoad() {
    this.loadData();
    this.locateUser({ silent: true });
  },

  async loadData() {
    this.setData({ loading: true, loadError: "" });
    try {
      const stores = await api.getStores();
      const normalized = stores.map(normalizeStore);
      this.setData({
        stores: normalized,
        loading: false
      });
      this.applyFilters();
      this.updateCategoryCounts(normalized);
    } catch (err) {
      const hint = getApiHint();
      this.setData({
        loading: false,
        loadError: `数据加载失败：${err.message}${hint ? "\n" + hint : ""}`
      });
    }
  },

  onSearchInput(event) {
    this.setData({ searchQuery: (event.detail.value || "").trim() });
    this.applyFilters();
  },

  onCategoryTap(event) {
    const key = event.currentTarget.dataset.key;
    this.setData({ currentCategory: key, activeStoreId: null });
    this.applyFilters();
  },

  toggleSheet() {
    this.setData({ sheetExpanded: !this.data.sheetExpanded });
  },

  onMapTap() {
    if (this.data.detailOpen) {
      this.closeDetail();
    }
  },

  onMarkerTap(event) {
    const markerId = event.detail.markerId;
    this.openStore(markerId);
  },

  selectStore(event) {
    const id = Number(event.currentTarget.dataset.id);
    this.openStore(id);
  },

  openStore(id) {
    const store = this.data.stores.find(item => item.id === id);
    if (!store) return;

    const updates = {
      activeStoreId: id,
      selectedStore: store,
      detailOpen: true,
      sheetExpanded: false
    };
    if (store.hasCoords) {
      updates.mapCenter = { latitude: store.lat, longitude: store.lng };
      updates.mapScale = Math.max(this.data.mapScale, 15);
    }
    this.setData(updates);
    this.applyFilters();
  },

  closeDetail() {
    this.setData({ detailOpen: false });
  },

  focusSelectedStore() {
    const store = this.data.selectedStore;
    if (!store || !store.hasCoords) return;
    this.setData({
      mapCenter: { latitude: store.lat, longitude: store.lng },
      mapScale: 16,
      detailOpen: false
    });
    this.showToast("已定位到店铺");
  },

  locateUser(options = {}) {
    this.setData({ locating: true });
    wx.getLocation({
      type: "gcj02",
      success: res => {
        this.setData({
          mapCenter: { latitude: res.latitude, longitude: res.longitude },
          mapScale: 15,
          locating: false
        });
      },
      fail: () => {
        this.setData({ locating: false });
        if (!options.silent) {
          this.showToast("无法获取当前位置，请检查微信定位权限");
        }
      }
    });
  },

  applyFilters() {
    const query = this.data.searchQuery.toLowerCase();
    let filtered = this.data.stores;

    if (this.data.currentCategory !== "all") {
      filtered = filtered.filter(store => store.category === this.data.currentCategory);
    }
    if (query) {
      filtered = filtered.filter(store => matchSearch(store, query));
    }

    this.setData({
      filteredStores: filtered,
      markers: filtered.filter(store => store.hasCoords).map(store => markerFromStore(store, store.id === this.data.activeStoreId))
    });
  },

  updateCategoryCounts(stores) {
    const counts = stores.reduce((acc, store) => {
      if (store.category) acc[store.category] = (acc[store.category] || 0) + 1;
      return acc;
    }, {});
    this.setData({
      categories: BASE_CATEGORIES.map(cat => ({
        ...cat,
        count: cat.key === "all" ? stores.length : (counts[cat.key] || 0)
      }))
    });
  },

  showToast(message) {
    this.setData({ toast: message });
    clearTimeout(this.toastTimer);
    this.toastTimer = setTimeout(() => this.setData({ toast: "" }), 1600);
  }
});

function normalizeStore(raw) {
  const tags = parseArray(raw.tags);
  const dishes = parseArray(raw.recommend_dishes);
  const lat = Number(raw.lat || 0);
  const lng = Number(raw.lng || 0);
  const rating = Number(raw.rating || 0);
  return {
    ...raw,
    tags,
    recommend_dishes: dishes,
    lat,
    lng,
    hasCoords: Boolean(lat && lng),
    ratingText: rating ? "★".repeat(Math.min(Math.round(rating), 5)) : "暂无评分"
  };
}

function parseArray(value) {
  if (Array.isArray(value)) return value;
  if (!value) return [];
  try {
    const parsed = JSON.parse(value);
    return Array.isArray(parsed) ? parsed : [];
  } catch (err) {
    return [];
  }
}

function matchSearch(store, query) {
  const haystack = [
    store.name,
    store.category,
    store.address,
    store.blogger_name,
    ...store.tags,
    ...store.recommend_dishes
  ].filter(Boolean).join(" ").toLowerCase();
  return haystack.includes(query);
}

function markerFromStore(store, active) {
  const color = CATEGORY_COLORS[store.category] || "#ff6b35";
  return {
    id: store.id,
    latitude: store.lat,
    longitude: store.lng,
    title: store.name,
    width: active ? 34 : 28,
    height: active ? 34 : 28,
    callout: {
      content: store.name,
      color: "#f5f5f7",
      fontSize: 12,
      borderRadius: 10,
      bgColor: active ? color : "#1a1d29",
      padding: 8,
      display: active ? "ALWAYS" : "BYCLICK"
    }
  };
}

function getApiHint() {
  const base = config.apiBase || "";
  if (base.includes("127.0.0.1") || base.includes("localhost")) {
    return "手机扫码不能访问 127.0.0.1，请在 utils/config.js 改成电脑局域网 IP，例如 http://192.168.x.x:5000/api。";
  }
  if (base.startsWith("http://")) {
    return "真机预览请确认手机和电脑在同一 Wi-Fi，生产上线需要 HTTPS 和小程序合法请求域名。";
  }
  return "";
}
