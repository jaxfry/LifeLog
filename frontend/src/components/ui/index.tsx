import React from 'react';
import { cva, type VariantProps } from 'class-variance-authority';
import { cn } from '../../lib/utils';

/* ────────────────────────────────────────────────────────────────────────── */
/*  Button Component Variants                                                */
/* ────────────────────────────────────────────────────────────────────────── */

const buttonVariants = cva(
  // Base styles
  "inline-flex items-center justify-center rounded-md text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50",
  {
    variants: {
      variant: {
        primary: "bg-primary-500 text-on-primary hover:bg-primary-600 active:bg-primary-700",
        secondary: "bg-neutral-200 text-neutral-900 hover:bg-neutral-300 active:bg-neutral-400",
        outline: "border border-primary-500 text-primary-500 hover:bg-primary-50 active:bg-primary-100",
        ghost: "text-primary-500 hover:bg-primary-50 active:bg-primary-100",
        danger: "bg-error-500 text-on-error hover:bg-error-600 active:bg-error-700",
        success: "bg-success-500 text-on-success hover:bg-success-600 active:bg-success-700",
      },
      size: {
        sm: "h-8 px-3 text-xs",
        md: "h-10 px-4 py-2",
        lg: "h-11 px-8",
        xl: "h-12 px-10 text-base",
        icon: "h-10 w-10",
      },
    },
    defaultVariants: {
      variant: "primary",
      size: "md",
    },
  }
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

export function Button({
  className,
  variant,
  size,
  asChild = false,
  ...props
}: ButtonProps) {
  return (
    <button
      className={cn(buttonVariants({ variant, size, className }))}
      {...props}
    />
  );
}

/* ────────────────────────────────────────────────────────────────────────── */
/*  Card Component                                                           */
/* ────────────────────────────────────────────────────────────────────────── */

const cardVariants = cva(
  "rounded-lg border bg-surface-primary text-on-surface shadow-sm",
  {
    variants: {
      variant: {
        default: "border-neutral-200",
        elevated: "border-neutral-200 shadow-md",
        interactive: "border-neutral-200 hover:shadow-md transition-shadow cursor-pointer",
        outlined: "border-2 border-primary-200 bg-primary-50/50",
      },
      padding: {
        none: "",
        sm: "p-4",
        md: "p-6",
        lg: "p-8",
      },
    },
    defaultVariants: {
      variant: "default",
      padding: "md",
    },
  }
);

export interface CardProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof cardVariants> {}

export function Card({ className, variant, padding, ...props }: CardProps) {
  return (
    <div
      className={cn(cardVariants({ variant, padding, className }))}
      {...props}
    />
  );
}

export function CardHeader({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn("flex flex-col space-y-1.5 p-6", className)}
      {...props}
    />
  );
}

export function CardTitle({
  className,
  ...props
}: React.HTMLAttributes<HTMLHeadingElement>) {
  return (
    <h3
      className={cn("text-2xl font-semibold leading-none tracking-tight", className)}
      {...props}
    />
  );
}

export function CardDescription({
  className,
  ...props
}: React.HTMLAttributes<HTMLParagraphElement>) {
  return (
    <p
      className={cn("text-sm text-on-surface-variant", className)}
      {...props}
    />
  );
}

export function CardContent({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("p-6 pt-0", className)} {...props} />;
}

export function CardFooter({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn("flex items-center p-6 pt-0", className)}
      {...props}
    />
  );
}

/* ────────────────────────────────────────────────────────────────────────── */
/*  Badge Component                                                          */
/* ────────────────────────────────────────────────────────────────────────── */

const badgeVariants = cva(
  "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2",
  {
    variants: {
      variant: {
        default: "bg-primary-100 text-primary-700 hover:bg-primary-200",
        secondary: "bg-neutral-100 text-neutral-700 hover:bg-neutral-200",
        success: "bg-success-100 text-success-700 hover:bg-success-200",
        warning: "bg-warning-100 text-warning-700 hover:bg-warning-200",
        error: "bg-error-100 text-error-700 hover:bg-error-200",
        outline: "border border-neutral-300 text-neutral-700 hover:bg-neutral-50",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  }
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof badgeVariants> {}

export function Badge({ className, variant, ...props }: BadgeProps) {
  return (
    <div className={cn(badgeVariants({ variant }), className)} {...props} />
  );
}

/* ────────────────────────────────────────────────────────────────────────── */
/*  Input Component                                                          */
/* ────────────────────────────────────────────────────────────────────────── */

const inputVariants = cva(
  "flex h-10 w-full rounded-md border px-3 py-2 text-sm ring-offset-surface-primary file:border-0 file:bg-transparent file:text-sm file:font-medium placeholder:text-neutral-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50",
  {
    variants: {
      variant: {
        default: "border-neutral-300 bg-surface-primary focus-visible:ring-primary-500",
        error: "border-error-500 bg-surface-primary focus-visible:ring-error-500",
        success: "border-success-500 bg-surface-primary focus-visible:ring-success-500",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  }
);

export interface InputProps
  extends React.InputHTMLAttributes<HTMLInputElement>,
    VariantProps<typeof inputVariants> {}

export const Input = React.forwardRef<HTMLInputElement, InputProps>(
  ({ className, variant, type, ...props }, ref) => {
    return (
      <input
        type={type}
        className={cn(inputVariants({ variant, className }))}
        ref={ref}
        {...props}
      />
    );
  }
);
Input.displayName = "Input";

/* ────────────────────────────────────────────────────────────────────────── */
/*  Label Component                                                          */
/* ────────────────────────────────────────────────────────────────────────── */

export interface LabelProps
  extends React.LabelHTMLAttributes<HTMLLabelElement> {}

export const Label = React.forwardRef<HTMLLabelElement, LabelProps>(
  ({ className, ...props }, ref) => (
    <label
      ref={ref}
      className={cn(
        "text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70",
        className
      )}
      {...props}
    />
  )
);
Label.displayName = "Label";

/* ────────────────────────────────────────────────────────────────────────── */
/*  Skeleton Component                                                       */
/* ────────────────────────────────────────────────────────────────────────── */

export function Skeleton({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn("animate-pulse rounded-md bg-surface-light", className)}
      {...props}
    />
  );
}

/* ────────────────────────────────────────────────────────────────────────── */
/*  Separator Component                                                      */
/* ────────────────────────────────────────────────────────────────────────── */

export interface SeparatorProps
  extends React.HTMLAttributes<HTMLDivElement> {
  orientation?: "horizontal" | "vertical";
}

export function Separator({
  className,
  orientation = "horizontal",
  ...props
}: SeparatorProps) {
  return (
    <div
      className={cn(
        "shrink-0 bg-neutral-200",
        orientation === "horizontal" ? "h-[1px] w-full" : "h-full w-[1px]",
        className
      )}
      {...props}
    />
  );
}
