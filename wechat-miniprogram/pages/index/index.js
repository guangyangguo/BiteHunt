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

const CLUSTER_ID_BASE = 1000000;

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
    this.currentMapScale = this.data.mapScale;
    this.loadData();
    this.locateUser({ silent: true });
  },

  onReady() {
    this.mapContext = wx.createMapContext("storeMap", this);
    this.refreshViewportStores();
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
    if (this.markerClusters && this.markerClusters[markerId]) {
      this.openCluster(markerId);
      return;
    }
    this.openStore(markerId);
  },

  onRegionChange(event) {
    if (event.type === "begin") {
      const causedBy = event.causedBy || (event.detail && event.detail.causedBy) || "";
      if (!causedBy || causedBy === "drag" || causedBy === "scale") {
        this.userMovedMap = true;
      }
      return;
    }
    if (event.type !== "end") return;
    if (event.detail && event.detail.scale) {
      this.currentMapScale = event.detail.scale;
    }
    clearTimeout(this.regionTimer);
    this.regionTimer = setTimeout(() => this.refreshViewportStores(), 180);
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
      this.currentMapScale = Math.max(this.data.mapScale, 15);
      updates.mapCenter = { latitude: store.lat, longitude: store.lng };
      updates.mapScale = this.currentMapScale;
    }
    this.setData(updates);
    this.applyFilters();
    this.focusStoreOnMap(store);
  },

  openCluster(markerId) {
    const stores = this.markerClusters[markerId] || [];
    const points = stores.map(store => ({ latitude: store.lat, longitude: store.lng }));
    if (!points.length) return;

    if (this.mapContext && points.length > 1) {
      this.mapContext.includePoints({
        points,
        padding: [120, 80, 220, 80]
      });
    } else {
      const store = stores[0];
      this.currentMapScale = Math.min(this.data.mapScale + 2, 18);
      this.setData({
        mapCenter: { latitude: store.lat, longitude: store.lng },
        mapScale: this.currentMapScale
      });
    }
    this.setData({ sheetExpanded: false, detailOpen: false });
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
    this.currentMapScale = 16;
    this.focusStoreOnMap(store);
    this.showToast("已定位到店铺");
  },

  copySourceVideo() {
    const store = this.data.selectedStore;
    if (!store || !store.sourceVideoUrl) {
      this.showToast("暂无来源视频链接");
      return;
    }
    wx.setClipboardData({
      data: store.sourceVideoUrl,
      success: () => this.showToast("已复制 B 站视频链接")
    });
  },

  locateUser(options = {}) {
    const silent = Boolean(options && options.silent);
    this.setData({ locating: true });
    wx.getLocation({
      type: "gcj02",
      success: res => {
        if (silent && this.userMovedMap) {
          this.setData({ locating: false });
          return;
        }
        this.setData({
          mapCenter: { latitude: res.latitude, longitude: res.longitude },
          mapScale: 15,
          locating: false
        });
        this.currentMapScale = 15;
      },
      fail: err => {
        this.setData({ locating: false });
        if (!silent) {
          const message = err && err.errMsg ? err.errMsg : "";
          if (message.includes("auth deny") || message.includes("authorize")) {
            this.showToast("请允许位置权限后再定位");
            wx.openSetting({});
          } else {
            this.showToast("无法获取当前位置，请检查微信定位权限");
          }
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

    this.baseFilteredStores = filtered;
    this.refreshViewportStores({ fallbackStores: filtered });
  },

  refreshViewportStores(options = {}) {
    const base = this.baseFilteredStores || this.data.stores || [];
    const fallbackStores = options.fallbackStores || base;

    if (!this.mapContext) {
      this.setVisibleStores(fallbackStores);
      return;
    }

    this.mapContext.getRegion({
      success: region => {
        const visible = filterStoresInRegion(base, region);
        this.updateScaleThenSetVisibleStores(visible);
      },
      fail: () => this.setVisibleStores(fallbackStores)
    });
  },

  updateScaleThenSetVisibleStores(stores) {
    if (!this.mapContext || !this.mapContext.getScale) {
      this.setVisibleStores(stores);
      return;
    }
    this.mapContext.getScale({
      success: res => {
        const scale = Number(res && res.scale);
        if (scale) {
          this.currentMapScale = scale;
          this.setVisibleStores(stores, scale);
        } else {
          this.setVisibleStores(stores);
        }
      },
      fail: () => this.setVisibleStores(stores)
    });
  },

  setVisibleStores(stores, scale = this.currentMapScale || this.data.mapScale) {
    const markerStores = stores.filter(store => store.hasCoords);
    this.markerClusters = {};
    this.setData({
      filteredStores: stores,
      markers: buildMarkers(markerStores, this.data.activeStoreId, scale, this.markerClusters)
    });
  },

  focusStoreOnMap(store) {
    if (!this.mapContext || !store || !store.hasCoords) return;
    this.mapContext.includePoints({
      points: [{ latitude: store.lat, longitude: store.lng }],
      padding: [220, 80, 260, 80]
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
    ratingText: rating ? "★".repeat(Math.min(Math.round(rating), 5)) : "暂无评分",
    ratingLabel: getRatingLabel(rating),
    ratingShortLabel: getRatingShortLabel(rating),
    ratingClass: rating ? `level-${Math.min(Math.max(Math.round(rating), 1), 5)}` : "empty",
    sourceVideoUrl: getVideoUrl(raw),
    sourceVideoTitle: raw.source_video_title || "B站探店视频"
  };
}

function getRatingLabel(rating) {
  const value = Number(rating || 0);
  if (!value) return "暂无评分";
  const rounded = Math.min(Math.max(Math.round(value), 1), 5);
  const label = getRatingWord(rounded);
  return `${label} · ${value.toFixed(value % 1 ? 1 : 0)}/5`;
}

function getRatingShortLabel(rating) {
  const value = Number(rating || 0);
  if (!value) return "-";
  return getRatingWord(Math.min(Math.max(Math.round(value), 1), 5));
}

function getRatingWord(rounded) {
  const labels = {
    5: "强烈推荐",
    4: "推荐",
    3: "中规中矩",
    2: "谨慎",
    1: "避雷"
  };
  return labels[rounded];
}

function getVideoUrl(store) {
  if (store.source_video_url) return store.source_video_url;
  const bvid = store.source_video_bvid || store.platform_video_id;
  return bvid ? `https://www.bilibili.com/video/${bvid}` : "";
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

function filterStoresInRegion(stores, region) {
  if (!region || !region.southwest || !region.northeast) return stores;
  const sw = region.southwest;
  const ne = region.northeast;
  return stores.filter(store => {
    if (!store.hasCoords) return false;
    const inLat = store.lat >= sw.latitude && store.lat <= ne.latitude;
    const inLng = sw.longitude <= ne.longitude
      ? store.lng >= sw.longitude && store.lng <= ne.longitude
      : store.lng >= sw.longitude || store.lng <= ne.longitude;
    return inLat && inLng;
  });
}

function buildMarkers(stores, activeStoreId, scale, clusterMap) {
  const zoom = Number(scale || 13);
  if (zoom >= 16 || stores.length <= 1) {
    return stores.map(store => markerFromStore(store, store.id === activeStoreId));
  }

  const cellSize = getClusterCellSize(zoom);
  const grouped = stores.reduce((acc, store) => {
    const key = `${Math.floor(store.lat / cellSize)}:${Math.floor(store.lng / cellSize)}`;
    if (!acc[key]) acc[key] = [];
    acc[key].push(store);
    return acc;
  }, {});

  let clusterIndex = 0;
  const markers = [];
  Object.keys(grouped).forEach(key => {
    const group = grouped[key];
    if (group.length === 1) {
      markers.push(markerFromStore(group[0], group[0].id === activeStoreId));
      return;
    }

    const markerId = CLUSTER_ID_BASE + clusterIndex++;
    clusterMap[markerId] = group;
    markers.push(clusterMarkerFromStores(markerId, group));
  });
  return markers;
}

function getClusterCellSize(zoom) {
  if (zoom <= 10) return 0.16;
  if (zoom <= 12) return 0.08;
  if (zoom <= 14) return 0.035;
  return 0.016;
}

function clusterMarkerFromStores(markerId, stores) {
  const total = stores.length;
  const latitude = stores.reduce((sum, store) => sum + store.lat, 0) / total;
  const longitude = stores.reduce((sum, store) => sum + store.lng, 0) / total;
  const topStore = stores.slice().sort((a, b) => Number(b.rating || 0) - Number(a.rating || 0))[0];
  const color = CATEGORY_COLORS[topStore.category] || "#ff6b35";

  return {
    id: markerId,
    latitude,
    longitude,
    title: `${total} 家店`,
    width: 40,
    height: 40,
    label: {
      content: String(total),
      color: "#ffffff",
      fontSize: 13,
      bgColor: color,
      borderRadius: 18,
      padding: 8,
      textAlign: "center"
    },
    callout: {
      content: `该区域 ${total} 家店`,
      color: "#f5f5f7",
      fontSize: 12,
      borderRadius: 10,
      bgColor: "#1a1d29",
      padding: 8,
      display: "BYCLICK"
    }
  };
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
