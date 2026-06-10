const {
  createInitialMessages,
  appendUserMessage,
  appendGuideLoading,
  appendAssistantDelta,
  finishLastAssistant,
  replaceLastAssistant,
  updateLastAssistantMeta
} = require("./chat-state");
const api = require("../../utils/api");
const { buildOpenLocationPayload } = require("../index/navigation");

const SUGGESTIONS = [
  "附近有什么不踩雷的店？",
  "按博主推荐帮我找火锅",
  "两个人 100 元以内吃什么？",
  "适合外地游客的路线"
];

Page({
  data: {
    messages: createInitialMessages(),
    suggestions: SUGGESTIONS,
    inputValue: "",
    scrollIntoView: "",
    sending: false,
    selectedStore: null,
    detailOpen: false
  },

  onInput(event) {
    this.setData({ inputValue: event.detail.value || "" });
  },

  onSuggestionTap(event) {
    const text = event.currentTarget.dataset.text || "";
    this.sendMessage(text);
  },

  onSendTap() {
    if (this.data.sending) {
      this.stopCurrentResponse();
      return;
    }
    this.sendMessage(this.data.inputValue);
  },

  async sendMessage(content) {
    if (this.data.sending) return;
    const before = this.data.messages;
    const withUser = appendUserMessage(before, content);
    if (withUser === before) return;

    const messages = appendGuideLoading(withUser);
    this.setData({
      messages,
      inputValue: "",
      sending: true,
      scrollIntoView: messages[messages.length - 1].id
    });

    const location = await this.getLocationIfNeeded(withUser);
    this.startStreamRequest(toApiMessages(withUser), location);
  },

  startStreamRequest(messages, location) {
    let finished = false;
    const streamId = `${Date.now()}-${Math.random()}`;
    this.activeStreamId = streamId;
    this.currentRequestTask = api.guideChatStream(messages, location, {
      onEvent: event => {
        if (!event || finished || this.activeStreamId !== streamId) return;
        if (event.type === "meta") {
          this.updateStreamingMessage({
            recommendations: event.recommendations || [],
            followUp: event.follow_up || event.followUp || ""
          });
          return;
        }
        if (event.type === "delta") {
          this.appendStreamingText(event.content || "");
          return;
        }
        if (event.type === "error") {
          finished = true;
          this.finishStreamingMessage(`这次没能完成推荐：${event.error || "服务异常"}`);
          return;
        }
        if (event.type === "done") {
          finished = true;
          this.finishStreamingMessage();
        }
      },
      onError: err => {
        if (finished || this.activeStreamId !== streamId) return;
        finished = true;
        this.finishStreamingMessage(`这次没能完成推荐：${err.message || "网络请求失败"}。`);
      },
      onAbort: () => {
        if (this.activeStreamId !== streamId) return;
        finished = true;
        this.finishStreamingMessage("", { aborted: true });
      },
      onComplete: () => {
        if (this.activeStreamId === streamId) {
          this.currentRequestTask = null;
        }
      }
    });
  },

  appendStreamingText(delta) {
    const updated = appendAssistantDelta(this.data.messages, delta);
    this.setData({
      messages: updated,
      scrollIntoView: updated[updated.length - 1].id
    });
  },

  updateStreamingMessage(payload) {
    const updated = updateLastAssistantMeta(this.data.messages, payload);
    this.setData({
      messages: updated,
      scrollIntoView: updated[updated.length - 1].id
    });
  },

  finishStreamingMessage(fallbackContent = "", options = {}) {
    let updated = this.data.messages;
    if (fallbackContent) {
      updated = replaceLastAssistant(updated, { content: fallbackContent });
    }
    updated = finishLastAssistant(updated, options);
    this.setData({
      messages: updated,
      sending: false,
      scrollIntoView: updated[updated.length - 1].id
    });
  },

  stopCurrentResponse() {
    this.activeStreamId = "";
    if (this.currentRequestTask && this.currentRequestTask.abort) {
      this.currentRequestTask.abort();
    }
    this.currentRequestTask = null;
    this.finishStreamingMessage("", { aborted: true });
  },

  getLocationIfNeeded(messages) {
    const text = (messages || []).map(item => item.content || "").join(" ");
    if (!/附近|周边|离我|当前位置/.test(text)) {
      return Promise.resolve(null);
    }
    return new Promise(resolve => {
      wx.getLocation({
        type: "gcj02",
        success: res => resolve({ lat: res.latitude, lng: res.longitude }),
        fail: () => resolve(null)
      });
    });
  },

  openStore(event) {
    const id = Number(event.currentTarget.dataset.id);
    if (!id) return;
    const store = findRecommendationById(this.data.messages, id);
    if (!store) return;
    this.setData({
      selectedStore: normalizeDetailStore(store),
      detailOpen: true
    });
  },

  closeDetail() {
    this.setData({ detailOpen: false });
  },

  navigateToStore() {
    const store = this.data.selectedStore;
    if (!store || !store.hasCoords) return;
    wx.openLocation({
      ...buildOpenLocationPayload(store),
      fail: () => {}
    });
  },

  focusSelectedStore() {
    const store = this.data.selectedStore;
    if (!store || !store.id) return;
    wx.setStorageSync("pendingStoreId", store.id);
    wx.setStorageSync("pendingStoreFocus", true);
    wx.switchTab({ url: "/pages/index/index" });
  },

  copySourceVideo() {
    const store = this.data.selectedStore;
    if (!store || !store.sourceVideoUrl) return;
    wx.setClipboardData({ data: store.sourceVideoUrl });
  }
});

function toApiMessages(messages) {
  return (messages || [])
    .filter(item => item && item.role && item.content && !item.loading)
    .map(item => ({ role: item.role, content: item.content }))
    .slice(-10);
}

function findRecommendationById(messages, id) {
  for (const message of messages || []) {
    for (const store of message.recommendations || []) {
      if (Number(store.id) === id) return store;
    }
  }
  return null;
}

function normalizeDetailStore(store) {
  const rating = Number(store.rating || 0);
  return {
    ...store,
    rating,
    lat: Number(store.lat || 0),
    lng: Number(store.lng || 0),
    hasCoords: Boolean(Number(store.lat || 0) && Number(store.lng || 0)),
    ratingLabel: getRatingLabel(rating),
    ratingClass: rating ? `level-${Math.min(Math.max(Math.round(rating), 1), 5)}` : "empty",
    recommend_dishes: Array.isArray(store.recommend_dishes) ? store.recommend_dishes : [],
    tags: Array.isArray(store.tags) ? store.tags : [],
    sourceVideoUrl: store.source_video_url || "",
    sourceVideoTitle: store.source_video_title || "B站探店视频"
  };
}

function getRatingLabel(rating) {
  const value = Number(rating || 0);
  if (!value) return "暂无评分";
  const rounded = Math.min(Math.max(Math.round(value), 1), 5);
  const labels = {
    5: "强烈推荐",
    4: "推荐",
    3: "中规中矩",
    2: "谨慎",
    1: "避雷"
  };
  return `${labels[rounded]} · ${value.toFixed(value % 1 ? 1 : 0)}/5`;
}
