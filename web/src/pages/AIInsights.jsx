import { useState } from 'react';
import { useQuery, useMutation } from '@tanstack/react-query';
import { aiChatAPI, lifeAreasAPI } from '../services/api';
import { Sparkles, Send, AlertCircle, MessageCircle, Loader, Database, Wrench } from 'lucide-react';
import MarkdownMessage from '../components/MarkdownMessage';

const AIInsights = () => {
  const [messages, setMessages] = useState([]);
  const [inputMessage, setInputMessage] = useState('');
  const [lifeAreaId, setLifeAreaId] = useState('');
  const { data: lifeAreas = [] } = useQuery({ queryKey: ['life-areas'], queryFn: lifeAreasAPI.list });

  // Check AI health
  const { data: health } = useQuery({
    queryKey: ['ai-health'],
    queryFn: aiChatAPI.checkHealth,
  });

  // Chat mutation
  const chatMutation = useMutation({
    mutationFn: aiChatAPI.sendMessage,
    onSuccess: (data) => {
      setMessages(prev => [
        ...prev,
        {
          role: 'assistant',
          content: data.response,
          contextUsed: data.context_used,
          citations: data.citations || [],
          retrieval: data.retrieval || {},
        }
      ]);
    },
    onError: (error) => {
      setMessages(prev => [
        ...prev,
        { 
          role: 'error', 
          content: `Error: ${error.response?.data?.detail || error.message || 'Failed to get response'}`
        }
      ]);
    }
  });

  const handleSend = () => {
    if (!inputMessage.trim()) return;

    const message = inputMessage.trim();
    const history = messages
      .filter(item => item.role === 'user' || item.role === 'assistant')
      .slice(-12)
      .map(({ role, content }) => ({ role, content }));
    setMessages(prev => [...prev, { role: 'user', content: message }]);
    setInputMessage('');
    chatMutation.mutate({
      message,
      history,
      lifeAreaId: lifeAreaId || null,
      timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC',
    });
  };

  const handleKeyPress = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const suggestedQuestions = [
    "What unfinished work do I have?",
    "What did I work on yesterday?",
    "How have my study habits changed over time?",
    "What do my notes say about the topics I've been learning?",
    "What should I focus on next?",
  ];

  const handleSuggestion = (question) => {
    setInputMessage(question);
  };

  if (!health?.configured) {
    return (
      <div className="max-w-4xl mx-auto">
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-gray-900 mb-2">AI Insights</h1>
          <p className="text-gray-600">Chat with LifeLog AI about your data</p>
        </div>
        
        <div className="card bg-yellow-50 border-2 border-yellow-200">
          <div className="flex items-start gap-3">
            <AlertCircle className="text-yellow-600 flex-shrink-0 mt-1" size={24} />
            <div>
              <h3 className="font-semibold text-gray-900 mb-2">AI Service Not Configured</h3>
              <p className="text-sm text-gray-700">
                The AI service requires a valid API key to function. Please configure your GEMINI_API_KEY 
                in the system settings or environment variables.
              </p>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto h-[calc(100vh-8rem)] flex flex-col">
      {/* Header */}
      <div className="mb-6">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 bg-gradient-to-br from-purple-500 to-pink-500 rounded-lg flex items-center justify-center">
            <Sparkles className="text-white" size={24} />
          </div>
          <div>
            <h1 className="text-3xl font-bold text-gray-900">AI Insights</h1>
            <p className="text-gray-600">Ask across your lifetime. LifeLog finds the right memories automatically.</p>
          </div>
        </div>
      </div>

      <div className="mb-4 flex flex-wrap items-center gap-2">
        <label className="text-sm font-medium text-gray-700" htmlFor="chat-scope">
          Scope
        </label>
        <select
          id="chat-scope"
          value={lifeAreaId}
          onChange={(e) => setLifeAreaId(e.target.value)}
          className="px-3 py-1 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500"
        >
          <option value="">Whole life</option>
          {lifeAreas.map((area) => <option key={area.id} value={area.id}>{area.name}</option>)}
        </select>
        <span className="text-xs text-gray-500">
          Time ranges come from your question; only relevant, permitted memories are retrieved.
        </span>
      </div>

      {/* Messages Area */}
      <div className="flex-1 card overflow-y-auto mb-4" style={{ minHeight: '400px' }}>
        {messages.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-center p-8">
            <div className="w-16 h-16 bg-gradient-to-br from-purple-500 to-pink-500 rounded-full flex items-center justify-center mb-4">
              <MessageCircle className="text-white" size={32} />
            </div>
            <h3 className="text-xl font-semibold text-gray-900 mb-2">Start a conversation</h3>
            <p className="text-gray-600 mb-6 max-w-md">
              Ask LifeLog AI about your activities, patterns, and insights from your personal data.
            </p>
            
            {/* Suggested Questions */}
            <div className="w-full max-w-xl">
              <p className="text-sm font-medium text-gray-700 mb-3">Suggested questions:</p>
              <div className="space-y-2">
                {suggestedQuestions.map((question, idx) => (
                  <button
                    key={idx}
                    onClick={() => handleSuggestion(question)}
                    className="w-full text-left px-4 py-3 bg-gray-50 hover:bg-gray-100 rounded-lg text-sm text-gray-700 transition-colors"
                  >
                    {question}
                  </button>
                ))}
              </div>
            </div>
          </div>
        ) : (
          <div className="space-y-4">
            {messages.map((message, idx) => (
              <div
                key={idx}
                className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}
              >
                <div
                  className={`max-w-[80%] rounded-lg p-4 ${
                    message.role === 'user'
                      ? 'bg-blue-600 text-white'
                      : message.role === 'error'
                      ? 'bg-red-50 border border-red-200 text-red-700'
                      : 'bg-gray-100 text-gray-900'
                  }`}
                >
                  {message.role === 'assistant' && (
                    <div className="flex items-center gap-2 mb-2">
                      <Sparkles className="text-purple-600" size={16} />
                      <span className="text-xs font-semibold text-purple-600">LifeLog AI</span>
                      {message.contextUsed && message.retrieval && (
                        <span className="text-xs text-gray-500">
                          {message.retrieval.scope} · {message.retrieval.time_scope} · {message.retrieval.mode}
                        </span>
                      )}
                    </div>
                  )}
                  {message.role === 'assistant' ? (
                    <MarkdownMessage content={message.content} />
                  ) : (
                    <div className="whitespace-pre-wrap">{message.content}</div>
                  )}
                  {message.role === 'assistant' && message.citations?.length > 0 && (
                    <div className="mt-3 pt-3 border-t border-gray-200 flex flex-wrap gap-2">
                      {message.citations.map((citation) => (
                        <span
                          key={citation.id}
                          title={citation.locator ? JSON.stringify(citation.locator) : undefined}
                          className="inline-flex items-center gap-1 rounded-full bg-white px-2 py-1 text-xs text-gray-600 border border-gray-200"
                        >
                          {citation.tool ? <Wrench size={12} /> : <Database size={12} />}
                          <strong>[{citation.id}]</strong>
                          {citation.filename || citation.title || citation.tool || citation.source_type}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            ))}
            
            {chatMutation.isPending && (
              <div className="flex justify-start">
                <div className="max-w-[80%] bg-gray-100 rounded-lg p-4">
                  <div className="flex items-center gap-2">
                    <Loader className="animate-spin text-purple-600" size={16} />
                    <span className="text-sm text-gray-600">AI is thinking...</span>
                  </div>
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Input Area */}
      <div className="card">
        <div className="flex gap-3">
          <textarea
            value={inputMessage}
            onChange={(e) => setInputMessage(e.target.value)}
            onKeyPress={handleKeyPress}
            placeholder="Ask anything about your life, or name a time range naturally..."
            className="flex-1 px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent resize-none"
            rows={2}
            disabled={chatMutation.isPending}
          />
          <button
            onClick={handleSend}
            disabled={!inputMessage.trim() || chatMutation.isPending}
            className="btn-primary px-6 self-end disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <Send size={20} />
          </button>
        </div>
        <p className="text-xs text-gray-500 mt-2">
          Press Enter to send, Shift+Enter for new line
        </p>
      </div>
    </div>
  );
};

export default AIInsights;
