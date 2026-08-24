import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ArrowRight, Check, Loader2, LogOut, Menu, PanelLeftClose, Plus, Send, Sparkles, X } from "lucide-react";
import { createChat, createThread, devLogin, enhancePrompt, getAuthConfig, getConversation, getCurrentUser, getResponseThreads, getThread, googleSignInUrl, listConversations, logout, sendThreadMessage } from "./api";
import threadLogo from "./assets/thread-ai-logo.png";

const DEMO_QUESTION = "Explain how Convolutional Neural Networks work.";

function ThreadGlyph({ size = 14, className }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" className={className} aria-hidden="true">
      <path d="M2 13c3-7 6 7 9 0s6-7 9 0" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeDasharray="0.8 3.4" />
      <circle cx="20" cy="13" r="1.5" fill="currentColor" />
    </svg>
  );
}

function GoogleIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 18 18" aria-hidden="true">
      <path fill="currentColor" d="M17.64 9.2c0-.63-.06-1.24-.16-1.82H9v3.44h4.84a4.14 4.14 0 0 1-1.8 2.72v2.26c1.7-1.57 2.68-3.88 2.68-6.6z" />
      <path fill="currentColor" d="M9 18c2.43 0 4.47-.8 5.96-2.2l-2.92-2.26c-.8.54-1.84.86-3.04.86-2.34 0-4.32-1.58-5.03-3.7H.96v2.33A9 9 0 0 0 9 18z" />
      <path fill="currentColor" d="M3.97 10.7A5.4 5.4 0 0 1 3.69 9c0-.59.1-1.16.28-1.7V4.97H.96A9 9 0 0 0 0 9c0 1.45.35 2.82.96 4.03l3.01-2.33z" />
      <path fill="currentColor" d="M9 3.58c1.32 0 2.5.45 3.44 1.35l2.58-2.58A8.65 8.65 0 0 0 9 0 9 9 0 0 0 .96 4.97L3.97 7.3C4.68 5.16 6.66 3.58 9 3.58z" />
    </svg>
  );
}

function ThreadLogo({ className = "" }) {
  return <img className={`thread-logo-image ${className}`} src={threadLogo} alt="THREAD AI" />;
}

function getOffset(root, node, offset) {
  let total = 0;
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  let current;
  while ((current = walker.nextNode())) {
    if (current === node) return total + offset;
    total += current.textContent.length;
  }
  return total;
}

function paragraphize(text) {
  const paragraphs = [];
  let cursor = 0;
  for (const part of text.split(/(\n\s*\n+)/)) {
    if (/^\n\s*\n+$/.test(part)) {
      cursor += part.length;
      continue;
    }
    const leading = part.match(/^\s*/)?.[0].length || 0;
    const trimmed = part.trim();
    if (trimmed) paragraphs.push({ text: trimmed, start: cursor + leading });
    cursor += part.length;
  }
  return paragraphs;
}

function paragraphStarts(paragraphs) {
  let cursor = 0;
  return paragraphs.map((paragraph, index) => {
    const start = cursor;
    cursor += paragraph.length + (index < paragraphs.length - 1 ? 2 : 0);
    return start;
  });
}

function getContext(text, start, end) {
  const left = Math.max(0, start - 260);
  const right = Math.min(text.length, end + 260);
  return text.slice(left, right);
}

function buildSegments(paragraph, paragraphStart, threads) {
  const anchors = threads
    .map((thread) => ({
      ...thread,
      localStart: Math.max(0, thread.start_offset - paragraphStart),
      localEnd: Math.min(paragraph.length, thread.end_offset - paragraphStart),
    }))
    .filter((thread) => thread.localEnd > 0 && thread.localStart < paragraph.length && thread.localEnd > thread.localStart)
    .sort((a, b) => a.localStart - b.localStart);
  const segments = [];
  let cursor = 0;
  for (const anchor of anchors) {
    if (anchor.localStart > cursor) segments.push({ text: paragraph.slice(cursor, anchor.localStart), thread: null });
    segments.push({ text: paragraph.slice(anchor.localStart, anchor.localEnd), thread: anchor });
    cursor = Math.max(cursor, anchor.localEnd);
  }
  if (cursor < paragraph.length) segments.push({ text: paragraph.slice(cursor), thread: null });
  return segments;
}

function normalizeThread(raw) {
  return {
    id: raw.id,
    response_id: raw.response_id,
    selected_text: raw.selected_text,
    start_offset: raw.start_offset,
    end_offset: raw.end_offset,
    surrounding_context: raw.surrounding_context,
    messages: raw.messages || [],
  };
}

