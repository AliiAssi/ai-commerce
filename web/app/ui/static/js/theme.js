tailwind.config = {
  theme: {
    extend: {
      colors: {
        brand: {
          DEFAULT: "rgb(var(--c-brand) / <alpha-value>)",
          hover: "rgb(var(--c-brand-hover) / <alpha-value>)",
          subtle: "rgb(var(--c-brand-subtle) / <alpha-value>)",
          contrast: "rgb(var(--c-brand-contrast) / <alpha-value>)",
        },
        surface: {
          DEFAULT: "rgb(var(--c-surface) / <alpha-value>)",
          alt: "rgb(var(--c-surface-alt) / <alpha-value>)",
          sunk: "rgb(var(--c-sunk) / <alpha-value>)",
        },
        ink: {
          DEFAULT: "rgb(var(--c-ink) / <alpha-value>)",
          muted: "rgb(var(--c-ink-muted) / <alpha-value>)",
          faint: "rgb(var(--c-ink-faint) / <alpha-value>)",
        },
        border: "rgb(var(--c-border) / <alpha-value>)",
        /* material tones — product plates only, never the interface */
        clay: "rgb(var(--c-clay) / <alpha-value>)",
        sea: "rgb(var(--c-sea) / <alpha-value>)",
        danger: {
          DEFAULT: "rgb(var(--c-danger) / <alpha-value>)",
          subtle: "rgb(var(--c-danger-subtle) / <alpha-value>)",
        },
        success: {
          DEFAULT: "rgb(var(--c-success) / <alpha-value>)",
          subtle: "rgb(var(--c-success-subtle) / <alpha-value>)",
        },
        warning: {
          DEFAULT: "rgb(var(--c-warning) / <alpha-value>)",
          subtle: "rgb(var(--c-warning-subtle) / <alpha-value>)",
        },
        star: "rgb(var(--c-star) / <alpha-value>)",
        sidebar: {
          DEFAULT: "rgb(var(--c-sidebar) / <alpha-value>)",
          ink: "rgb(var(--c-sidebar-ink) / <alpha-value>)",
          "ink-active": "rgb(var(--c-sidebar-ink-active) / <alpha-value>)",
          active: "rgb(var(--c-sidebar-active) / <alpha-value>)",
        },
      },
      borderRadius: {
        el: "var(--radius-el)",
        card: "var(--radius-card)",
      },
      boxShadow: {
        card: "var(--shadow-card)",
        pop: "var(--shadow-pop)",
      },
      backgroundImage: {
        assistant: "var(--asset-assistant)",
      },
      fontFamily: {
        serif: "var(--font-serif)",
        sans: "var(--font-sans)",
      },
      maxWidth: {
        shell: "var(--container-max)",
      },
      letterSpacing: {
        tight: "var(--tracking-tight)",
        snug: "var(--tracking-snug)",
        wide: "var(--tracking-wide)",
        label: "var(--tracking-label)",
        mark: "var(--tracking-mark)",
      },
      fontSize: {
        display: "var(--text-display)",
        title: "var(--text-title)",
        mark: "var(--text-mark)",
      },
      transitionTimingFunction: {
        rise: "var(--ease-rise)",
        soft: "var(--ease-soft)",
      },
      transitionDuration: {
        fast: "var(--motion-fast)",
        base: "var(--motion-base)",
        slow: "var(--motion-slow)",
      },
    },
  },
};
