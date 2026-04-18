import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "../../lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 rounded-full text-sm font-semibold transition-all duration-150 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 disabled:pointer-events-none disabled:opacity-45",
  {
    variants: {
      variant: {
        primary:
          "bg-gradient-to-b from-[#e4dbc9] to-[#b8aa8d] text-[#14161a] shadow-[inset_0_1px_0_rgba(255,255,255,0.28),0_12px_28px_rgba(0,0,0,0.18)] hover:-translate-y-px hover:shadow-[inset_0_1px_0_rgba(255,255,255,0.34),0_16px_30px_rgba(0,0,0,0.22)]",
        secondary:
          "bg-[rgba(23,28,34,0.92)] border border-[rgba(201,209,220,0.16)] text-[#eef2f7] hover:-translate-y-px hover:border-[rgba(215,203,177,0.22)] hover:bg-[rgba(28,33,40,0.96)]",
        ghost:
          "text-[var(--text-secondary)] hover:bg-[rgba(215,203,177,0.08)] hover:text-[var(--text-primary)]",
        destructive:
          "bg-[rgba(248,113,113,0.16)] border border-[rgba(248,113,113,0.24)] text-[#fecaca] hover:bg-[rgba(248,113,113,0.22)]",
      },
      size: {
        sm: "h-8 px-3 text-xs",
        md: "h-10 px-4",
        lg: "h-11 px-6 text-base",
      },
    },
    defaultVariants: { variant: "secondary", size: "md" },
  }
);

interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : "button";
    return (
      <Comp
        className={cn(buttonVariants({ variant, size, className }))}
        ref={ref}
        {...props}
      />
    );
  }
);
Button.displayName = "Button";

export { buttonVariants };
