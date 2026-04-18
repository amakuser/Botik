export const motionTokens = {
  duration: {
    fast: 0.08,
    base: 0.15,
    slow: 0.28,
    page: 0.22,
  },
  ease: {
    out: [0.0, 0.0, 0.2, 1] as const,
    spring: { type: "spring" as const, stiffness: 400, damping: 30 },
    springBounce: { type: "spring" as const, stiffness: 600, damping: 35 },
  },
} as const;

export const fadeIn = {
  initial: { opacity: 0, y: 6 },
  animate: { opacity: 1, y: 0 },
  exit: { opacity: 0, y: -4 },
  transition: { duration: motionTokens.duration.page, ease: motionTokens.ease.out },
};

export const fadeInFast = {
  initial: { opacity: 0 },
  animate: { opacity: 1 },
  exit: { opacity: 0 },
  transition: { duration: motionTokens.duration.base },
};

export const scaleIn = {
  initial: { opacity: 0, scale: 0.97 },
  animate: { opacity: 1, scale: 1 },
  exit: { opacity: 0, scale: 0.97 },
  transition: { duration: motionTokens.duration.base, ease: motionTokens.ease.out },
};

export const slideInLeft = {
  initial: { opacity: 0, x: -10 },
  animate: { opacity: 1, x: 0 },
  exit: { opacity: 0, x: -10 },
  transition: { duration: motionTokens.duration.slow, ease: motionTokens.ease.out },
};

export const staggerContainer = {
  animate: { transition: { staggerChildren: 0.06 } },
};

export const staggerItem = {
  initial: { opacity: 0, y: 8 },
  animate: { opacity: 1, y: 0 },
  transition: { duration: motionTokens.duration.slow, ease: motionTokens.ease.out },
};
