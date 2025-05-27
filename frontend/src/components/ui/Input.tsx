import React from "react";

interface InputProps {
  value: string;
  onChange: (e: React.ChangeEvent<HTMLInputElement>) => void;
  type?: string;
  className?: string;
}

const Input: React.FC<InputProps> = ({ value, onChange, type = "text", className }) => {
  return (
    <input
      type={type}
      value={value}
      onChange={onChange}
      className={`w-full px-3 py-2 border rounded-md text-sm ${className}`}
    />
  );
};

export default Input;