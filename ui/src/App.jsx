import React, { useState, useRef, useEffect } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Send,
  Brain,
  Database,
  Search,
  Layers,
  Terminal,
  User,
  Cpu,
  Sparkles,
  Loader2,
  MessageSquare,
  Zap,
  Sun,
  Moon,
  ChevronRight,
  ShoppingCart,
  CheckCircle2,
  ExternalLink,
  Plus
} from 'lucide-react';

const API_BASE = "http://localhost:8000/api/chat";
const IS_MOCK_MODE = false;

const MOCK_RESPONSE = {
  answer: "Chào bạn! Với nhu cầu tìm kiếm một chiếc smartphone cao cấp của Apple để chụp ảnh đẹp, mình xin đề xuất bộ đôi **iPhone 15 Pro** và **iPhone 15 Pro Max**.\n\nĐây là những lựa chọn hàng đầu hiện nay với hệ thống camera chuyên nghiệp và chip A17 Pro mạnh mẽ. Ngoài ra, để tối ưu trải nghiệm hệ sinh thái iOS, bạn có thể cân nhắc thêm tai nghe **AirPods Pro (2nd Gen)** đang có giá cực tốt. \n\nDưới đây là chi tiết các sản phẩm mình tìm thấy cho bạn:",
  extraction_log: {
    is_small_talk: false,
    brand: "Apple",
    category: ["phone", "headphone"],
    os_type: "ios",
    max_price: 35000000,
    semantic_intent: "chụp ảnh đẹp, chuyên nghiệp",
    trigger_cross_sell: true
  },
  retrieval_log: {
    status: "Success",
    queries: [
      { type: "Graph Search", cypher: "MATCH (p:Product)-[:HAS_SPEC]->(s:Spec)\nWHERE p.brand = 'Apple' AND p.category = 'phone' AND s.price < 35000000\nRETURN p, s LIMIT 5" },
      { type: "Cross-sell Logic", cypher: "MATCH (p:Product {brand: 'Apple'})-[:WORKS_WITH]->(acc:Product)\nWHERE acc.category = 'headphone'\nRETURN acc LIMIT 1" }
    ],
    qdrant: { hit_count: 12, top_score: 0.92 }
  },
  products: [
    {
      product_id: "iPhone 15 Pro",
      brand: "Apple",
      category: "phone",
      price: 28990000,
      specs: "A17 Pro, 6.1\" OLED, 48MP Triple Camera",
      final_score: 0.945,
      is_cross_sell: false,
      url: "https://www.apple.com/vn/iphone-15-pro/"
    },
    {
      product_id: "iPhone 15 Pro Max",
      brand: "Apple",
      category: "phone",
      price: 34490000,
      specs: "A17 Pro, 6.7\" OLED, 5x Optical Zoom",
      final_score: 0.921,
      is_cross_sell: false,
      url: "https://www.apple.com/vn/iphone-15-pro/"
    },
    {
      product_id: "AirPods Pro (2nd Gen)",
      brand: "Apple",
      category: "headphone",
      price: 5990000,
      specs: "H2 Chip, Active Noise Cancellation",
      final_score: 0.880,
      is_cross_sell: true,
      url: "https://www.apple.com/vn/airpods-pro/"
    }
  ],
  latency_ms: 2450.5
};

// --- SUB-COMPONENTS ---

const CypherHighlighter = ({ code }) => {
  if (!code) return null;
  const keywords = /\b(MATCH|WHERE|RETURN|LIMIT|AND|OR|WITH|AS|CREATE|MERGE)\b/g;
  const parts = code.split(keywords);

  return (
    <pre className="p-3 rounded-lg bg-slate-100 dark:bg-black/50 text-xs font-mono leading-relaxed border border-slate-200 dark:border-zinc-800 overflow-x-auto whitespace-pre-wrap">
      {parts.map((part, i) => (
        keywords.test(part) ?
          <span key={i} className="text-indigo-600 dark:text-indigo-400 font-bold">{part}</span> :
          <span key={i} className="text-emerald-700 dark:text-emerald-400/80">{part}</span>
      ))}
    </pre>
  );
};

