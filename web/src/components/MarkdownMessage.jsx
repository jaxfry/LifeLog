import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkBreaks from 'remark-breaks';

const components = {
  pre: ({ children }) => (
    <pre className="my-3 overflow-x-auto rounded-lg bg-gray-800 p-3 text-sm text-gray-100">
      {children}
    </pre>
  ),
  code: ({ className, children, ...props }) => {
    const isBlock = /language-(\w+)/.test(className || '') || String(children).includes('\n');
    if (isBlock) {
      return (
        <code className={className} {...props}>
          {children}
        </code>
      );
    }
    return (
      <code
        className="rounded bg-gray-200 px-1.5 py-0.5 text-[0.875em] text-gray-800"
        {...props}
      >
        {children}
      </code>
    );
  },
  h1: ({ children }) => (
    <h1 className="mt-4 mb-2 text-xl font-bold text-gray-900">{children}</h1>
  ),
  h2: ({ children }) => (
    <h2 className="mt-4 mb-2 text-lg font-bold text-gray-900">{children}</h2>
  ),
  h3: ({ children }) => (
    <h3 className="mt-3 mb-1.5 text-base font-semibold text-gray-900">{children}</h3>
  ),
  h4: ({ children }) => (
    <h4 className="mt-3 mb-1.5 text-sm font-semibold text-gray-900">{children}</h4>
  ),
  h5: ({ children }) => (
    <h5 className="mt-3 mb-1.5 text-sm font-semibold text-gray-900">{children}</h5>
  ),
  h6: ({ children }) => (
    <h6 className="mt-3 mb-1.5 text-sm font-semibold text-gray-900">{children}</h6>
  ),
  p: ({ children }) => <p className="my-2 leading-relaxed">{children}</p>,
  ul: ({ children }) => <ul className="my-2 list-disc space-y-1 pl-5">{children}</ul>,
  ol: ({ children }) => <ol className="my-2 list-decimal space-y-1 pl-5">{children}</ol>,
  li: ({ children }) => <li className="my-0.5">{children}</li>,
  blockquote: ({ children }) => (
    <blockquote className="my-3 border-l-4 border-gray-300 pl-4 text-gray-700 italic">
      {children}
    </blockquote>
  ),
  hr: () => <hr className="my-4 border-gray-300" />,
  a: ({ children, href }) => (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="text-blue-600 underline hover:text-blue-800"
    >
      {children}
    </a>
  ),
  table: ({ children }) => (
    <div className="my-3 overflow-x-auto">
      <table className="min-w-full divide-y divide-gray-300 rounded-lg border border-gray-300 text-sm">
        {children}
      </table>
    </div>
  ),
  thead: ({ children }) => <thead className="bg-gray-200">{children}</thead>,
  th: ({ children }) => (
    <th className="px-3 py-2 text-left font-semibold text-gray-900">{children}</th>
  ),
  td: ({ children }) => <td className="border-t border-gray-300 px-3 py-2">{children}</td>,
};

const MarkdownMessage = ({ content }) => (
  <div className="break-words">
    <ReactMarkdown remarkPlugins={[remarkGfm, remarkBreaks]} components={components}>
      {content}
    </ReactMarkdown>
  </div>
);

export default MarkdownMessage;