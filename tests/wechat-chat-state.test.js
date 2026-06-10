const assert = require("assert");
const {
  createInitialMessages,
  appendUserMessage,
  appendGuideLoading,
  appendAssistantDelta,
  finishLastAssistant,
  replaceLastAssistant,
  updateLastAssistantMeta
} = require("../wechat-miniprogram/pages/chat/chat-state");

{
  const messages = createInitialMessages();
  assert.strictEqual(messages.length, 1);
  assert.strictEqual(messages[0].role, "assistant");
}

{
  const messages = appendUserMessage(createInitialMessages(), " 武汉有什么火锅推荐 ");
  assert.strictEqual(messages.length, 2);
  assert.strictEqual(messages[1].role, "user");
  assert.strictEqual(messages[1].content, "武汉有什么火锅推荐");
}

{
  const messages = appendGuideLoading(
    appendUserMessage(createInitialMessages(), "附近适合两个人吃的店")
  );
  assert.strictEqual(messages.length, 3);
  assert.strictEqual(messages[2].role, "assistant");
  assert.strictEqual(messages[2].loading, true);
  assert.strictEqual(messages[2].thinking, true);
  assert.strictEqual(messages[2].content, "");
}

{
  const messages = appendGuideLoading(
    appendUserMessage(createInitialMessages(), "附近适合两个人吃的店")
  );
  const updated = replaceLastAssistant(messages, {
    content: "给你挑了 2 家",
    recommendations: [{ id: 1, name: "测试店" }]
  });
  assert.strictEqual(updated[2].loading, false);
  assert.strictEqual(updated[2].content, "给你挑了 2 家");
  assert.strictEqual(updated[2].recommendations.length, 1);
  assert.strictEqual(updated[2].recommendationsReady, true);
}

{
  const messages = appendGuideLoading(
    appendUserMessage(createInitialMessages(), "附近适合两个人吃的店")
  );
  const streamed = appendAssistantDelta(messages, "我推荐");
  assert.strictEqual(streamed[2].thinking, false);
  assert.strictEqual(streamed[2].content, "我推荐");
  const finished = finishLastAssistant(streamed);
  assert.strictEqual(finished[2].loading, false);
}

{
  const messages = appendGuideLoading(
    appendUserMessage(createInitialMessages(), "附近适合两个人吃的店")
  );
  const withMeta = updateLastAssistantMeta(messages, {
    recommendations: [{ id: 1, name: "测试店" }]
  });
  assert.strictEqual(withMeta[2].recommendations.length, 1);
  assert.strictEqual(withMeta[2].recommendationsReady, false);
  const finished = finishLastAssistant(withMeta);
  assert.strictEqual(finished[2].recommendationsReady, true);
  const aborted = finishLastAssistant(withMeta, { aborted: true });
  assert.strictEqual(aborted[2].recommendationsReady, false);
}

console.log("wechat chat-state tests passed");
