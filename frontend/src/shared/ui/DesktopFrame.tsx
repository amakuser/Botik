import { getCurrentWindow } from "@tauri-apps/api/window";
import { PropsWithChildren, useCallback, useEffect, useMemo, useState } from "react";
import { isDesktopRuntime } from "../host";

async function runWindowAction(action: () => Promise<void>) {
  try {
    await action();
  } catch (error) {
    console.error("Desktop window action failed", error);
  }
}

export function DesktopFrame({ children }: PropsWithChildren) {
  const desktop = isDesktopRuntime();
  const appWindow = useMemo(() => (desktop ? getCurrentWindow() : null), [desktop]);
  const [isMaximized, setIsMaximized] = useState(false);

  const syncMaximizedState = useCallback(async () => {
    if (!appWindow) {
      return;
    }

    try {
      setIsMaximized(await appWindow.isMaximized());
    } catch (error) {
      console.error("Failed to read desktop maximize state", error);
    }
  }, [appWindow]);

  useEffect(() => {
    if (!appWindow) {
      return;
    }

    let mounted = true;
    let unlisten: (() => void) | undefined;

    const sync = async () => {
      try {
        const nextValue = await appWindow.isMaximized();
        if (mounted) {
          setIsMaximized(nextValue);
        }
      } catch (error) {
        console.error("Failed to sync desktop maximize state", error);
      }
    };

    void sync();
    void appWindow.onResized(() => {
      void sync();
    }).then((listener) => {
      unlisten = listener;
    });

    return () => {
      mounted = false;
      unlisten?.();
    };
  }, [appWindow, syncMaximizedState]);

  const handleToggleMaximize = useCallback(() => {
    if (!appWindow) {
      return;
    }

    void runWindowAction(async () => {
      await appWindow.toggleMaximize();
      await syncMaximizedState();
    });
  }, [appWindow, syncMaximizedState]);

  const handleMinimize = useCallback(() => {
    if (!appWindow) {
      return;
    }

    void runWindowAction(() => appWindow.minimize());
  }, [appWindow]);

  const handleClose = useCallback(() => {
    if (!appWindow) {
      return;
    }

    void runWindowAction(() => appWindow.close());
  }, [appWindow]);

  if (!desktop) {
    return <>{children}</>;
  }

  return (
    <div
      className={isMaximized ? "desktop-frame is-maximized" : "desktop-frame"}
      data-testid="foundation.desktop-frame"
    >
      <header className="desktop-frame__titlebar" data-testid="foundation.desktop-titlebar">
        <div
          className="desktop-frame__drag-surface"
          data-tauri-drag-region
          onDoubleClick={handleToggleMaximize}
        >
          <div className="desktop-frame__brand-lockup">
            <p className="desktop-frame__eyebrow">Primary Desktop Shell</p>
            <div className="desktop-frame__brand-row">
              <strong className="desktop-frame__brand">Botik Foundation</strong>
              <span className="desktop-frame__window-state">
                {isMaximized ? "Maximized" : "Windowed"} workspace
              </span>
            </div>
          </div>
        </div>

        <div className="desktop-frame__window-controls" aria-label="Window controls">
          <button
            type="button"
            className="desktop-frame__window-control"
            aria-label="Minimize window"
            onClick={handleMinimize}
          >
            <span className="desktop-frame__window-icon desktop-frame__window-icon--minimize" aria-hidden="true" />
          </button>
          <button
            type="button"
            className="desktop-frame__window-control"
            aria-label={isMaximized ? "Restore window" : "Maximize window"}
            onClick={handleToggleMaximize}
          >
            <span
              className={
                isMaximized
                  ? "desktop-frame__window-icon desktop-frame__window-icon--restore"
                  : "desktop-frame__window-icon desktop-frame__window-icon--maximize"
              }
              aria-hidden="true"
            />
          </button>
          <button
            type="button"
            className="desktop-frame__window-control desktop-frame__window-control--close"
            aria-label="Close window"
            onClick={handleClose}
          >
            <span className="desktop-frame__window-icon desktop-frame__window-icon--close" aria-hidden="true" />
          </button>
        </div>
      </header>

      <div className="desktop-frame__body">{children}</div>
    </div>
  );
}
