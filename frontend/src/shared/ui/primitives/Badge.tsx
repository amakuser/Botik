import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "../../lib/utils";

const badgeVariants = cva(
  "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold border transition-colors",
  {
    variants: {
      variant: {
        default:
          "bg-[rgba(215,203,177,0.1)] border-[rgba(215,203,177,0.18)] text-[#ece2cb]",
        success:
          "bg-[rgba(34,197,94,0.14)] border-[rgba(34,197,94,0.24)] text-[#86efac]",
        error:
          "bg-[rgba(248,113,113,0.14)] border-[rgba(248,113,113,0.2)] text-[#fecaca]",
        warning:
          "bg-[rgba(217,119,6,0.16)] border-[rgba(245,158,11,0.18)] text-[#fde68a]",
        muted:
          "bg-[rgba(15,23,42,0.82)] border-[rgba(148,163,184,0.14)] text-[#94a3b8]",
      },
    },
    defaultVariants: { variant: "default" },
  }
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof badgeVariants> {}

export function Badge({ className, variant, ...props }: BadgeProps) {
  return <div className={cn(badgeVariants({ variant }), className)} {...props} />;
}
