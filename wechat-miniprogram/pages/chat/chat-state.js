function createInitialMessages() {
  return [
    {
      id: "welcome",
      role: "assistant",
      content: "我是你的探店智能向导。你可以告诉我城市、预算、菜系、是否想找附近，我会基于真实探店视频分析结果推荐。"
    }
  ];
}

function appendUserMessage(messages, content) {
  const text = String(content || "").trim();
  if (!text) return messages;
  return [
    ...messages,
    {
      id: `user-${Date.now()}`,
      role: "user",
      content: text
    }
  ];
}

function appendGuideLoading(messages) {
  return [
    ...messages,
    {
      id: `assistant-${Date.now()}`,
      role: "assistant",
      content: "",
      loading: true,
      thinking: true,
      recommendations: [],
      recommendationsReady: false
    }
  ];
}

function replaceLastAssistant(messages, payload) {
  const next = messages.slice();
  for (let i = next.length - 1; i >= 0; i--) {
    if (next[i].role === "assistant") {
      next[i] = {
        ...next[i],
        loading: false,
        thinking: false,
        content: payload.content || next[i].content,
        recommendations: payload.recommendations || [],
        recommendationsReady: Boolean(payload.recommendations && payload.recommendations.length),
        followUp: payload.followUp || ""
      };
      return next;
    }
  }
  return messages;
}

function appendAssistantDelta(messages, delta) {
  if (!delta) return messages;
  const next = messages.slice();
  for (let i = next.length - 1; i >= 0; i--) {
    if (next[i].role === "assistant") {
      next[i] = {
        ...next[i],
        thinking: false,
        content: `${next[i].content || ""}${delta}`
      };
      return next;
    }
  }
  return messages;
}

function updateLastAssistantMeta(messages, payload) {
  const next = messages.slice();
  for (let i = next.length - 1; i >= 0; i--) {
    if (next[i].role === "assistant") {
      next[i] = {
        ...next[i],
        recommendations: payload.recommendations || next[i].recommendations || [],
        recommendationsReady: false,
        followUp: payload.followUp || next[i].followUp || ""
      };
      return next;
    }
  }
  return messages;
}

function finishLastAssistant(messages, options = {}) {
  const next = messages.slice();
  for (let i = next.length - 1; i >= 0; i--) {
    if (next[i].role === "assistant") {
      const content = next[i].content || (options.aborted ? "已停止生成。" : "");
      next[i] = {
        ...next[i],
        loading: false,
        thinking: false,
        recommendationsReady: !options.aborted && Boolean((next[i].recommendations || []).length),
        content
      };
      return next;
    }
  }
  return messages;
}

module.exports = {
  createInitialMessages,
  appendUserMessage,
  appendGuideLoading,
  replaceLastAssistant,
  appendAssistantDelta,
  updateLastAssistantMeta,
  finishLastAssistant
};
