/**
 * 探店地图 - Food Explorer Map
 * 主应用逻辑：地图、标记、筛选、搜索、详情面板
 * 数据来源：后端 API（动态加载，非静态数据）
 */

(function () {
  'use strict';

  // ==================== 品类定义 ====================
  const CATEGORIES = [
    { key: 'all', icon: '🏷️', label: '全部' },
    { key: '火锅', icon: '🫕', label: '火锅' },
    { key: '川菜', icon: '🌶️', label: '川菜' },
    { key: '小吃', icon: '🥟', label: '小吃' },
    { key: '面馆', icon: '🍜', label: '面馆' },
    { key: '烧烤', icon: '🍢', label: '烧烤' },
    { key: '甜品饮品', icon: '🍰', label: '甜品饮品' },
    { key: '创意料理', icon: '✨', label: '创意料理' },
    { key: '轻食简餐', icon: '🥗', label: '轻食简餐' },
    { key: '日料', icon: '🍣', label: '日料' },
    { key: '西餐', icon: '🥩', label: '西餐' },
    { key: '其他', icon: '🍽️', label: '其他' },
  ];

  // 品类对应颜色
  const CATEGORY_COLORS = {
    '火锅': '#e74c3c',
    '川菜': '#e67e22',
    '小吃': '#f39c12',
    '面馆': '#f1c40f',
    '烧烤': '#c0392b',
    '甜品饮品': '#e91e63',
    '创意料理': '#9b59b6',
    '轻食简餐': '#2ecc71',
    '日料': '#3498db',
    '西餐': '#1abc9c',
    '其他': '#95a5a6',
  };

  // ==================== 状态管理 ====================
  const state = {
    currentCategory: 'all',
    searchQuery: '',
    activeStoreId: null,
    sidebarVisible: false,
    detailOpen: false,
    markers: [],
    markerClusters: {},
    filteredStores: [],
    baseFilteredStores: [],
    allStoresCache: [],    // 全量店铺缓存（来自API）
    bloggersCache: [],     // 博主缓存
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
    loadingOverlay: null,
  };

  // ==================== 初始化 ====================
  let map;
  let markersGroup;

  async function init() {
    console.log('[tandian] init() 开始执行，即将调用 loadData()');
    showLoading(true);
    initMap();
    initCategories();
    initSearch();
    initSidebarToggle();
    initDetailClose();
    try {
      await loadData();
    } catch (e) {
      console.error('Init error:', e);
      showToast('数据加载失败，请检查后端服务');
    }
    showLoading(false);
  }

  async function loadData() {
    console.log('[tandian] loadData() 开始请求 API...');
    try {
      // 并行加载店铺和统计
      const [stores, stats] = await Promise.all([
        API.getStores(),
        API.getStats().catch(() => null),
      ]);

      state.allStoresCache = stores;
      state.filteredStores = stores;
      state.baseFilteredStores = stores;

      // 更新统计
      if (stats) {
        dom.statsTotal.textContent = stats.total_stores || stores.length;
        dom.statsBloggers.textContent = stats.total_bloggers || new Set(stores.map(s => s.source_blogger_id).filter(Boolean)).size;
        dom.statsCategories.textContent = stats.categories_list?.length || new Set(stores.map(s => s.category).filter(Boolean)).size;
      } else {
        updateStatsLocal();
      }

      // 渲染
      applyStoreResults(stores, { fitBounds: true });
      updateCategoryCounts(stores);
    } catch (err) {
      console.error('加载数据失败:', err);
      showToast('⚠️ 数据加载失败，请确认后端服务已启动');
      // 静态数据文件已移除，显示错误提示
    }
  }

  // ==================== 地图初始化 ====================
  function initMap() {
    // 默认中心点（成都，作为定位失败时的兜底）
    const defaultCenter = [30.655, 104.075];
    const defaultZoom = 13;

    map = L.map('map', {
      center: defaultCenter,
      zoom: defaultZoom,
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

    // 尝试获取用户当前位置
    if (navigator.geolocation) {
      navigator.geolocation.getCurrentPosition(
        function (pos) {
          const userLatLng = [pos.coords.latitude, pos.coords.longitude];
          map.setView(userLatLng, Math.max(map.getZoom(), 14));
          // 在地图上添加用户位置标记
          L.circleMarker(userLatLng, {
            radius: 8,
            fillColor: '#3b82f6',
            color: '#fff',
            weight: 2,
            fillOpacity: 0.9,
          }).addTo(map).bindTooltip('我的位置', {
            direction: 'top',
            offset: [0, -8],
          });
        },
        function () {
          // 定位失败或用户拒绝，保持默认中心
          console.log('Geolocation unavailable, using default center');
        },
        { enableHighAccuracy: true, timeout: 5000, maximumAge: 600000 }
      );
    }

    // ===== 当前位置按钮 =====
    const LocateControl = L.Control.extend({
      options: { position: 'bottomright' },
      onAdd: function () {
        const btn = L.DomUtil.create('button', 'leaflet-locate-btn');
        btn.title = '定位到当前位置';
        btn.innerHTML = '⊕';
        btn.setAttribute('aria-label', '定位到当前位置');

        L.DomEvent.on(btn, 'click', function (e) {
          L.DomEvent.stopPropagation(e);
          L.DomEvent.preventDefault(e);
          btn.classList.add('locating');
          btn.innerHTML = '⟳';

          if (!navigator.geolocation) {
            btn.classList.remove('locating');
            btn.innerHTML = '⊕';
            showToast('⚠️ 浏览器不支持定位功能');
            return;
          }

          navigator.geolocation.getCurrentPosition(
            function (pos) {
              btn.classList.remove('locating');
              btn.innerHTML = '⊕';
              const latLng = [pos.coords.latitude, pos.coords.longitude];
              map.setView(latLng, Math.max(map.getZoom(), 15), { animate: true });
              // 更新或创建位置标记
              if (!map._userMarker) {
                map._userMarker = L.circleMarker(latLng, {
                  radius: 8,
                  fillColor: '#3b82f6',
                  color: '#fff',
                  weight: 2,
                  fillOpacity: 0.9,
                }).addTo(map).bindTooltip('我的位置', { direction: 'top', offset: [0, -8] });
              } else {
                map._userMarker.setLatLng(latLng);
              }
              map._userMarker.openTooltip();
              showToast('📍 已定位到当前位置');
            },
            function (err) {
              btn.classList.remove('locating');
              btn.innerHTML = '⊕';
              const msgs = {
                1: '请允许浏览器获取位置信息',
                2: '无法获取位置信息',
                3: '获取位置超时',
              };
              showToast('⚠️ ' + (msgs[err.code] || '定位失败'));
            },
            { enableHighAccuracy: true, timeout: 8000, maximumAge: 300000 }
          );
        });

        return btn;
      },
    });
    map.addControl(new LocateControl());

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

  function createClusterIcon(stores) {
    const topStore = stores.slice().sort((a, b) => Number(b.rating || 0) - Number(a.rating || 0))[0];
    const color = CATEGORY_COLORS[topStore?.category] || '#ff6b35';
    const count = stores.length;
    const size = count >= 10 ? 52 : 46;

    return L.divIcon({
      className: 'cluster-marker',
      html: `
        <div class="cluster-bubble" style="--cluster-color:${color};width:${size}px;height:${size}px;">
          <span>${count}</span>
          <small>家</small>
        </div>
      `,
      iconSize: [size, size],
      iconAnchor: [size / 2, size / 2],
    });
  }

  function renderAllMarkers(stores) {
    const data = stores || state.allStoresCache;
    markersGroup.clearLayers();
    state.markers = [];
    state.markerClusters = {};

    const markerStores = data.filter(hasValidCoords);
    const markerItems = buildMarkerItems(markerStores);

    markerItems.forEach((item) => {
      if (item.type === 'cluster') {
        const marker = L.marker(item.latLng, {
          icon: createClusterIcon(item.stores),
          clusterId: item.id,
        });

        state.markerClusters[item.id] = item.stores;
        marker.on('click', () => openCluster(item.id));
        marker.bindTooltip(`该区域 ${item.stores.length} 家店`, {
          direction: 'top',
          offset: [0, -24],
          className: 'marker-tooltip',
          opacity: 0.9,
        });
        markersGroup.addLayer(marker);
        return;
      }

      const store = item.store;
      // 跳过没有有效坐标的店铺
      if (!hasValidCoords(store)) {
        return;
      }

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

    // 适配地图视野（仅在初始加载时）
    if (state.markers.length > 0 && !state._boundsFit) {
      state._boundsFit = true;
      map.fitBounds(markersGroup.getBounds().pad(0.1), { maxZoom: 14 });
    }
  }

  function updateVisibleMarkers() {
    refreshViewportStores();
  }

  function applyStoreResults(stores, options = {}) {
    state.baseFilteredStores = stores;
    if (options.fitBounds) {
      renderAllMarkers(stores);
      renderStoreList(stores);
      fitStoresBounds(stores, options.maxZoom || 14);
      return;
    }
    refreshViewportStores({ fallbackStores: stores });
  }

  function refreshViewportStores(options = {}) {
    const base = state.baseFilteredStores.length ? state.baseFilteredStores : state.allStoresCache;
    const visibleStores = filterStoresInMapBounds(base);
    const stores = map ? visibleStores : (options.fallbackStores || base);
    renderAllMarkers(stores);
    renderStoreList(stores);
  }

  function filterStoresInMapBounds(stores) {
    if (!map) return stores;
    const bounds = map.getBounds();
    return stores.filter((store) => hasValidCoords(store) && bounds.contains([Number(store.lat), Number(store.lng)]));
  }

  function buildMarkerItems(stores) {
    if (map.getZoom() >= 16 || stores.length <= 1) {
      return stores.map((store) => ({ type: 'store', store }));
    }

    const cellSize = getClusterCellSize(map.getZoom());
    const grouped = stores.reduce((acc, store) => {
      const key = `${Math.floor(Number(store.lat) / cellSize)}:${Math.floor(Number(store.lng) / cellSize)}`;
      if (!acc[key]) acc[key] = [];
      acc[key].push(store);
      return acc;
    }, {});

    let clusterIndex = 0;
    const items = [];
    Object.keys(grouped).forEach((key) => {
      const group = grouped[key];
      if (group.length === 1) {
        items.push({ type: 'store', store: group[0] });
        return;
      }

      const lat = group.reduce((sum, store) => sum + Number(store.lat), 0) / group.length;
      const lng = group.reduce((sum, store) => sum + Number(store.lng), 0) / group.length;
      items.push({
        type: 'cluster',
        id: `cluster-${clusterIndex++}`,
        stores: group,
        latLng: [lat, lng],
      });
    });
    return items;
  }

  function getClusterCellSize(zoom) {
    if (zoom <= 10) return 0.16;
    if (zoom <= 12) return 0.08;
    if (zoom <= 14) return 0.035;
    return 0.016;
  }

  function openCluster(clusterId) {
    const stores = state.markerClusters[clusterId] || [];
    fitStoresBounds(stores, 17);
    setSheetExpanded(false);
  }

  function fitStoresBounds(stores, maxZoom = 15) {
    const points = stores.filter(hasValidCoords).map((store) => [Number(store.lat), Number(store.lng)]);
    if (!points.length) return;
    if (points.length === 1) {
      map.flyTo(points[0], Math.min(Math.max(map.getZoom(), 15), maxZoom), { duration: 0.6 });
      return;
    }
    map.fitBounds(L.latLngBounds(points).pad(0.18), { maxZoom });
  }

  function hasValidCoords(store) {
    const lat = Number(store?.lat);
    const lng = Number(store?.lng);
    return Boolean(lat && lng && !(lat === 0 && lng === 0));
  }

  // ==================== 店铺高亮 ====================
  function highlightStore(storeId) {
    // 取消之前的高亮
    if (state.activeStoreId) {
      const prevStore = state.allStoresCache.find((s) => s.id === state.activeStoreId);
      if (prevStore) {
        const prevMarker = state.markers.find((m) => m.options.storeId === state.activeStoreId);
        if (prevMarker) {
          prevMarker.setIcon(createMarkerIcon(prevStore.category, false));
        }
      }
    }

    // 设置新高亮
    state.activeStoreId = storeId;
    const store = state.allStoresCache.find((s) => s.id === storeId);
    if (store) {
      const marker = state.markers.find((m) => m.options.storeId === storeId);
      if (marker) {
        marker.setIcon(createMarkerIcon(store.category, true));
        marker.setZIndexOffset(1000);
        // 飞行动画到该位置
        if (store.lat && store.lng && !(store.lat === 0 && store.lng === 0)) {
          map.flyTo([store.lat, store.lng], Math.max(map.getZoom(), 16), {
            duration: 0.8,
          });
        }
      } else if (store.lat && store.lng && !(store.lat === 0 && store.lng === 0)) {
        // 有坐标但没有marker（可能被过滤），直接飞行
        map.flyTo([store.lat, store.lng], Math.max(map.getZoom(), 16), {
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
  function getRatingView(rating) {
    const value = Number(rating || 0);
    if (!value) {
      return { text: '暂无评分', shortText: '-', className: 'rating-empty' };
    }

    const rounded = Math.min(Math.max(Math.round(value), 1), 5);
    const labels = {
      5: '强烈推荐',
      4: '推荐',
      3: '中规中矩',
      2: '谨慎',
      1: '避雷',
    };

    return {
      text: `${labels[rounded]} · ${value.toFixed(value % 1 ? 1 : 0)}/5`,
      shortText: labels[rounded],
      className: `rating-level-${rounded}`,
    };
  }

  function getVideoUrl(store) {
    if (store.source_video_url) return store.source_video_url;
    const bvid = store.source_video_bvid || store.platform_video_id;
    return bvid ? `https://www.bilibili.com/video/${bvid}` : '';
  }

  function openSourceVideo(storeId) {
    const store = state.allStoresCache.find((s) => s.id === storeId);
    if (!store) return;
    const url = getVideoUrl(store);
    if (!url) {
      showToast('暂无来源视频链接');
      return;
    }
    window.open(url, '_blank', 'noopener,noreferrer');
  }

  function openDetail(storeId) {
    const store = state.allStoresCache.find((s) => s.id === storeId);
    if (!store) return;
    setSheetExpanded(false);

    // 兼容新旧数据格式
    const bloggerName = store.blogger_name || store.bloggerName || '未知博主';
    let bloggerAvatar = store.blogger_avatar || '';
    // 修复 B站头像 URL（添加 https: 前缀）
    if (bloggerAvatar && bloggerAvatar.startsWith('//')) {
      bloggerAvatar = 'https:' + bloggerAvatar;
    }
    const visitDate = store.visitDate || store.created_at?.split('T')[0] || '';
    const tags = Array.isArray(store.tags) ? store.tags : [];
    const dishes = Array.isArray(store.recommend_dishes) ? store.recommend_dishes : [];
    const color = CATEGORY_COLORS[store.category] || '#ff6b35';
    const hasCoords = store.lat && store.lng && !(store.lat === 0 && store.lng === 0);
    const ratingView = getRatingView(store.rating);
    const sourceVideoUrl = getVideoUrl(store);
    const sourceVideoTitle = store.source_video_title || 'B站探店视频';

    dom.detailOverlay.innerHTML = `
      <div class="detail-header">
        <button class="detail-close" onclick="APP.closeDetail()">✕</button>
        <h2 class="detail-name">${store.name}</h2>
        <span class="detail-category" style="background:${color}20;color:${color};border:1px solid ${color}40">${store.category || '未知'}</span>
      </div>
      <div class="detail-body">
        <div class="detail-section">
          <h4>基本信息</h4>
          <div class="detail-info-grid">
            <div class="detail-info-item">
              <div class="info-label">评分</div>
              <div class="info-value rating-badge ${ratingView.className}">${ratingView.text}</div>
            </div>
            <div class="detail-info-item">
              <div class="info-label">💰 人均</div>
              <div class="info-value">${store.avg_price ? '¥' + store.avg_price : '-'}</div>
            </div>
            <div class="detail-info-item">
              <div class="info-label">📅 收录日期</div>
              <div class="info-value">${visitDate || '-'}</div>
            </div>
            <div class="detail-info-item">
              <div class="info-label">🤖 AI置信度</div>
              <div class="info-value">${store.confidence ? Math.round(store.confidence * 100) + '%' : '-'}</div>
            </div>
          </div>
        </div>

        <div class="detail-section">
          <h4>📍 地址</h4>
          <p class="detail-address">${store.address || '地址待补充'}</p>
          ${hasCoords ? `
            <button class="detail-locate-btn" onclick="APP.locateStore(${store.id})">
              🎯 定位到地图
            </button>
          ` : `<p style="font-size:12px;color:var(--text-muted);margin-top:8px;">⚠️ 该店铺暂无有效坐标，无法定位</p>`}
        </div>

        ${dishes.length ? `
        <div class="detail-section">
          <h4>🍽️ 推荐菜品</h4>
          <div class="detail-dishes">
            ${dishes.map((d) => `<span class="detail-dish">${d}</span>`).join('')}
          </div>
        </div>
        ` : ''}

        ${tags.length ? `
        <div class="detail-section">
          <h4>🏷️ 标签</h4>
          <div class="detail-dishes">
            ${tags.map((t) => `<span class="detail-dish">${t}</span>`).join('')}
          </div>
        </div>
        ` : ''}

        <div class="detail-section">
          <h4>🎥 探店来源</h4>
          <div class="detail-blogger">
            <div class="blogger-avatar">
              ${bloggerAvatar
                ? `<img src="${bloggerAvatar}" style="width:100%;height:100%;border-radius:50%;object-fit:cover;" onerror="this.style.display='none';this.parentElement.textContent='🎬'">`
                : '🎬'}
            </div>
            <div class="blogger-info">
              <div class="blogger-name">${bloggerName}</div>
              <div class="blogger-meta">${visitDate || ''} 探访</div>
            </div>
          </div>
          ${sourceVideoUrl ? `
            <div class="detail-source-video">
              <div class="source-video-title">${sourceVideoTitle}</div>
              <button class="source-video-btn" onclick="APP.openSourceVideo(${store.id})">直达 B 站视频</button>
            </div>
          ` : ''}
          ${store.note ? `<div class="detail-analysis-summary">${store.note}</div>` : ''}
          ${store.confidence ? `<div class="detail-confidence">AI 置信度: ${Math.round(store.confidence * 100)}%</div>` : ''}
        </div>
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
          <p style="font-size:12px;margin-top:6px;">试试调整筛选条件，或去<a href="/admin.html" style="color:var(--accent);">管理后台</a>添加数据</p>
        </div>
      `;
      return;
    }

    dom.sidebarContent.innerHTML = stores
      .map(
        (store) => {
          const storeTags = Array.isArray(store.tags) ? store.tags : [];
          const dishes = Array.isArray(store.recommend_dishes) ? store.recommend_dishes : [];
          const bloggerName = store.blogger_name || store.bloggerName || '未知';
          const dateStr = store.visitDate || (store.created_at || '').split('T')[0];
          const ratingView = getRatingView(store.rating);

          return `
      <div class="store-card${state.activeStoreId === store.id ? ' active' : ''}"
           data-store-id="${store.id}"
           onclick="APP.selectStore(${store.id})">
        <div class="card-header">
          <div class="store-name">${store.name}</div>
          <div class="store-rating rating-pill ${ratingView.className}">${ratingView.shortText}</div>
        </div>
        <div class="store-meta">
          <span>💰 ¥${store.avg_price || store.avgPrice || '-'}/人</span>
          <span>📅 ${dateStr || '-'}</span>
        </div>
        <div class="store-tags">
          ${storeTags.map((t) => `<span class="tag">${t}</span>`).join('')}
        </div>
        <div class="store-blogger">
          <span>🎥</span>
          <span>${bloggerName} 探访</span>
          ${store.confidence ? `<span style="margin-left:auto;font-size:10px;opacity:0.5">AI:${Math.round(store.confidence * 100)}%</span>` : ''}
        </div>
      </div>
    `;
        }
      )
      .join('');
  }

  function selectStore(storeId) {
    highlightStore(storeId);
    openDetail(storeId);
  }

  function locateStore(storeId) {
    // 关闭详情面板，飞行定位到店铺
    closeDetail();
    highlightStore(storeId);
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

  async function filterByCategory(category) {
    state.currentCategory = category;
    state.activeStoreId = null;

    // 更新按钮状态
    $$('.category-btn').forEach((btn) => {
      btn.classList.toggle('active', btn.dataset.category === category);
    });

    // 从API加载（服务端筛选）
    try {
      const stores = await API.getStores(category);
      // 本地再搜索过滤
      let filtered = stores;
      if (state.searchQuery) {
        filtered = filtered.filter((s) => matchSearch(s, state.searchQuery));
      }

      applyStoreResults(filtered, { fitBounds: true, maxZoom: 15 });
    } catch (err) {
      // 回退到本地筛选
      let filtered = state.allStoresCache;
      if (category !== 'all') {
        filtered = filtered.filter((s) => s.category === category);
      }
      if (state.searchQuery) {
        filtered = filtered.filter((s) => matchSearch(s, state.searchQuery));
      }
      applyStoreResults(filtered, { fitBounds: true, maxZoom: 15 });
    }
  }

  function updateCategoryCounts(stores) {
    $$('.category-btn .cat-count').forEach((el) => el.remove());
    const counts = {};
    stores.forEach((s) => {
      if (s.category) counts[s.category] = (counts[s.category] || 0) + 1;
    });
    $$('.category-btn').forEach((btn) => {
      const cat = btn.dataset.category;
      if (cat === 'all') return;
      const count = counts[cat] || 0;
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

    let filtered = state.allStoresCache;
    if (state.currentCategory !== 'all') {
      filtered = filtered.filter((s) => s.category === state.currentCategory);
    }
    if (state.searchQuery) {
      filtered = filtered.filter((s) => matchSearch(s, state.searchQuery));
    }

    applyStoreResults(filtered, { fitBounds: Boolean(state.searchQuery), maxZoom: 15 });
  }

  function matchSearch(store, query) {
    const tags = Array.isArray(store.tags) ? store.tags : [];
    const dishes = Array.isArray(store.recommend_dishes) ? store.recommend_dishes : [];
    const bloggerName = (store.blogger_name || store.bloggerName || '').toLowerCase();

    return (
      (store.name || '').toLowerCase().includes(query) ||
      (store.category || '').toLowerCase().includes(query) ||
      tags.some((t) => (t || '').toLowerCase().includes(query)) ||
      dishes.some((d) => (d || '').toLowerCase().includes(query)) ||
      bloggerName.includes(query) ||
      (store.address || '').toLowerCase().includes(query)
    );
  }

  // ==================== 侧边栏折叠 ====================
  function initSidebarToggle() {
    setSheetExpanded(state.sidebarVisible);
    dom.sidebarToggle.addEventListener('click', () => {
      setSheetExpanded(!state.sidebarVisible);
    });
  }

  function setSheetExpanded(expanded) {
    state.sidebarVisible = expanded;
    dom.sidebar.classList.toggle('collapsed', !expanded);
    dom.sidebarToggle.textContent = expanded ? '⌄' : '⌃';
    dom.sidebarToggle.title = expanded ? '收起店铺列表' : '展开店铺列表';
    dom.sidebarToggle.setAttribute('aria-label', dom.sidebarToggle.title);
  }

  // ==================== 详情关闭 ====================
  function initDetailClose() {
    // 使用事件委托，因为 detail-close 是动态创建的
    document.addEventListener('click', (e) => {
      if (e.target.closest('.detail-close') && state.detailOpen) {
        closeDetail();
      }
    });
    dom.detailBackdrop.addEventListener('click', closeDetail);

    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && state.detailOpen) {
        closeDetail();
      }
    });
  }

  // ==================== 统计信息 ====================
  function updateStatsLocal() {
    const stores = state.allStoresCache;
    const uniqueBloggers = new Set(stores.map((s) => s.source_blogger_id || s.bloggerId).filter(Boolean));
    const uniqueCategories = new Set(stores.map((s) => s.category).filter(Boolean));

    dom.statsTotal.textContent = stores.length;
    dom.statsBloggers.textContent = uniqueBloggers.size;
    dom.statsCategories.textContent = uniqueCategories.size;
  }

  // ==================== 加载状态 ====================
  function showLoading(show) {
    // 清除之前的自动超时定时器
    if (dom._loadingTimeout) {
      clearTimeout(dom._loadingTimeout);
      dom._loadingTimeout = null;
    }

    if (!dom.loadingOverlay && show) {
      dom.loadingOverlay = document.createElement('div');
      dom.loadingOverlay.className = 'loading-overlay';
      dom.loadingOverlay.innerHTML = `
        <div style="text-align:center;">
          <div class="loading-spinner"></div>
          <p style="margin-top:12px;color:var(--text-secondary);font-size:14px;">加载店铺数据...</p>
        </div>
      `;
      dom.loadingOverlay.style.cssText = `
        position:fixed;top:0;left:0;width:100%;height:100%;
        background:rgba(15,15,20,0.85);z-index:9999;
        display:flex;align-items:center;justify-content:center;
      `;
      document.body.appendChild(dom.loadingOverlay);

      // 安全阀：20 秒后自动隐藏，防止永久卡在 loading
      dom._loadingTimeout = setTimeout(() => {
        console.warn('Loading timeout — force hiding overlay');
        showLoading(false);
        showToast('⚠️ 加载超时，请检查后端服务是否正常');
      }, 20000);
    }

    if (dom.loadingOverlay && !show) {
      dom.loadingOverlay.style.opacity = '0';
      setTimeout(() => {
        if (dom.loadingOverlay) {
          dom.loadingOverlay.remove();
          dom.loadingOverlay = null;
        }
      }, 300);
    }
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
    locateStore,
    openSourceVideo,
    refreshData: loadData,
  };

  // ==================== 启动 ====================
  document.addEventListener('DOMContentLoaded', init);
})();
