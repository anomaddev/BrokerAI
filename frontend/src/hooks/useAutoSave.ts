import { useCallback, useEffect, useRef, useState } from "react";

type UseAutoSaveOptions = {
  onSave: () => Promise<void>;
  canSave?: () => boolean;
  defaultDebounceMs?: number;
  savedFlashMs?: number;
};

export default function useAutoSave({
  onSave,
  canSave,
  defaultDebounceMs = 300,
  savedFlashMs = 2000,
}: UseAutoSaveOptions) {
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [savedVisible, setSavedVisible] = useState(false);

  const skipSaveRef = useRef(true);
  const saveTimerRef = useRef<number | null>(null);
  const saveChainRef = useRef<Promise<void>>(Promise.resolve());
  const savedTimerRef = useRef<number | null>(null);
  const onSaveRef = useRef(onSave);
  const canSaveRef = useRef(canSave);

  onSaveRef.current = onSave;
  canSaveRef.current = canSave;

  const clearSavedTimer = useCallback(() => {
    if (savedTimerRef.current) {
      window.clearTimeout(savedTimerRef.current);
      savedTimerRef.current = null;
    }
  }, []);

  const flashSaved = useCallback(() => {
    clearSavedTimer();
    setSavedVisible(true);
    savedTimerRef.current = window.setTimeout(() => {
      savedTimerRef.current = null;
      setSavedVisible(false);
    }, savedFlashMs);
  }, [clearSavedTimer, savedFlashMs]);

  const enqueueSave = useCallback(() => {
    if (skipSaveRef.current) return;

    saveChainRef.current = saveChainRef.current
      .then(async () => {
        if (canSaveRef.current && !canSaveRef.current()) return;

        setSaving(true);
        try {
          await onSaveRef.current();
          setError(null);
          flashSaved();
        } catch (err) {
          setError(err instanceof Error ? err.message : "Failed to save");
        } finally {
          setSaving(false);
        }
      })
      .catch(() => {
        // Keep the chain alive after a rejected save.
      });
  }, [flashSaved]);

  const scheduleSave = useCallback(
    (debounceMs?: number) => {
      if (skipSaveRef.current) return;

      if (saveTimerRef.current) {
        window.clearTimeout(saveTimerRef.current);
      }

      const delay = debounceMs !== undefined && debounceMs > 0 ? debounceMs : defaultDebounceMs;
      saveTimerRef.current = window.setTimeout(() => {
        saveTimerRef.current = null;
        enqueueSave();
      }, delay);
    },
    [defaultDebounceMs, enqueueSave],
  );

  const saveNow = useCallback(() => {
    if (skipSaveRef.current) return;

    if (saveTimerRef.current) {
      window.clearTimeout(saveTimerRef.current);
      saveTimerRef.current = null;
    }

    enqueueSave();
  }, [enqueueSave]);

  const markReady = useCallback(() => {
    skipSaveRef.current = false;
  }, []);

  const markNotReady = useCallback(() => {
    skipSaveRef.current = true;
    if (saveTimerRef.current) {
      window.clearTimeout(saveTimerRef.current);
      saveTimerRef.current = null;
    }
  }, []);

  const clearError = useCallback(() => {
    setError(null);
  }, []);

  useEffect(() => {
    return () => {
      if (saveTimerRef.current) {
        window.clearTimeout(saveTimerRef.current);
      }
      clearSavedTimer();
    };
  }, [clearSavedTimer]);

  const saveStatus: "idle" | "saving" | "saved" | "error" = error
    ? "error"
    : saving
      ? "saving"
      : savedVisible
        ? "saved"
        : "idle";

  return {
    saving,
    error,
    savedVisible,
    saveStatus,
    clearError,
    markReady,
    markNotReady,
    scheduleSave,
    saveNow,
  };
}
