function buildStoreListState(options) {
  const stores = options.stores || [];
  const viewportStores = options.viewportStores || [];
  const query = normalizeText(options.query || "");
  const category = options.category || "all";
  const blogger = options.blogger || "all";
  const searchActive = Boolean(query || blogger !== "all");
  const globalMatches = filterStores(stores, { query, category, blogger });
  const displayStores = searchActive ? globalMatches : viewportStores;

  return {
    searchActive,
    displayStores,
    globalMatches,
    title: getTitle(searchActive, displayStores.length),
    subtitle: searchActive ? "全局搜索结果，点击店铺后定位" : "当前地图区域内的探店记录",
    emptyText: searchActive ? "没有找到匹配的店铺" : "当前区域没有店铺"
  };
}

function filterStores(stores, filters) {
  const query = normalizeText(filters.query || "");
  const category = filters.category || "all";
  const blogger = filters.blogger || "all";

  return stores.filter(store => {
    if (category !== "all" && store.category !== category) return false;
    if (blogger !== "all" && store.blogger_name !== blogger) return false;
    if (query && !matchSearch(store, query)) return false;
    return true;
  });
}

function matchSearch(store, query) {
  const haystack = [
    store.name,
    store.category,
    store.address,
    store.blogger_name,
    store.sourceVideoTitle,
    store.source_video_title,
    ...(store.tags || []),
    ...(store.recommend_dishes || [])
  ].filter(Boolean).join(" ");
  return normalizeText(haystack).includes(normalizeText(query));
}

function buildBloggerOptions(stores) {
  const names = Array.from(new Set(
    stores.map(store => store.blogger_name).filter(Boolean)
  )).sort((a, b) => a.localeCompare(b, "zh-CN"));
  return [
    { name: "全部博主", value: "all" },
    ...names.map(name => ({ name, value: name }))
  ];
}

function normalizeText(value) {
  return String(value || "").trim().toLowerCase();
}

function getTitle(searchActive, count) {
  if (searchActive) return count ? `找到 ${count} 家好店` : "没有找到店铺";
  return count ? `发现 ${count} 家好店` : "当前区域没有店铺";
}

module.exports = {
  buildStoreListState,
  filterStores,
  matchSearch,
  buildBloggerOptions
};
