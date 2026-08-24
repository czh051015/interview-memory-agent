"use client";

import { useState, useRef, useEffect } from "react";
import { sendMessage } from "@/lib/api";
import type { ChatMessage } from "@/lib/types";

function MessageBubble({ msg }: { msg: ChatMessage }) {
  const isUser = msg.role === "user";

  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"} animate-fade-in-up`}>
      <div className="max-w-[80%]">
        {!isUser && (
          <div className="flex items-center gap-2 mb-1.5">
            <div className="w-6 h-6 rounded-full bg-indigo-100 flex items-center justify-center text-[10px] font-bold text-indigo-600">
              🧠
            </div>
            <span className="text-[11px] text-zinc-500 font-medium">OfferLoop · 面试错题本</span>
          </div>
        )}
        <div
          className={`rounded-2xl px-4 py-2.5 text-sm leading-relaxed whitespace-pre-wrap ${
            isUser
              ? "bg-indigo-600 text-white rounded-br-md"
              : "bg-white border border-zinc-200 rounded-bl-md shadow-sm"
          }`}
        >
          {msg.content}
        </div>
      </div>
    </div>
  );
}

function TypingIndicator() {
  return (
    <div className="flex justify-start animate-fade-in-up">
      <div className="max-w-[80%]">
        <div className="flex items-center gap-2 mb-1.5">
          <div className="w-6 h-6 rounded-full bg-indigo-100 flex items-center justify-center text-[10px] font-bold text-indigo-600">
            🧠
          </div>
          <span className="text-[11px] text-zinc-500 font-medium">OfferLoop · 面试错题本</span>
        </div>
        <div className="bg-white border border-zinc-200 rounded-2xl rounded-bl-md px-4 py-3 shadow-sm">
          <div className="flex gap-1.5">
            <span className="typing-dot w-2 h-2 bg-zinc-400 rounded-full inline-block" />
            <span className="typing-dot w-2 h-2 bg-zinc-400 rounded-full inline-block" />
            <span className="typing-dot w-2 h-2 bg-zinc-400 rounded-full inline-block" />
          </div>
        </div>
      </div>
    </div>
  );
}

const WELCOME = `我是 OfferLoop，一个「记得你」的面试错题本。

你可以直接用自然语言跟我说话：
· 「今天面了字节，被问了 RAG 混合检索，没答上」→ 记错题
· 「我该复习啥」→ 按遗忘状态提醒你
· 「看错题」→ 列出你栽过的题
· 「整理一下」→ 体检数据、查重复`;

export default function Home() {
  const [messages, setMessages] = useState<ChatMessage[]>([
    { role: "assistant", content: WELCOME },
  ]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  async function handleSend() {
    const text = input.trim();
    if (!text || loading) return;

    setInput("");
    setMessages((prev) => [...prev, { role: "user", content: text }]);
    setLoading(true);

    try {
      const space = localStorage.getItem("offerloop.space") || "default";
      const res = await sendMessage(text, space);
      setMessages((prev) => [...prev, { role: "assistant", content: res.reply }]);
    } catch (e: unknown) {
      const errMsg = e instanceof Error ? e.message : "请求失败";
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: `抱歉，处理时出了点问题：${errMsg}。请确认后端已启动（uvicorn app.main:app）。`,
        },
      ]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex flex-col h-dvh max-w-3xl mx-auto w-full bg-white shadow-sm border-x border-zinc-200">
      {/* Header */}
      <div className="flex items-center gap-3 px-5 py-3 border-b border-zinc-200 bg-white shrink-0">
        <div className="w-8 h-8 rounded-lg bg-indigo-600 flex items-center justify-center text-white text-sm font-bold">
          O
        </div>
        <div>
          <h1 className="text-sm font-semibold text-zinc-900">OfferLoop · 面试错题本</h1>
          <p className="text-[11px] text-zinc-500">记得你的面试错题本 Agent</p>
        </div>
        <div className="ml-auto flex items-center gap-2 text-[11px] text-zinc-400">
          <a
            href="/items"
            className="px-2.5 py-1 rounded-lg border border-zinc-200 text-zinc-500 hover:bg-zinc-50 hover:text-indigo-600 transition-colors"
          >
            错题本
          </a>
          <a
            href="/record"
            className="px-2.5 py-1 rounded-lg border border-zinc-200 text-zinc-500 hover:bg-zinc-50 hover:text-indigo-600 transition-colors"
          >
            ＋ 记错题
          </a>
          <a
            href="/mock-interview"
            className="px-2.5 py-1 rounded-lg border border-indigo-200 text-indigo-600 bg-indigo-50/60 hover:bg-indigo-100 transition-colors"
          >
            🎯 模拟面试
          </a>
          <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
          在线
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4 bg-zinc-50/50">
        {messages.map((msg, i) => (
          <MessageBubble key={i} msg={msg} />
        ))}
        {loading && <TypingIndicator />}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div className="border-t border-zinc-200 bg-white px-4 py-3 shrink-0">
        <div className="flex items-end gap-2">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                handleSend();
              }
            }}
            placeholder="说人话：记错题 / 看错题 / 我该复习啥..."
            rows={1}
            className="flex-1 resize-none rounded-xl border border-zinc-300 bg-zinc-50 px-4 py-2.5 text-sm outline-none focus:border-indigo-500 focus:bg-white focus:ring-1 focus:ring-indigo-500/20 transition-all"
            disabled={loading}
          />
          <button
            onClick={handleSend}
            disabled={loading || !input.trim()}
            className="shrink-0 h-10 w-10 rounded-xl bg-indigo-600 text-white flex items-center justify-center hover:bg-indigo-700 disabled:opacity-40 disabled:cursor-not-allowed transition-all active:scale-95"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 12h14M12 5l7 7-7 7" />
            </svg>
          </button>
        </div>
        <div className="mt-1.5 flex gap-3 text-[10px] text-zinc-400">
          <span>Enter 发送</span>
          <span>Shift+Enter 换行</span>
        </div>
      </div>
    </div>
  );
}
