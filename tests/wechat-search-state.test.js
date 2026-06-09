const assert = require("assert");
const { buildStoreListState } = require("../wechat-miniprogram/pages/index/search-state");

const stores = [
  { id: 1, name: "成都火锅", category: "火锅", blogger_name: "真探唐仁杰" },
  { id: 2, name: "武汉面馆", category: "面馆", blogger_name: "大祥哥" },
  { id: 3, name: "上海甜品", category: "甜品饮品", blogger_name: "真探唐仁杰" }
];

const viewportStores = [stores[0]];

{
  const state = buildStoreListState({
    stores,
    viewportStores,
    query: "",
    category: "all",
    blogger: "all"
  });
  assert.strictEqual(state.searchActive, false);
  assert.deepStrictEqual(state.displayStores.map(item => item.id), [1]);
}

{
  const state = buildStoreListState({
    stores,
    viewportStores,
    query: "武汉",
    category: "all",
    blogger: "all"
  });
  assert.strictEqual(state.searchActive, true);
  assert.deepStrictEqual(state.displayStores.map(item => item.id), [2]);
}

{
  const state = buildStoreListState({
    stores,
    viewportStores,
    query: "",
    category: "all",
    blogger: "真探唐仁杰"
  });
  assert.strictEqual(state.searchActive, true);
  assert.deepStrictEqual(state.displayStores.map(item => item.id), [1, 3]);
}

{
  const state = buildStoreListState({
    stores,
    viewportStores,
    query: "甜品",
    category: "甜品饮品",
    blogger: "真探唐仁杰"
  });
  assert.strictEqual(state.searchActive, true);
  assert.deepStrictEqual(state.displayStores.map(item => item.id), [3]);
}

console.log("wechat search-state tests passed");
