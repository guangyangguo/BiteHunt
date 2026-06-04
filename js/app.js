/**
 * 探店地图 - Food Explorer Map
 * 主应用逻辑：地图、标记、筛选、搜索、详情面板
 */

(function () {
  'use strict';

  // ==================== 状态管理 ====================
  const state = {
    currentCategory: 'all',
    searchQuery: '',
    activeStoreId: null,
    sidebarVisible: true,
    detailOpen: false,
    markers: [],
    filteredStores: [],
  };

  // ==================== DOM 引用 ====================
  const $ = (sel) => document.querySelector(sel);
  const $$ = (sel) => document.querySelectorAll(sel);

  const dom = {
    map: $('#map'),
    sidebar: $('.sidebar'),
    sidebarContent: $('.sidebar-content'),
    sidebarToggle: $('.sidebar-toggle'),
    sidebarHeader: $('.sidebar-header h2'),
    searchInput: $('#searchInput'),
    categoryBar: $('.category-bar'),
    detailOverlay: $('.detail-overlay'),
    detailBackdrop: $('.detail-backdrop'),
    detailClose: $('.detail-close'),
    statsTotal: $('#statTotal'),
    statsBloggers: $('#statBloggers'),
    statsCategories: $('#statCategories'),
    toast: $('#toast'),
  };

  // ==================== 初始化 ====================
  let map;
  let markersGroup;

  function init() {
    initMap();
    initCategories();
    initSearch();
    initSidebarToggle();
    initDetailClose();
    updateStats();
    renderStoreList(EXPLORE_DATA.stores);
  }

  // ==================== 地图初始化 ====================
  function initMap() {
    // 成都市中心
    const center = [30.655, 104.075];
    const zoom = 13;

    map = L.map('map', {
      center: center,
      zoom: zoom,
      zoomControl: true,
      preferCanvas: true,
      attributionControl: true,
    });

    // 高德地图瓦片（国内速度快）
    L.tileLayer('https://webrd0{s}.is.autonavi.com/appmaptile?lang=zh_cn&size=1&scale=1&style=8&x={x}&y={y}&z={z}', {
      subdomains: ['1', '2', '3', '4'],
      attribution: '&copy; 高德地图 | 探店地图',
      maxZoom: 18,
    }).addTo(map);

    // 创建一个 FeatureGroup 来管理所有标记
    markersGroup = L.featureGroup().addTo(map);

    // 渲染所有标记
    renderAllMarkers();

    // 地图移动/缩放时更新聚类
    map.on('moveend', debounce(updateVisibleMarkers, 150));
    map.on('zoomend', debounce(updateVisibleMarkers, 150));

    // 点击地图空白区域关闭详情
    map.on('click', () => {
      if (state.detailOpen) closeDetail();
    });
  }

  // ==================== 自定义标记渲染 ====================
  function createMarkerIcon(category, isActive) {
    const color = CATEGORY_COLORS[category] || '#ff6b35';
    const size = isActive ? 40 : 36;

    return L.divIcon({
      className: 'custom-marker',
      html: `
        <div class="custom-marker" style="width:${size}px;height:${size}px;">
          <div class="marker-pulse" style="--marker-color:${color};width:${size}px;height:${size}px;"></div>
          <div class="marker-dot" style="background:${color};--marker-color:${color};"></div>
        </div>
      `,
      iconSize: [size, size],
      iconAnchor: [size / 2, size / 2],
      popupAnchor: [0, -(size / 2) - 4],
    });
  }

  function renderAllMarkers(stores) {
    const data = stores || EXPLORE_DATA.stores;
    markersGroup.clearLayers();
    state.markers = [];

    data.forEach((store) => {
      const marker = L.marker([store.lat, store.lng], {
        icon: createMarkerIcon(store.category, false),
        storeId: store.id,
      });

      marker.on('click', () => {
        highlightStore(store.id);
        openDetail(store.id);
      });

      marker.on('mouseover', function () {
        if (state.activeStoreId !== store.id) {
          this.setIcon(createMarkerIcon(store.category, true));
        }
      });

      marker.on('mouseout', function () {
        if (state.activeStoreId !== store.id) {
          this.setIcon(createMarkerIcon(store.category, false));
        }
      });

      marker.bindTooltip(store.name, {
        direction: 'top',
        offset: [0, -20],
        className: 'marker-tooltip',
        opacity: 0.9,
      });

      state.markers.push(marker);
      markersGroup.addLayer(marker);
    });

    // 适配地图视野
    if (state.markers.length > 0 && stores === EXPLORE_DATA.stores) {
      map.fitBounds(markersGroup.getBounds().pad(0.1), { maxZoom: 14 });
    }
  }

  function updateVisibleMarkers() {
    // 在高缩放级别时不做额外处理，leaflet 自动优化渲染
  }

  // ==================== 店铺高亮 ====================
  function highlightStore(storeId) {
    // 取消之前的高亮
    if (state.activeStoreId) {
      const prevStore = EXPLORE_DATA.stores.find((s) => s.id === state.activeStoreId);
      if (prevStore) {
        const prevMarker = state.markers.find((m) => m.options.storeId === state.activeStoreId);
        if (prevMarker) {
          prevMarker.setIcon(createMarkerIcon(prevStore.category, false));
        }
      }
    }

    // 设置新高亮
    state.activeStoreId = storeId;
    const store = EXPLORE_DATA.stores.find((s) => s.id === storeId);
    if (store) {
      const marker = state.markers.find((m) => m.options.storeId === storeId);
      if (marker) {
        marker.setIcon(createMarkerIcon(store.category, true));
        marker.setZIndexOffset(1000);
        // 飞行动画到该位置
        map.flyTo([store.lat, store.lng], Math.max(map.getZoom(), 15), {
          duration: 0.8,
        });
      }
    }

    // 更新侧边栏高亮
    $$('.store-card').forEach((card) => {
      card.classList.toggle('active', card.dataset.storeId === storeId);
    });
  }

  // ==================== 店铺详情面板 ====================
  function openDetail(storeId) {
    const store = EXPLORE_DATA.stores.find((s) => s.id === storeId);
    if (!store) return;

    const blogger = EXPLORE_DATA.bloggers.find((b) => b.id === store.bloggerId);
    const color = CATEGORY_COLORS[store.category] || '#ff6b35';

    dom.detailOverlay.innerHTML = `
      <div class="detail-header">
        <button class="detail-close" onclick="APP.closeDetail()">✕</button>
        <h2 class="detail-name">${store.name}</h2>
        <span class="detail-category" style="background:${color}20;color:${color};border:1px solid ${color}40">${store.category}</span>
      </div>
      <div class="detail-body">
        <div class="detail-section">
          <h4>基本信息</h4>
          <div class="detail-info-grid">
            <div class="detail-info-item">
              <div class="info-label">⭐ 评分</div>
              <div class="info-value">${store.rating}</div>
            </div>
            <div class="detail-info-item">
              <div class="info-label">💰 人均</div>
              <div class="info-value">¥${store.avgPrice}</div>
            </div>
            <div class="detail-info-item">
              <div class="info-label">📅 探店日期</div>
              <div class="info-value">${store.visitDate}</div>
            </div>
            <div class="detail-info-item">
              <div class="info-label">🏷️ 标签</div>
              <div class="info-value" style="font-size:12px;">${store.tags.join(' · ')}</div>
            </div>
          </div>
        </div>

        <div class="detail-section">
          <h4>📍 地址</h4>
          <p class="detail-address">${store.address}</p>
        </div>

        <div class="detail-section">
          <h4>🍽️ 推荐菜品</h4>
          <div class="detail-dishes">
            ${store.recommendDishes.map((d) => `<span class="detail-dish">${d}</span>`).join('')}
          </div>
        </div>

        ${store.note ? `
        <div class="detail-section">
          <h4>💬 博主点评</h4>
          <div class="detail-note">"${store.note}"</div>
        </div>
        ` : ''}

        ${blogger ? `
        <div class="detail-section">
          <h4>🎥 探店博主</h4>
          <div class="detail-blogger">
            <div class="blogger-avatar">${blogger.avatar}</div>
            <div class="blogger-info">
              <div class="blogger-name">${blogger.name}</div>
              <div class="blogger-meta">${blogger.platform} · ${blogger.followers}粉丝</div>
              <div class="blogger-meta" style="margin-top:4px;color:var(--text-secondary)">${blogger.bio}</div>
            </div>
          </div>
        </div>
        ` : ''}
      </div>
    `;

    dom.detailOverlay.classList.add('open');
    dom.detailBackdrop.classList.add('open');
    state.detailOpen = true;

    // 移动端滚动到顶部
    dom.detailOverlay.querySelector('.detail-body').scrollTop = 0;
  }

  function closeDetail() {
    dom.detailOverlay.classList.remove('open');
    dom.detailBackdrop.classList.remove('open');
    state.detailOpen = false;
  }

  // ==================== 侧边栏店铺列表 ====================
  function renderStoreList(stores) {
    state.filteredStores = stores;
    const count = stores.length;

    dom.sidebarHeader.textContent = count > 0 ? `发现 ${count} 家好店` : '没有找到店铺';

    if (count === 0) {
      dom.sidebarContent.innerHTML = `
        <div style="text-align:center;padding:40px 20px;color:var(--text-muted);">
          <div style="font-size:40px;margin-bottom:12px;">🔍</div>
          <p>没有找到匹配的店铺</p>
          <p style="font-size:12px;margin-top:6px;">试试调整筛选条件</p>
        </div>
      `;
      return;
    }

    dom.sidebarContent.innerHTML = stores
      .map(
        (store) => `
      <div class="store-card${state.activeStoreId === store.id ? ' active' : ''}"
           data-store-id="${store.id}"
           onclick="APP.selectStore('${store.id}')">
        <div class="card-header">
          <div class="store-name">${store.name}</div>
          <div class="store-rating">⭐ ${store.rating}</div>
        </div>
        <div class="store-meta">
          <span>💰 ¥${store.avgPrice}/人</span>
          <span>📅 ${store.visitDate}</span>
        </div>
        <div class="store-tags">
          ${store.tags.map((t) => `<span class="tag">${t}</span>`).join('')}
        </div>
        <div class="store-blogger">
          <span>🎥</span>
          <span>${store.bloggerName} 探访</span>
        </div>
      </div>
    `
      )
      .join('');
  }

  function selectStore(storeId) {
    highlightStore(storeId);
    openDetail(storeId);
  }

  // ==================== 分类筛选 ====================
  function initCategories() {
    dom.categoryBar.innerHTML = CATEGORIES.map(
      (cat) => `
      <button class="category-btn${cat.key === 'all' ? ' active' : ''}"
              data-category="${cat.key}"
              onclick="APP.filterByCategory('${cat.key}')">
        <span>${cat.icon}</span>
        <span class="cat-label">${cat.label}</span>
      </button>
    `
    ).join('');
  }

  function filterByCategory(category) {
    state.currentCategory = category;
    state.activeStoreId = null;

    // 更新按钮状态
    $$('.category-btn').forEach((btn) => {
      btn.classList.toggle('active', btn.dataset.category === category);
    });

    // 筛选数据
    let filtered = EXPLORE_DATA.stores;
    if (category !== 'all') {
      filtered = filtered.filter((s) => s.category === category);
    }
    if (state.searchQuery) {
      filtered = filtered.filter((s) => matchSearch(s, state.searchQuery));
    }

    // 更新地图标记
    renderAllMarkers(filtered);

    // 更新列表
    renderStoreList(filtered);

    // 适配视野
    if (filtered.length > 0) {
      const group = L.featureGroup(state.markers);
      map.fitBounds(group.getBounds().pad(0.15), { maxZoom: 15 });
    }

    // 更新计数
    $$('.category-btn .cat-count').forEach((el) => el.remove());
    $$('.category-btn').forEach((btn) => {
      const cat = btn.dataset.category;
      if (cat === 'all') return;
      const count = EXPLORE_DATA.stores.filter((s) => s.category === cat).length;
      const span = document.createElement('span');
      span.className = 'cat-count';
      span.textContent = count;
      btn.appendChild(span);
    });
  }

  // ==================== 搜索 ====================
  function initSearch() {
    dom.searchInput.addEventListener('input', debounce(handleSearch, 300));
  }

  function handleSearch(e) {
    state.searchQuery = e.target.value.trim().toLowerCase();
    state.activeStoreId = null;

    let filtered = EXPLORE_DATA.stores;
    if (state.currentCategory !== 'all') {
      filtered = filtered.filter((s) => s.category === state.currentCategory);
    }
    if (state.searchQuery) {
      filtered = filtered.filter((s) => matchSearch(s, state.searchQuery));
    }

    renderAllMarkers(filtered);
    renderStoreList(filtered);

    if (filtered.length > 0 && state.searchQuery) {
      const group = L.featureGroup(state.markers);
      map.fitBounds(group.getBounds().pad(0.15), { maxZoom: 15 });
    }
  }

  function matchSearch(store, query) {
    return (
      store.name.toLowerCase().includes(query) ||
      store.category.toLowerCase().includes(query) ||
      store.tags.some((t) => t.toLowerCase().includes(query)) ||
      store.recommendDishes.some((d) => d.toLowerCase().includes(query)) ||
      store.bloggerName.toLowerCase().includes(query) ||
      store.address.toLowerCase().includes(query)
    );
  }

  // ==================== 侧边栏折叠 ====================
  function initSidebarToggle() {
    dom.sidebarToggle.addEventListener('click', () => {
      state.sidebarVisible = !state.sidebarVisible;
      dom.sidebar.classList.toggle('collapsed', !state.sidebarVisible);
      dom.sidebarToggle.textContent = state.sidebarVisible ? '◀' : '▶';
    });
  }

  // ==================== 详情关闭 ====================
  function initDetailClose() {
    dom.detailClose.addEventListener('click', closeDetail);
    dom.detailBackdrop.addEventListener('click', closeDetail);

    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && state.detailOpen) {
        closeDetail();
      }
    });
  }

  // ==================== 统计信息 ====================
  function updateStats() {
    const stores = EXPLORE_DATA.stores;
    const uniqueBloggers = new Set(stores.map((s) => s.bloggerId));
    const uniqueCategories = new Set(stores.map((s) => s.category));

    dom.statsTotal.textContent = stores.length;
    dom.statsBloggers.textContent = uniqueBloggers.size;
    dom.statsCategories.textContent = uniqueCategories.size;
  }

  // ==================== Toast ====================
  function showToast(message) {
    dom.toast.textContent = message;
    dom.toast.classList.add('show');
    clearTimeout(dom.toast._timeout);
    dom.toast._timeout = setTimeout(() => {
      dom.toast.classList.remove('show');
    }, 2000);
  }

  // ==================== 工具函数 ====================
  function debounce(fn, delay) {
    let timer;
    return function (...args) {
      clearTimeout(timer);
      timer = setTimeout(() => fn.apply(this, args), delay);
    };
  }

  // ==================== 暴露全局 API ====================
  window.APP = {
    selectStore,
    filterByCategory,
    closeDetail,
    showToast,
  };

  // ==================== 启动 ====================
  document.addEventListener('DOMContentLoaded', init);
})();