const ProductCard = ({ product }) => {
  const shopeeUrl = `https://shopee.vn/search?keyword=${encodeURIComponent(product.product_id)}`;

  // Giải quyết giá tiền từ specs nếu không có ở root
  let rawPrice = product.price;
  if (rawPrice === undefined && product.specs && product.specs.price) {
    rawPrice = product.specs.price;
  }
  let numericPrice = parseFloat(String(rawPrice).replace(/[^0-9.]/g, '')) || 0;

  // Giá trị trong cơ sở dữ liệu đã được quy đổi sang VND tại bước Ingestion.
  // Chúng ta hiển thị trực tiếp, phòng thủ nhân tỉ giá chỉ khi phát hiện số quá nhỏ.
  if (numericPrice > 0 && numericPrice < 200000) {
    if (numericPrice < 10000) {
      numericPrice = Math.round(numericPrice * 25000);
    } else {
      if (product.category === 'phone' || product.category === 'headphone') {
        numericPrice = Math.round(numericPrice * 300);
      } else {
        numericPrice = Math.round(numericPrice * 1000);
      }
    }
  }

  const priceString = numericPrice > 0
    ? Math.round(numericPrice).toLocaleString('vi-VN') + ' đ'
    : 'Liên hệ';

  // Giải quyết thông tin specs
  let specsText = "";
  if (typeof product.specs === 'string') {
    specsText = product.specs;
  } else if (product.specs && typeof product.specs === 'object') {
    const excludeKeys = ['price', 'id', 'popularity', 'overall_rating', 'model_name', 'brand', 'category', 'os', 'specs'];
    const parts = Object.entries(product.specs)
      .filter(([k]) => !excludeKeys.includes(k.toLowerCase()))
      .map(([k, v]) => `${k}: ${v}`);

    if (product.specs.specs) {
      parts.unshift(product.specs.specs);
    }
    specsText = parts.join(', ');
  }
  if (!specsText) {
    specsText = "Không có cấu hình chi tiết";
  }

  const scoreVal = product.final_score !== undefined ? product.final_score : 0.85;

  return (
    <motion.div
      whileHover={{ y: -4, scale: 1.02 }}
      className={`p-5 rounded-2xl border flex flex-col gap-4 transition-all shadow-sm hover:shadow-md ${product.is_cross_sell
        ? 'bg-indigo-50 border-indigo-200 dark:bg-indigo-500/5 dark:border-indigo-500/30'
        : 'bg-white border-slate-200 dark:bg-zinc-900 dark:border-zinc-800 hover:border-slate-300 dark:hover:border-zinc-700'
        }`}
    >
      <div className="flex justify-between items-start">
        <div className="flex flex-col gap-1.5">
          <span className={`text-[11px] font-black uppercase tracking-widest px-2.5 py-1 rounded-full w-fit ${product.is_cross_sell ? 'bg-indigo-100 text-indigo-600 dark:bg-indigo-500/20 dark:text-indigo-300' : 'bg-slate-100 text-slate-500 dark:bg-zinc-800 dark:text-zinc-400'
            }`}>
            {product.category}
          </span>
          <h3 className="text-base font-bold text-slate-900 dark:text-zinc-100">{product.product_id}</h3>
        </div>
        <div className="p-2.5 rounded-xl bg-slate-50 dark:bg-zinc-800/50">
          <ShoppingCart size={16} className="text-slate-400 dark:text-zinc-500" />
        </div>
      </div>

      <div className="space-y-2">
        <div className="text-sm text-slate-500 dark:text-zinc-400 leading-relaxed font-medium">{specsText}</div>
        <div className="text-xl font-black text-emerald-600 dark:text-emerald-400">
          {priceString}
        </div>
      </div>

      <div className="pt-3 border-t border-slate-100 dark:border-zinc-800/50 flex items-center justify-between text-xs">
        <span className="text-slate-400 dark:text-zinc-500 font-medium">Độ tương quan:</span>
        <span className="text-slate-600 dark:text-zinc-300 font-bold font-mono">{(scoreVal * 100).toFixed(1)}%</span>
      </div>

      <button
        onClick={() => window.open(shopeeUrl, '_blank')}
        className="mt-1 w-full py-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-bold transition-colors flex items-center justify-center gap-2 shadow-sm"
      >
        Xem trên Shopee <ExternalLink size={14} />
      </button>
    </motion.div>
  );
};

