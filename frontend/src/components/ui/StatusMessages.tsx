import React from 'react';
import { useNavigate } from 'react-router-dom';

export function CenteredMessage({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex-1 flex items-center justify-center">
      <div className="text-gray-500">{children}</div>
    </div>
  );
}

export function EmptyState(props: {
  message: string;
  actionLabel: string;
  action?: () => void;
}) {
  const navigate = useNavigate();
  
  const handleAction = () => {
    if (props.action) {
      props.action();
    } else {
      navigate('/');
    }
  };

  return (
    <div className="flex-1 flex items-center justify-center bg-gray-50">
      <div className="bg-white shadow rounded-xl p-8 space-y-6 text-center max-w-md">
        <p className="text-gray-600">{props.message}</p>
        <button
          onClick={handleAction}
          className="px-4 py-2 bg-gray-800 text-white rounded-lg hover:bg-gray-700"
        >
          {props.actionLabel}
        </button>
      </div>
    </div>
  );
}