function mapConversationSummary(raw) {
  return {
    id: raw.id,
    title: raw.title,
    messages: [],
    loaded: false,
    created_at: raw.created_at,
    updated_at: raw.updated_at,
  };
}

function mapStoredConversation(raw) {
  const messages = [];
  for (const response of raw.responses || []) {
    messages.push({
      id: `${response.id}-user`,
      role: "user",
      content: response.user_query,
    });
    messages.push({
      id: response.id,
      role: "assistant",
      question: response.user_query,
      response_id: response.id,
      response_text: response.response_text,
      paragraphs: paragraphize(response.response_text),
      threads: (response.threads || []).map(normalizeThread),
    });
  }
  return {
    id: raw.id,
    title: raw.title,
    messages,
    loaded: true,
    created_at: raw.created_at,
    updated_at: raw.updated_at,
  };
}

function submittedInputValue(event, fallback) {
  return event.currentTarget.querySelector("input")?.value || fallback;
}

function formInputValueFromButton(event, fallback) {
  return event.currentTarget.closest("form")?.querySelector("input")?.value || fallback;
}

function submitOnEnter(event, submit) {
  if (event.key !== "Enter") return;
  event.preventDefault();
  submit(event.currentTarget.value);
}

function ChatApp({ user, onLogout }) {
  const [conversations, setConversations] = useState([]);
  const [activeConversationId, setActiveConversationId] = useState(null);
  const [inputValue, setInputValue] = useState(DEMO_QUESTION);
  const [promptEnhanced, setPromptEnhanced] = useState(false);
  const [loadingMain, setLoadingMain] = useState(false);
  const [enhancingPrompt, setEnhancingPrompt] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [popover, setPopover] = useState(null);
  const [panel, setPanel] = useState(null);
  const [panelInput, setPanelInput] = useState("");
  const [panelLoading, setPanelLoading] = useState(false);
  const [panelMinimized, setPanelMinimized] = useState(false);
  const [errorMsg, setErrorMsg] = useState(null);
  const [historyLoading, setHistoryLoading] = useState(false);

  const scrollRef = useRef(null);
  const markRefs = useRef({});
  const historyLoadedRef = useRef(false);

  const activeConversation = conversations.find((conversation) => conversation.id === activeConversationId);
  const activeThreadMessage = useMemo(
    () => activeConversation?.messages.find((message) => message.role === "assistant" && message.response_id === panel?.responseId),
    [activeConversation, panel?.responseId]
  );
  const activeThread = panel?.mode === "thread" ? activeThreadMessage?.threads.find((thread) => thread.id === panel.threadId) : null;

  function isBackendConversationId(id) {
    return Boolean(id && !id.startsWith("local-"));
  }

  function updateConversation(conversationId, updater) {
    setConversations((prev) => prev.map((conversation) => (conversation.id === conversationId ? updater(conversation) : conversation)));
  }

  function updateThreads(conversationId, responseId, updater) {
    updateConversation(conversationId, (conversation) => ({
      ...conversation,
      messages: conversation.messages.map((message) =>
        message.role === "assistant" && message.response_id === responseId ? { ...message, threads: updater(message.threads || []) } : message
      ),
    }));
  }

  async function refreshThreads(conversationId, responseId) {
    const rawThreads = await getResponseThreads(responseId);
    updateThreads(conversationId, responseId, () => rawThreads.map(normalizeThread));
  }

  const loadConversation = useCallback(async (conversationId) => {
    setHistoryLoading(true);
    setErrorMsg(null);
    try {
      const raw = await getConversation(conversationId);
      const mapped = mapStoredConversation(raw);
      setConversations((prev) => {
        const exists = prev.some((conversation) => conversation.id === conversationId);
        if (exists) return prev.map((conversation) => (conversation.id === conversationId ? mapped : conversation));
        return [mapped, ...prev];
      });
      setActiveConversationId(conversationId);
      setPanel(null);
      setPopover(null);
    } catch (error) {
      setErrorMsg(error.message || "THREAD AI could not load that conversation.");
    } finally {
      setHistoryLoading(false);
    }
  }, []);

  useEffect(() => {
    if (historyLoadedRef.current) return undefined;
    historyLoadedRef.current = true;
    let cancelled = false;
    async function loadHistory() {
      setHistoryLoading(true);
      try {
        const raw = await listConversations();
        if (cancelled) return;
        const summaries = raw.map(mapConversationSummary);
        setConversations((prev) => {
          const byId = new Map(prev.map((conversation) => [conversation.id, conversation]));
          const serverItems = summaries.map((summary) => {
            const existing = byId.get(summary.id);
            return existing?.loaded ? existing : { ...summary, messages: existing?.messages || [] };
          });
          const localItems = prev.filter((conversation) => conversation.id.startsWith("local-"));
          return [...localItems, ...serverItems];
        });
        if (!activeConversationId && summaries.length > 0) {
          await loadConversation(summaries[0].id);
        }
      } catch (error) {
        if (!cancelled) setErrorMsg(error.message || "THREAD AI could not load your history.");
      } finally {
        if (!cancelled) setHistoryLoading(false);
      }
    }
    loadHistory();
    return () => {
      cancelled = true;
    };
  }, [loadConversation]);

  useEffect(() => {
    function onMouseUp() {
      const selection = window.getSelection();
      if (!selection || selection.isCollapsed || selection.rangeCount === 0) return;
      const rawSelectedText = selection.toString();
      const selectedText = rawSelectedText.trim();
      if (selectedText.length < 2) return;
      const leadingTrim = rawSelectedText.length - rawSelectedText.trimStart().length;
      const trailingTrim = rawSelectedText.length - rawSelectedText.trimEnd().length;
      const range = selection.getRangeAt(0);
      const node = range.commonAncestorContainer;
      const el = node.nodeType === Node.TEXT_NODE ? node.parentElement : node;
      const responseEl = el?.closest("[data-response-id]");
      const paraEl = el?.closest("[data-paragraph-start]");
      if (!responseEl || !paraEl || !scrollRef.current?.contains(responseEl)) return;
      if (!responseEl.contains(range.startContainer) || !responseEl.contains(range.endContainer)) return;
      const paragraphStart = Number(paraEl.dataset.paragraphStart);
      const localStart = getOffset(paraEl, range.startContainer, range.startOffset);
      const localEnd = getOffset(paraEl, range.endContainer, range.endOffset);
      const startOffset = paragraphStart + localStart + leadingTrim;
      const endOffset = paragraphStart + localEnd - trailingTrim;
      if (endOffset <= startOffset) return;
      const message = activeConversation?.messages.find(
        (item) => item.role === "assistant" && item.response_id === responseEl.dataset.responseId
      );
      const responseText = message?.response_text || "";
      const rect = range.getBoundingClientRect();
      const existing = message?.threads.find(
        (thread) =>
          thread.response_id === responseEl.dataset.responseId &&
          thread.start_offset === startOffset &&
          thread.end_offset === endOffset &&
          thread.selected_text === selectedText
      );
      setPopover({
        responseId: responseEl.dataset.responseId,
        selectedText,
        startOffset,
        endOffset,
        surroundingContext: getContext(responseText, startOffset, endOffset),
        existingThreadId: existing?.id,
        x: rect.left + rect.width / 2,
        y: rect.top,
      });
    }
    function onMouseDown(event) {
      if (event.target.closest?.(".thread-popover")) return;
      setPopover(null);
    }
    document.addEventListener("mouseup", onMouseUp);
    document.addEventListener("mousedown", onMouseDown);
    return () => {
      document.removeEventListener("mouseup", onMouseUp);
      document.removeEventListener("mousedown", onMouseDown);
    };
  }, [activeConversation]);

  useEffect(() => {
    function onKey(event) {
      if (event.key === "Escape") {
        setPanel(null);
        setPopover(null);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  useEffect(() => {
    if (!panel || panel.mode !== "thread") return;
    const node = markRefs.current[panel.threadId];
    if (!node || !scrollRef.current) return;
    const observer = new IntersectionObserver(([entry]) => setPanelMinimized(!entry.isIntersecting), {
      root: scrollRef.current,
      threshold: 0.3,
    });
    observer.observe(node);
    return () => observer.disconnect();
  }, [panel]);

  const openThread = useCallback(async (threadId, responseId) => {
    setPanel({ mode: "thread", threadId, responseId });
    setPanelMinimized(false);
    setPopover(null);
    setPanelInput("");
    setErrorMsg(null);
    try {
      const raw = await getThread(threadId);
      setPanel({ mode: "thread", threadId, responseId: raw.response_id });
      updateThreads(activeConversationId, raw.response_id, (threads) =>
        threads.map((thread) => (thread.id === threadId ? normalizeThread(raw) : thread))
      );
    } catch (error) {
      setErrorMsg(error.message);
    }
  }, [activeConversationId]);

  function startDraft() {
    if (!popover) return;
    if (popover.existingThreadId) {
      openThread(popover.existingThreadId, popover.responseId);
      return;
    }
    setPanel({ mode: "draft", selection: popover });
    setPanelMinimized(false);
    setPopover(null);
    setPanelInput("");
    setErrorMsg(null);
  }

  async function sendMessage(question) {
    const cleaned = question.trim();
    if (!cleaned || loadingMain) return;
    const existingConversation = activeConversation;
    const localId = existingConversation?.id || `local-${Date.now()}`;
    const userMessage = { id: `${localId}-user-${Date.now()}`, role: "user", content: cleaned };
    if (existingConversation) {
      updateConversation(existingConversation.id, (conversation) => ({
        ...conversation,
        title: conversation.title === "New chat" ? cleaned.slice(0, 80) : conversation.title,
        messages: [...conversation.messages, userMessage],
      }));
    } else {
      setConversations((prev) => [{ id: localId, title: cleaned.slice(0, 80), messages: [userMessage], loaded: true }, ...prev]);
      setActiveConversationId(localId);
    }
    setInputValue("");
    setPromptEnhanced(false);
    setPanel(null);
    setLoadingMain(true);
    setErrorMsg(null);
    try {
      const response = await createChat(cleaned, isBackendConversationId(existingConversation?.id) ? existingConversation.id : undefined);
      updateConversation(localId, (conversation) => ({
        ...conversation,
        id: response.conversation_id,
        loaded: true,
        title: conversation.title === "New chat" ? response.user_query.slice(0, 80) : conversation.title,
        messages: [
          ...conversation.messages,
          {
            id: response.response_id,
            role: "assistant",
            question: response.user_query,
            response_id: response.response_id,
            response_text: response.response_text,
            paragraphs: paragraphize(response.response_text),
            threads: [],
          },
        ],
      }));
      setActiveConversationId(response.conversation_id);
      await refreshThreads(response.conversation_id, response.response_id);
    } catch (error) {
      setErrorMsg(error.message || "THREAD AI had trouble generating that answer.");
    } finally {
      setLoadingMain(false);
    }
  }

  async function enhanceCurrentPrompt(question) {
    const cleaned = question.trim();
    if (!cleaned || loadingMain || enhancingPrompt) return;
    setEnhancingPrompt(true);
    setErrorMsg(null);
    try {
      const result = await enhancePrompt(cleaned);
      setInputValue(result.enhanced_prompt || cleaned);
      setPromptEnhanced(Boolean(result.enhanced_prompt));
    } catch (error) {
      setErrorMsg(error.message || "THREAD AI could not enhance that prompt.");
    } finally {
      setEnhancingPrompt(false);
    }
  }

  async function submitDraft(question) {
    const selection = panel.selection;
    setPanelLoading(true);
    setErrorMsg(null);
    try {
      const result = await createThread({
        response_id: selection.responseId,
        selected_text: selection.selectedText,
        start_offset: selection.startOffset,
        end_offset: selection.endOffset,
        surrounding_context: selection.surroundingContext,
        question,
      });
      await refreshThreads(activeConversationId, selection.responseId);
      await openThread(result.thread_id, selection.responseId);
    } catch (error) {
      setErrorMsg(error.message || "THREAD AI had trouble answering.");
    } finally {
      setPanelLoading(false);
    }
  }

  async function submitFollowUp(question) {
    if (!activeThread) return;
    setPanelLoading(true);
    setErrorMsg(null);
    try {
      const result = await sendThreadMessage(activeThread.id, question);
      const raw = await getThread(result.thread_id);
      updateThreads(activeConversationId, raw.response_id, (threads) =>
        threads.map((thread) => (thread.id === result.thread_id ? normalizeThread(raw) : thread))
      );
    } catch (error) {
      setErrorMsg(error.message || "THREAD AI had trouble answering.");
    } finally {
      setPanelLoading(false);
    }
  }

  function handlePanelSubmit(event) {
    event.preventDefault();
    const question = panelInput.trim();
    if (!question || panelLoading) return;
    setPanelInput("");
    if (panel.mode === "draft") submitDraft(question);
    else submitFollowUp(question);
  }

  function newChat() {
    const id = `local-${Date.now()}`;
    setConversations((prev) => [{ id, title: "New chat", messages: [], loaded: true }, ...prev]);
    setActiveConversationId(id);
    setPanel(null);
    setPopover(null);
    setInputValue("");
    setPromptEnhanced(false);
    setErrorMsg(null);
  }

  const hasMessages = (activeConversation?.messages.length || 0) > 0;
  const panelOpen = Boolean(panel);
  const panelVisible = panelOpen && !panelMinimized;

  return (
    <div className="thread-app">
      <aside className={`thread-sidebar ${sidebarCollapsed ? "thread-sidebar-collapsed" : ""}`}>
        <div className="thread-sidebar-head">
          <div className="thread-logo"><ThreadLogo /></div>
          <button className="thread-icon-btn" onClick={() => setSidebarCollapsed(true)} title="Collapse sidebar"><PanelLeftClose size={16} /></button>
        </div>
        <button className="thread-new-chat" onClick={newChat}><Plus size={15} /> New chat</button>
        <div className="thread-sidebar-label">Recent</div>
        <div className="thread-sidebar-list">
          {historyLoading && conversations.length === 0 && <div className="thread-sidebar-empty">Loading history...</div>}
          {conversations.map((conversation) => (
            <button
              key={conversation.id}
              className={`thread-sidebar-item ${conversation.id === activeConversationId ? "thread-sidebar-item-active" : ""}`}
              onClick={() => {
                if (conversation.loaded || conversation.id.startsWith("local-")) {
                  setActiveConversationId(conversation.id);
                  setPanel(null);
                  setPopover(null);
                } else {
                  loadConversation(conversation.id);
                }
              }}
            >
              {conversation.title}
            </button>
          ))}
        </div>
        <div className="thread-sidebar-foot">
          <div className="thread-sidebar-avatar">{(user?.name || user?.email || "U").slice(0, 1).toUpperCase()}</div>
          <div className="thread-sidebar-foot-text">{user?.name || user?.email || "THREAD AI"}</div>
          <button className="thread-icon-btn thread-logout-btn" onClick={onLogout} title="Sign out"><LogOut size={15} /></button>
        </div>
      </aside>

      <main className={`thread-chat-col ${panelVisible ? "thread-panel-shifted" : ""}`}>
        <div className="thread-topbar">
          {sidebarCollapsed && <button className="thread-icon-btn" onClick={() => setSidebarCollapsed(false)} title="Show sidebar"><Menu size={17} /></button>}
          <span className="thread-topbar-title">{activeConversation?.title || "New chat"}</span>
        </div>

        {!hasMessages && !loadingMain ? (
          <div className="thread-empty">
            <ThreadLogo className="thread-logo-empty" />
            <h1 className="thread-empty-title">Ask where the doubt happens.</h1>
            <p className="thread-empty-sub">Highlight any word, sentence, or paragraph in an answer to open a conversation attached to it.</p>
            <form className={`thread-composer-empty ${promptEnhanced ? "thread-composer-enhanced" : ""}`} onSubmit={(event) => { event.preventDefault(); sendMessage(submittedInputValue(event, inputValue)); }}>
              <input
                className="thread-composer-input"
                value={inputValue}
                onChange={(event) => { setInputValue(event.target.value); setPromptEnhanced(false); }}
                onKeyDown={(event) => submitOnEnter(event, sendMessage)}
                placeholder="What would you like to understand?"
                autoFocus
              />
              <button
                type="button"
                className="thread-composer-tool"
                disabled={loadingMain || enhancingPrompt}
                title="Enhance prompt"
                onMouseDown={(event) => event.preventDefault()}
                onClick={(event) => enhanceCurrentPrompt(formInputValueFromButton(event, inputValue))}
              >
                {enhancingPrompt ? <Loader2 size={15} className="thread-spin" /> : <Sparkles size={15} />}
              </button>
              <button
                type="button"
                className="thread-composer-send"
                disabled={loadingMain || enhancingPrompt}
                onMouseDown={(event) => event.preventDefault()}
                onClick={(event) => sendMessage(formInputValueFromButton(event, inputValue))}
              >
                {loadingMain ? <Loader2 size={16} className="thread-spin" /> : "Ask"}
              </button>
            </form>
            {errorMsg && <div className="thread-error thread-empty-error">{errorMsg}</div>}
          </div>
        ) : (
          <>
            <div className="thread-chat-scroll" ref={scrollRef}>
              <div className="thread-chat-inner">
                {activeConversation?.messages.map((message) =>
                  message.role === "user" ? (
                    <div className="thread-msg-row thread-msg-row-user" key={message.id}><div className="thread-user-bubble">{message.content}</div></div>
                  ) : (
                    <div className="thread-msg-row" key={message.id}>
                      <div className="thread-assistant-block" data-response-id={message.response_id}>
                        <div className="thread-assistant-avatar"><ThreadGlyph size={13} /></div>
                        <div className="thread-assistant-content">
                          {message.paragraphs.map((paragraph, index) => {
                            return (
                            <p className="thread-paragraph" data-paragraph-start={paragraph.start} key={index}>
                              {buildSegments(paragraph.text, paragraph.start, message.threads).map((segment, segmentIndex) =>
                                segment.thread ? (
                                  <mark
                                    key={segmentIndex}
                                    ref={(el) => { if (el) markRefs.current[segment.thread.id] = el; }}
                                    className={`thread-mark ${panel?.threadId === segment.thread.id ? "thread-mark-active" : ""}`}
                                    onClick={() => openThread(segment.thread.id, message.response_id)}
                                  >
                                    {segment.text}<sup className="thread-badge"><ThreadGlyph size={9} />{Math.max(1, Math.ceil(segment.thread.messages.length / 2))}</sup>
                                  </mark>
                                ) : <React.Fragment key={segmentIndex}>{segment.text}</React.Fragment>
                              )}
                            </p>
                            );
                          })}
                        </div>
                      </div>
                    </div>
                  )
                )}
                {loadingMain && <div className="thread-msg-row"><div className="thread-assistant-block"><div className="thread-assistant-avatar"><ThreadGlyph size={13} /></div><div className="thread-shimmer-block">{[92, 85, 96, 70].map((w, i) => <div className="thread-shimmer-line" style={{ width: `${w}%` }} key={i} />)}</div></div></div>}
                {errorMsg && !panelOpen && <div className="thread-error">{errorMsg}</div>}
              </div>
            </div>
            <div className="thread-composer-wrap">
              <form className={`thread-composer ${promptEnhanced ? "thread-composer-enhanced" : ""}`} onSubmit={(event) => { event.preventDefault(); sendMessage(submittedInputValue(event, inputValue)); }}>
                <input
                  className="thread-composer-input"
                  placeholder="Ask a new question..."
                  value={inputValue}
                  onChange={(event) => { setInputValue(event.target.value); setPromptEnhanced(false); }}
                  onKeyDown={(event) => submitOnEnter(event, sendMessage)}
                />
                <button
                  type="button"
                  className="thread-composer-tool"
                  disabled={loadingMain || enhancingPrompt}
                  title="Enhance prompt"
                  onMouseDown={(event) => event.preventDefault()}
                  onClick={(event) => enhanceCurrentPrompt(formInputValueFromButton(event, inputValue))}
                >
                  {enhancingPrompt ? <Loader2 size={15} className="thread-spin" /> : <Sparkles size={15} />}
                </button>
                <button
                  type="button"
                  className="thread-composer-send"
                  disabled={loadingMain || enhancingPrompt}
                  onMouseDown={(event) => event.preventDefault()}
                  onClick={(event) => sendMessage(formInputValueFromButton(event, inputValue))}
                >
                  {loadingMain ? <Loader2 size={16} className="thread-spin" /> : <Send size={15} />}
                </button>
              </form>
              <p className="thread-hint">Highlight text above to open a thread on it.</p>
            </div>
          </>
        )}
      </main>

      {popover && (
        <div className="thread-popover" style={{ left: popover.x, top: popover.y }}>
          <button className="thread-popover-btn" onClick={startDraft}><ThreadGlyph size={13} /> {popover.existingThreadId ? "Open Thread" : "Ask Thread AI"}</button>
        </div>
      )}

      <aside className={`thread-panel ${panelOpen ? "thread-panel-open" : ""}`}>
        {panelVisible && panel && (
          <>
            <div className="thread-panel-header">
              <div className="thread-panel-heading"><ThreadGlyph size={13} /> Thread</div>
              <button className="thread-panel-close" onClick={() => setPanel(null)}><X size={16} /></button>
            </div>
            <div className="thread-panel-selected">
              <span className="thread-panel-label">Selected text</span>
              <p className="thread-panel-quote">&quot;{panel.mode === "draft" ? panel.selection.selectedText : activeThread?.selected_text}&quot;</p>
            </div>
            <div className="thread-panel-messages">
              {panel.mode === "thread" && activeThread?.messages.map((message) => (
                <div key={message.id} className={message.role === "user" ? "thread-msg thread-msg-user" : "thread-msg thread-msg-ai"}>{message.content}</div>
              ))}
              {panel.mode === "draft" && <p className="thread-panel-help">Ask a question about the highlighted text. This becomes a thread anchored to that exact spot.</p>}
              {panelLoading && <div className="thread-msg thread-msg-ai thread-loading"><span /><span /><span /></div>}
            </div>
            {errorMsg && <div className="thread-error">{errorMsg}</div>}
            <form className="thread-panel-input-row" onSubmit={handlePanelSubmit}>
              <input className="thread-panel-input" placeholder={panel.mode === "draft" ? "What would you like to understand?" : "Ask a follow-up..."} value={panelInput} onChange={(event) => setPanelInput(event.target.value)} autoFocus />
              <button type="submit" className="thread-panel-send" disabled={panelLoading}><Send size={15} /></button>
            </form>
          </>
        )}
        {panelOpen && panelMinimized && (
          <button className="thread-panel-mini" onClick={() => setPanelMinimized(false)}>
            <ThreadGlyph size={12} /> Continue thread - &quot;{(activeThread?.selected_text || "").slice(0, 28)}{(activeThread?.selected_text || "").length > 28 ? "..." : ""}&quot;
          </button>
        )}
      </aside>
    </div>
  );
}

function WelcomePage({ user, authError, googleConfigured, devAuthEnabled, onContinue, onDevLogin }) {
  const [emailOpen, setEmailOpen] = useState(false);
  const [email, setEmail] = useState("");
  const [emailLoading, setEmailLoading] = useState(false);

  function startGoogle() {
    if (!googleConfigured) return;
    window.location.href = googleSignInUrl();
  }

  async function submitEmail(event) {
    event.preventDefault();
    setEmailLoading(true);
    if (googleConfigured) {
      startGoogle();
      return;
    }
    await onDevLogin();
    setEmailLoading(false);
  }

  return (
    <main className="thread-auth-page">
      <section className="thread-auth-demo" aria-label="THREAD AI product demonstration">
        <div className="thread-auth-brand"><ThreadLogo /></div>
        <div className="thread-auth-copy">
          <ThreadLogo className="thread-logo-hero" />
          <p className="thread-auth-tagline">Ask where the doubt happens.</p>
          <p className="thread-auth-sub">Highlight any part of an AI answer and start a conversation exactly there.</p>
        </div>

        <div className="thread-demo-stage">
          <div className="thread-demo-answer">
            <span className="thread-demo-label">Question</span>
            <h2>How do neural networks learn?</h2>
            <p>Neural networks learn by <mark>adjusting internal parameters called weights</mark>.</p>
            <p>During training, predictions are compared with the expected result, and the network gradually reduces the error.</p>
            <button className="thread-demo-ask" type="button"><ThreadGlyph size={14} /> Ask Thread</button>
          </div>
          <div className="thread-demo-panel">
            <div className="thread-demo-panel-head">Thread on: <strong>adjusting internal parameters called weights</strong></div>
            <div className="thread-demo-message thread-demo-user">What exactly are weights?</div>
            <div className="thread-demo-message thread-demo-ai">Weights are numerical values that determine how strongly one part of the network influences the next.</div>
          </div>
        </div>

        <div className="thread-prompt-demo" aria-label="THREAD AI prompt enhancer demonstration">
          <div className="thread-prompt-demo-head">
            <Sparkles size={16} />
            <span>Prompt enhancer</span>
          </div>
          <div className="thread-prompt-demo-grid">
            <div className="thread-prompt-rough">
              <span>Your question</span>
              <p>cnn filter how work explain simple</p>
            </div>
            <button className="thread-prompt-enhance" type="button"><Sparkles size={15} /> Enhance</button>
            <div className="thread-prompt-enhanced">
              <span>Enhanced by THREAD <strong>AI</strong></span>
              <p>Explain how filters work in a CNN in simple terms. Use a visual example if possible.</p>
            </div>
          </div>
        </div>

        <div className="thread-auth-differentiators">
          <div><strong>ASK IN CONTEXT</strong><span>Ask directly about the exact part you do not understand.</span></div>
          <div><strong>THREADS THAT STAY</strong><span>Your discussion remains attached to the original text.</span></div>
          <div><strong>ASK NATURALLY</strong><span>Write what you mean. THREAD AI can help refine your question.</span></div>
        </div>
      </section>

      <aside className="thread-auth-card" aria-label="Sign in">
        <div className="thread-auth-card-brand"><ThreadLogo /></div>
        <h2><span>Welcome to</span><ThreadLogo className="thread-logo-title" /></h2>
        <p>Think freely. Ask precisely.</p>
        {authError && <div className="thread-auth-notice">{authError}</div>}
        {user ? (
          <button className="thread-auth-primary" type="button" onClick={onContinue}>
            Continue to THREAD AI <ArrowRight size={16} />
          </button>
        ) : (
          <>
            {googleConfigured ? (
              <button className="thread-auth-primary thread-auth-google" type="button" onClick={startGoogle}>
                <GoogleIcon /> Continue with Google
              </button>
            ) : (
              <button className="thread-auth-primary" type="button" onClick={onDevLogin} disabled={!devAuthEnabled}>
                Continue to local preview <ArrowRight size={16} />
              </button>
            )}
            {!googleConfigured && <div className="thread-auth-notice">Google OAuth is not connected yet. Local preview keeps the app usable while you add Google credentials.</div>}
            <button className="thread-auth-secondary" type="button" onClick={() => setEmailOpen((value) => !value)}>
              Continue with email
            </button>
            {emailOpen && (
              <form className="thread-auth-email" onSubmit={submitEmail}>
                <label htmlFor="thread-email">Email</label>
                <input id="thread-email" value={email} onChange={(event) => setEmail(event.target.value)} placeholder="you@example.com" type="email" />
                <button className="thread-auth-secondary" type="submit" disabled={emailLoading || !email.trim()}>
                  {emailLoading ? <Loader2 className="thread-spin" size={14} /> : <ArrowRight size={14} />} Continue
                </button>
                <p>Email sign-in will use Google verification until a dedicated email provider is connected.</p>
              </form>
            )}
          </>
        )}
        <p className="thread-auth-legal">
          By continuing, you agree to the <a href="/terms">Terms</a> and <a href="/privacy">Privacy Policy</a>.
        </p>
        <div className="thread-auth-checks">
          <span><Check size={14} /> Contextual threads</span>
          <span><Check size={14} /> Prompt enhancer</span>
          <span><Check size={14} /> Private workspace</span>
        </div>
      </aside>
    </main>
  );
}

function LegalPage({ type, onBack }) {
  const title = type === "privacy" ? "Privacy Policy" : "Terms";
  return (
    <main className="thread-legal-page">
      <div className="thread-legal-shell">
        <div className="thread-auth-card-brand"><ThreadLogo /></div>
        <h1>{title}</h1>
        <p>THREAD AI is an early product prototype. This placeholder should be replaced with a reviewed legal document before public launch.</p>
        <p>Authentication data is used to keep each user&apos;s conversations and contextual threads separate. API keys and OAuth secrets belong only in server environment variables.</p>
        <button className="thread-auth-secondary" type="button" onClick={onBack}>Back to sign in</button>
      </div>
    </main>
  );
}

export default function App() {
  const [user, setUser] = useState(null);
  const [authLoading, setAuthLoading] = useState(true);
  const [googleConfigured, setGoogleConfigured] = useState(false);
  const [devAuthEnabled, setDevAuthEnabled] = useState(false);
  const [path, setPath] = useState(window.location.pathname);
  const [authError, setAuthError] = useState(null);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const error = params.get("auth_error");
    if (error) {
      setAuthError("Google sign-in could not be completed. Please try again.");
      window.history.replaceState({}, "", "/");
      setPath("/");
    }
  }, []);

  useEffect(() => {
    function onPopState() {
      setPath(window.location.pathname);
    }
    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
  }, []);

  useEffect(() => {
    let cancelled = false;
    async function loadUser() {
      try {
        const config = await getAuthConfig().catch(() => ({ google_configured: false }));
        if (!cancelled) setGoogleConfigured(Boolean(config.google_configured));
        if (!cancelled) setDevAuthEnabled(Boolean(config.dev_auth_enabled));
        const result = await getCurrentUser();
        if (!cancelled) setUser(result.user);
      } catch {
        if (!cancelled) setUser(null);
      } finally {
        if (!cancelled) setAuthLoading(false);
      }
    }
    loadUser();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (authLoading) return;
    if (path === "/app") {
      window.history.replaceState({}, "", "/");
      setPath("/");
    }
  }, [authLoading, path, user]);

  function navigate(nextPath) {
    window.history.pushState({}, "", nextPath);
    setPath(nextPath);
  }

  async function handleLogout() {
    await logout().catch(() => {});
    setUser(null);
    navigate("/");
  }

  async function handleDevLogin() {
    setAuthError(null);
    try {
      const result = await devLogin();
      setUser(result.user);
      navigate("/");
    } catch (error) {
      setAuthError(error.message || "Local preview sign-in is not available.");
    }
  }

  if (authLoading) {
    return <div className="thread-auth-loading"><ThreadLogo className="thread-logo-image-loading" /></div>;
  }

  if (path === "/privacy") return <LegalPage type="privacy" onBack={() => navigate("/")} />;
  if (path === "/terms") return <LegalPage type="terms" onBack={() => navigate("/")} />;
  if (user) return <ChatApp user={user} onLogout={handleLogout} />;
  return (
    <WelcomePage
      user={user}
      authError={authError}
      googleConfigured={googleConfigured}
      devAuthEnabled={devAuthEnabled}
      onContinue={() => navigate("/")}
      onDevLogin={handleDevLogin}
    />
  );
}
