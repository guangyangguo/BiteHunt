const assert = require("assert");
const { buildOpenLocationPayload } = require("../wechat-miniprogram/pages/index/navigation");

{
  const payload = buildOpenLocationPayload({
    name: "测试火锅",
    address: "武汉市江汉区测试路 1 号",
    lat: 30.58,
    lng: 114.27
  });
  assert.deepStrictEqual(payload, {
    latitude: 30.58,
    longitude: 114.27,
    name: "测试火锅",
    address: "武汉市江汉区测试路 1 号",
    scale: 18
  });
}

{
  const payload = buildOpenLocationPayload({
    name: "",
    address: "",
    lat: "30.58",
    lng: "114.27"
  });
  assert.deepStrictEqual(payload, {
    latitude: 30.58,
    longitude: 114.27,
    name: "店铺位置",
    address: "",
    scale: 18
  });
}

console.log("wechat navigation tests passed");
