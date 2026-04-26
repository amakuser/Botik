import { cn } from "../../../shared/lib/utils";

export interface SkeletonBoxProps {
  className?: string;
  scope: string;
  rounded?: boolean;
  height?: string;
  width?: string;
  ariaLabel?: string;
}

export function SkeletonBox({
  className,
  scope,
  rounded = true,
  height,
  width,
  ariaLabel = "Загрузка",
}: SkeletonBoxProps) {
  return (
    <div
      role="status"
      aria-label={ariaLabel}
      data-ui-role="skeleton"
      data-ui-scope={scope}
      style={{
        height: height ?? "1rem",
        width: width ?? "100%",
      }}
      className={cn(
        "bg-white/5 motion-safe:animate-pulse",
        rounded ? "rounded-md" : "rounded-none",
        className,
      )}
    />
  );
}
