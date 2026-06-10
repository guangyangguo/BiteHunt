function buildOpenLocationPayload(store) {
  return {
    latitude: Number(store.lat),
    longitude: Number(store.lng),
    name: store.name || "店铺位置",
    address: store.address || "",
    scale: 18
  };
}

module.exports = {
  buildOpenLocationPayload
};