const SuggestionChip = ({ text, onClick }) => (
  <button
    onClick={() => onClick(text)}
    className="px-5 py-2.5 rounded-full border border-slate-200 bg-white dark:border-zinc-800 dark:bg-zinc-900/50 hover:bg-slate-50 dark:hover:bg-zinc-800 hover:border-slate-300 dark:hover:border-zinc-700 text-sm text-slate-600 dark:text-zinc-400 transition-all flex items-center gap-2.5 whitespace-nowrap shadow-sm"
  >
    <MessageSquare size={16} className="text-indigo-500" />
    {text}
  </button>
);

// --- MAIN APP ---

export default function App() {
  const [messages, setMessages] = useState(() => {
    const saved = localStorage.getItem('chatHistory');
    return saved ? JSON.parse(saved) : [];
  });
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [thinkingData, setThinkingData] = useState(null);
  const [isDark, setIsDark] = useState(() => localStorage.getItem('theme') !== 'light');
  const scrollRef = useRef(null);

  useEffect(() => {
    localStorage.setItem('chatHistory', JSON.stringify(messages));
  }, [messages]);

  useEffect(() => {
    if (isDark) {
      document.documentElement.classList.add('dark');
      localStorage.setItem('theme', 'dark');
    } else {
      document.documentElement.classList.remove('dark');
      localStorage.setItem('theme', 'light');
    }
  }, [isDark]);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages]);

  const handleSend = async (queryText) => {
    const text = typeof queryText === 'string' ? queryText : input;
    if (!text.trim() || isLoading) return;

    const userMsg = { role: 'user', content: text };
    setMessages(prev => [...prev, userMsg]);
    setIsLoading(true);
    setInput("");
    setThinkingData(null);

    if (IS_MOCK_MODE) {
      await new Promise(r => setTimeout(r, 2000));

      const isGreeting = ['xin chào', 'hello', 'hi', 'chào'].some(g => text.toLowerCase().includes(g));

      if (isGreeting) {
        const MOCK_GREETING = {
          answer: "Chào bạn! Mình là trợ lý mua sắm đồ điện tử cao cấp. Mình có thể giúp gì cho bạn hôm nay?",
          extraction_log: {
            is_small_talk: true,
            brand: null,
            category: [],
            os_type: null,
            max_price: null,
            semantic_intent: null,
            trigger_cross_sell: false
          },
          retrieval_log: {
            status: "Phát hiện câu hỏi giao tiếp - Tối ưu hóa bằng cách bỏ qua truy vấn Database",
            queries: [],
            qdrant: { hit_count: 0 }
          },
          products: [],
          latency_ms: 150.2
        };

        setMessages(prev => [...prev, {
          role: 'assistant',
          content: MOCK_GREETING.answer,
          products: []
        }]);
        setThinkingData({
          intent: MOCK_GREETING.extraction_log,
          retrieval: MOCK_GREETING.retrieval_log,
          products: [],
          latency: MOCK_GREETING.latency_ms
        });
      } else {
        let currentMockResponse = JSON.parse(JSON.stringify(MOCK_RESPONSE));

        // Mock Price Sync logic
        const priceMatch = text.match(/(\d+)\s*(triệu|tr|m)/i);
        if (priceMatch) {
          const extractedPrice = parseInt(priceMatch[1]) * 1000000;
          currentMockResponse.extraction_log.max_price = extractedPrice;
        }

        setMessages(prev => [...prev, {
          role: 'assistant',
          content: currentMockResponse.answer,
          products: currentMockResponse.products
        }]);
        setThinkingData({
          intent: currentMockResponse.extraction_log,
          retrieval: currentMockResponse.retrieval_log,
          products: currentMockResponse.products,
          latency: currentMockResponse.latency_ms
        });
      }
      setIsLoading(false);
      return;
    }

    try {
      const response = await fetch(API_BASE, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          query: text,
          history: messages.slice(-10)
        }),
      });
      if (!response.ok) throw new Error("API Connection Failed");
      const data = await response.json();
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: data.answer,
        products: data.products
      }]);
      setThinkingData({
        intent: data.extraction_log,
        retrieval: data.retrieval_log,
        products: data.products,
        latency: data.latency_ms
      });
    } catch (error) {
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: "❌ **Lỗi kết nối Backend.** Hãy đảm bảo Server đang chạy."
      }]);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="flex h-screen bg-white dark:bg-zinc-950 text-slate-900 dark:text-zinc-100 font-sans overflow-hidden transition-colors duration-300">

      {/* LEFT PANE: Chat Interface */}
      <div className="flex-1 flex flex-col min-w-0 border-r border-slate-100 dark:border-zinc-900">

        {/* Header */}
        <header className="h-16 flex items-center justify-between px-6 border-b border-slate-100 dark:border-zinc-900 bg-white/80 dark:bg-zinc-950/80 backdrop-blur-md z-10">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-indigo-600 flex items-center justify-center shadow-lg shadow-indigo-500/20">
              <Zap className="w-6 h-6 text-white fill-current" />
            </div>
            <div>
              <h1 className="text-sm font-black tracking-tight uppercase">Agentic RAG Assistant</h1>
              <div className="flex items-center gap-1.5 text-[10px] text-slate-500 dark:text-zinc-500 font-bold uppercase tracking-wider">
                <div className={`w-1.5 h-1.5 rounded-full ${IS_MOCK_MODE ? 'bg-amber-500' : 'bg-emerald-500'} animate-pulse`} />
                {IS_MOCK_MODE ? "Mock Mode" : "Real Backend"}
              </div>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <button
              onClick={() => {
                if (window.confirm("Bạn có chắc muốn bắt đầu cuộc trò chuyện mới?")) {
                  setMessages([]);
                  setThinkingData(null);
                  localStorage.removeItem('chatHistory');
                }
              }}
              className="px-4 py-2 rounded-xl bg-slate-100 dark:bg-zinc-900 text-slate-600 dark:text-zinc-400 hover:bg-slate-200 dark:hover:bg-zinc-800 transition-all border border-slate-200 dark:border-zinc-800 shadow-sm flex items-center gap-2 text-sm font-bold"
            >
              <Plus size={16} /> Mới
            </button>
            <button
              onClick={() => setIsDark(!isDark)}
              className="p-2.5 rounded-xl bg-slate-100 dark:bg-zinc-900 text-slate-600 dark:text-zinc-400 hover:bg-slate-200 dark:hover:bg-zinc-800 transition-all border border-slate-200 dark:border-zinc-800 shadow-sm"
            >
              {isDark ? <Sun size={20} /> : <Moon size={20} />}
            </button>
          </div>
        </header>

        {/* Chat Content */}
        <main className="flex-1 overflow-y-auto p-6 space-y-10 scroll-smooth" ref={scrollRef}>

          {messages.length === 0 && (
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              className="h-full flex flex-col items-center justify-center max-w-2xl mx-auto space-y-10 text-center"
            >
              <div className="relative">
                <div className="absolute -inset-6 bg-indigo-500/20 rounded-full blur-3xl animate-pulse" />
                <div className="relative p-6 rounded-3xl bg-slate-50 dark:bg-zinc-900 border border-slate-100 dark:border-zinc-800 shadow-inner">
                  <Brain className="w-16 h-16 text-indigo-600 dark:text-indigo-400" />
                </div>
              </div>
              <div className="space-y-4">
                <h2 className="text-4xl font-black tracking-tight text-slate-900 dark:text-zinc-100 leading-tight">
                  Tôi có thể giúp bạn <br /> tìm mua gì hôm nay?
                </h2>
                <p className="text-slate-500 dark:text-zinc-400 text-base leading-relaxed px-12 font-medium">
                  Trợ lý tư vấn mua sắm cao cấp. Am hiểu iPhone, Laptop, Tai nghe và hệ sinh thái đồ công nghệ.
                </p>
              </div>
              <div className="flex flex-wrap items-center justify-center gap-3">
                <SuggestionChip text="Tìm iPhone 15 Pro dưới 30tr" onClick={handleSend} />
                <SuggestionChip text="Laptop Dell tầm 15tr cho sinh viên" onClick={handleSend} />
                <SuggestionChip text="Tai nghe Sony chống ồn tốt nhất" onClick={handleSend} />
              </div>
            </motion.div>
          )}

          <AnimatePresence>
            {messages.map((msg, idx) => (
              <motion.div
                key={idx}
                initial={{ opacity: 0, scale: 0.98, y: 20 }}
                animate={{ opacity: 1, scale: 1, y: 0 }}
                className={`flex gap-5 ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
              >
                {msg.role === 'assistant' && (
                  <div className="w-10 h-10 rounded-xl bg-indigo-600/10 border border-indigo-500/20 flex items-center justify-center flex-shrink-0 shadow-sm">
                    <Cpu size={20} className="text-indigo-600 dark:text-indigo-400" />
                  </div>
                )}

                <div className="flex flex-col gap-4 max-w-[85%]">
                  <div className={`px-6 py-5 rounded-3xl shadow-sm ${msg.role === 'user'
                    ? 'bg-indigo-600 text-white rounded-tr-none shadow-indigo-500/20'
                    : 'bg-white dark:bg-zinc-950 border border-slate-100 dark:border-zinc-900 text-slate-800 dark:text-zinc-200 rounded-tl-none'
                    }`}>
                    <div className="prose dark:prose-invert prose-slate max-w-none text-base leading-relaxed font-normal">
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>
                        {msg.content}
                      </ReactMarkdown>
                    </div>
                  </div>

                  {msg.products && msg.products.length > 0 && (
                    <motion.div
                      key={`products-${idx}`}
                      initial={{ opacity: 0, y: 15 }}
                      animate={{ opacity: 1, y: 0 }}
                      className="space-y-3 mt-2"
                    >
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        {msg.products.map((p, pIdx) => (
                          <ProductCard key={pIdx} product={p} />
                        ))}
                      </div>
                      <p className="text-xs text-slate-400 dark:text-zinc-500 italic font-normal pl-1">
                        * Giá bán dựa trên dữ liệu của tôi, bạn hãy kiểm tra lại giá của sản phẩm ở thời điểm hiện tại một lần nữa để đảm bảo độ chính xác
                      </p>
                    </motion.div>
                  )}
                </div>

                {msg.role === 'user' && (
                  <div className="w-10 h-10 rounded-xl bg-slate-100 dark:bg-zinc-800 border border-slate-200 dark:border-zinc-700 flex items-center justify-center flex-shrink-0 shadow-sm">
                    <User size={20} className="text-slate-400 dark:text-zinc-500" />
                  </div>
                )}
              </motion.div>
            ))}
          </AnimatePresence>

          {isLoading && (
            <div className="flex justify-start gap-5">
              <div className="w-10 h-10 rounded-xl bg-indigo-50 dark:bg-zinc-900 border border-indigo-100 dark:border-zinc-800 flex items-center justify-center">
                <Loader2 className="w-5 h-5 animate-spin text-indigo-500" />
              </div>
              <div className="flex items-center gap-3 px-5 py-3 bg-white dark:bg-zinc-950 border border-slate-100 dark:border-zinc-900 rounded-2xl shadow-sm">
                <span className="text-sm text-slate-400 dark:text-zinc-500 font-bold uppercase tracking-wider animate-pulse italic">Thinking...</span>
              </div>
            </div>
          )}
        </main>

        {/* Input Area */}
        <footer className="p-6 bg-white dark:bg-zinc-950 border-t border-slate-100 dark:border-zinc-900 transition-colors">
          <form
            onSubmit={(e) => { e.preventDefault(); handleSend(); }}
            className="relative max-w-4xl mx-auto group"
          >
            <div className="absolute -inset-1 bg-gradient-to-r from-indigo-500 to-purple-500 rounded-3xl blur opacity-10 group-focus-within:opacity-20 transition-opacity" />
            <div className="relative bg-slate-50 dark:bg-zinc-900 border border-slate-200 dark:border-zinc-800 rounded-3xl flex items-center p-2.5 focus-within:border-indigo-300 dark:focus-within:border-zinc-700 focus-within:bg-white dark:focus-within:bg-zinc-900 transition-all shadow-sm">
              <input
                type="text"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder="Tìm sản phẩm, so sánh cấu hình..."
                className="flex-1 bg-transparent border-none py-3 px-5 focus:ring-0 text-base placeholder:text-slate-400 dark:placeholder:text-zinc-600 text-slate-900 dark:text-zinc-100"
                disabled={isLoading}
              />
              <button
                type="submit"
                disabled={isLoading || !input.trim()}
                className="p-4 bg-indigo-600 hover:bg-indigo-700 disabled:bg-slate-200 dark:disabled:bg-zinc-800 disabled:text-slate-400 dark:disabled:text-zinc-700 text-white rounded-2xl transition-all shadow-lg active:scale-95"
              >
                {isLoading ? <Loader2 size={20} className="animate-spin" /> : <Send size={20} />}
              </button>
            </div>
          </form>
        </footer>
      </div>

      {/* RIGHT PANE: Thinking Space (Timeline) */}
      <div className="w-[440px] flex flex-col bg-slate-50/50 dark:bg-zinc-950/80 backdrop-blur-xl transition-colors">
        <header className="h-16 flex items-center justify-between px-6 border-b border-slate-100 dark:border-zinc-900">
          <div className="flex items-center gap-3">
            <Terminal size={18} className="text-indigo-600 dark:text-indigo-400" />
            <h2 className="text-[11px] font-black uppercase tracking-[0.25em] text-slate-400 dark:text-zinc-500">System Logs</h2>
          </div>
          {thinkingData && (
            <span className="text-[11px] font-bold bg-white dark:bg-zinc-900 text-slate-500 dark:text-zinc-500 px-3 py-1.5 rounded-lg border border-slate-200 dark:border-zinc-800 shadow-sm">
              {thinkingData.latency.toFixed(0)}ms
            </span>
          )}
        </header>

        <div className="flex-1 overflow-y-auto p-8 space-y-10">
          <AnimatePresence mode="wait">
            {!thinkingData && (
              <motion.div
                key="empty"
                initial={{ opacity: 0 }} animate={{ opacity: 1 }}
                className="h-full flex flex-col items-center justify-center text-center space-y-6"
              >
                <div className="p-10 rounded-3xl border-2 border-dashed border-slate-200 dark:border-zinc-900 bg-white/30 dark:bg-zinc-900/10">
                  <Cpu size={56} className="mx-auto text-slate-200 dark:text-zinc-900 mb-6" />
                  <p className="text-xs font-black tracking-widest uppercase text-slate-400 dark:text-zinc-800 mb-2">Monitor Inactive</p>
                  <p className="text-sm text-slate-300 dark:text-zinc-800 font-medium">Quy trình Agentic RAG sẽ <br /> được hiển thị tại đây</p>
                </div>
              </motion.div>
            )}

            {thinkingData && (
              <div className="space-y-10 relative">
                <div className="absolute left-6 top-2 bottom-2 w-px bg-slate-200 dark:bg-zinc-900" />

                {/* STEP 1: Intent */}
                <ThinkingStep
                  title="Step 1: Intent Analysis"
                  icon={<Search size={16} className="text-blue-500" />}
                  delay={0.2}
                >
                  <div className="flex flex-wrap gap-2.5">
                    <Tag label="Brand" value={thinkingData.intent?.brand} color="indigo" />
                    <Tag label="OS" value={thinkingData.intent?.os_type} color="blue" />
                    <Tag label="Price" value={thinkingData.intent?.max_price ? `${(thinkingData.intent.max_price / 1000000).toFixed(1)}M` : null} color="emerald" />
                    {thinkingData.intent?.category?.map((c, i) => (
                      <Tag key={i} label="Cat" value={c} color="purple" />
                    ))}
                  </div>
                  {thinkingData.intent?.semantic_intent && (
                    <div className="mt-4 p-3 rounded-xl bg-white dark:bg-zinc-900/80 border border-slate-100 dark:border-zinc-800 text-xs text-slate-500 dark:text-zinc-400 font-medium leading-relaxed">
                      <span className="text-indigo-500 font-bold mr-2 tracking-wide uppercase text-[10px]">Cảm nhận:</span>
                      {thinkingData.intent.semantic_intent}
                    </div>
                  )}
                </ThinkingStep>

                {/* STEP 2: Database Retrieval */}
                <ThinkingStep
                  title="Step 2: Knowledge Retrieval"
                  icon={<Database size={16} className="text-emerald-500" />}
                  delay={0.6}
                >
                  <div className="space-y-5">
                    {thinkingData.retrieval?.queries?.map((q, idx) => (
                      <div key={idx} className="space-y-2">
                        <div className="flex items-center justify-between text-[10px] font-black text-slate-400 dark:text-zinc-600 uppercase tracking-wider">
                          <span>{q.type}</span>
                          <span className="text-indigo-500/60 font-mono">NEO4J_DB</span>
                        </div>
                        <CypherHighlighter code={q.cypher} />
                      </div>
                    ))}
                  </div>
                </ThinkingStep>

                {/* STEP 3: Reranking */}
                <ThinkingStep
                  title="Step 3: Synthesis & Rerank"
                  icon={<Layers size={16} className="text-amber-500" />}
                  delay={1.0}
                >
                  <div className="p-5 rounded-2xl bg-white dark:bg-zinc-950 border border-slate-100 dark:border-zinc-900 space-y-4 shadow-sm transition-all hover:border-slate-200">
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-semibold text-slate-500 dark:text-zinc-500">Qdrant Review Hits</span>
                      <span className="text-sm font-black text-amber-600 dark:text-amber-500">{thinkingData.retrieval?.qdrant?.hit_count ?? 0}</span>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-semibold text-slate-500 dark:text-zinc-500">Candidate Pool</span>
                      <span className="text-sm font-black text-slate-900 dark:text-zinc-200">{(thinkingData.products?.length ?? 0)} SP</span>
                    </div>

                    <div className="pt-4 border-t border-slate-50 dark:border-zinc-900 mt-2 flex items-center justify-center">
                      <div className="flex items-center gap-2 text-emerald-600 dark:text-emerald-400 text-xs font-black uppercase tracking-widest">
                        <CheckCircle2 size={16} />
                        Validated & Ready
                      </div>
                    </div>
                  </div>
                </ThinkingStep>
              </div>
            )}
          </AnimatePresence>
        </div>
      </div>
    </div>
  );
}

function ThinkingStep({ title, icon, children, delay }) {
  return (
    <motion.div
      initial={{ opacity: 0, x: 20 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ duration: 0.6, delay }}
      className="relative pl-12"
    >
      <div className="absolute left-4 top-1 w-5 h-5 rounded-full bg-white dark:bg-zinc-950 border-2 border-indigo-500 flex items-center justify-center z-10 shadow-lg dark:shadow-indigo-500/20">
        <div className="w-1.5 h-1.5 rounded-full bg-indigo-500" />
      </div>
      <div className="space-y-4">
        <div className="flex items-center gap-2.5 text-slate-900 dark:text-zinc-100">
          <div className="p-1.5 rounded-lg bg-slate-100 dark:bg-zinc-900 shadow-inner">
            {icon}
          </div>
          <h3 className="text-xs font-black uppercase tracking-[0.15em]">{title}</h3>
        </div>
        {children}
      </div>
    </motion.div>
  );
}

function Tag({ label, value, color }) {
  if (!value) return null;
  const colors = {
    indigo: "bg-indigo-50 text-indigo-600 border-indigo-100 dark:bg-indigo-500/10 dark:text-indigo-400 dark:border-indigo-500/20",
    blue: "bg-blue-50 text-blue-600 border-blue-100 dark:bg-blue-500/10 dark:text-blue-400 dark:border-blue-500/20",
    emerald: "bg-emerald-50 text-emerald-600 border-emerald-100 dark:bg-emerald-500/10 dark:text-emerald-400 dark:border-emerald-500/20",
    purple: "bg-purple-50 text-purple-600 border-purple-100 dark:bg-purple-500/10 dark:text-purple-400 dark:border-purple-500/20",
  };
  return (
    <div className={`px-2.5 py-1.5 rounded-xl border text-[10px] font-black uppercase tracking-wider ${colors[color] || colors.indigo} shadow-sm`}>
      <span className="opacity-50 mr-1.5 font-bold">{label}:</span>
      {value}
    </div>
  );
}
