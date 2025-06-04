import React from 'react';
import { useNavigate } from 'react-router-dom';
import { Button } from './index'; // Import CVA Button

export interface CenteredMessageProps {
  children: React.ReactNode;
  className?: string;
}

export function CenteredMessage({ children, className = "" }: CenteredMessageProps) {
  return (
    <section 
      className={`flex-1 flex items-center justify-center ${className}`}
      role="status"
      aria-live="polite"
    >
      <div className="text-secondary">{children}</div>
    </section>
  );
}

export interface EmptyStateProps {
  message: string;
  actionLabel: string;
  action?: () => void;
  className?: string;
}

export function EmptyState({ 
  message, 
  actionLabel, 
  action,
  className = ""
}: EmptyStateProps) {
  const navigate = useNavigate();
  
  const handleAction = () => {
    if (action) {
      action();
    } else {
      navigate('/');
    }
  };

  return (
    <section 
      className={`flex-1 flex items-center justify-center bg-background-secondary ${className}`}
      role="status"
      aria-live="polite"
    >
      <div className="bg-surface-primary shadow rounded-xl p-8 space-y-6 text-center max-w-md">
        <p className="text-secondary">{message}</p>
        <Button
          onClick={handleAction}
          variant="primary"
        >
          {actionLabel}
        </Button>
      </div>
    </section>
  );
}

// Additional semantic status components
export interface LoadingStateProps {
  message?: string;
  className?: string;
}

export function LoadingState({ 
  message = "Loading...", 
  className = "" 
}: LoadingStateProps) {
  return (
    <section 
      className={`flex-1 flex items-center justify-center ${className}`}
      role="status"
      aria-live="polite"
      aria-label={message}
    >
      <div className="text-center">
        <div className="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-primary-500 mb-4" aria-hidden="true"></div>
        <p className="text-secondary">{message}</p>
      </div>
    </section>
  );
}
