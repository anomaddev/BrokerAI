import { useCallback, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ROUTES } from "../lib/routes";

/** Close the strategy builder, confirming first when there are unsaved changes. */
export function useStrategyBuilderExit(
  isDirty: boolean,
  exitTo: string = ROUTES.research.strategies,
) {
  const navigate = useNavigate();
  const [confirmOpen, setConfirmOpen] = useState(false);

  const leave = useCallback(() => {
    navigate(exitTo);
  }, [navigate, exitTo]);

  const requestClose = useCallback(() => {
    if (isDirty) {
      setConfirmOpen(true);
      return;
    }
    leave();
  }, [isDirty, leave]);

  const cancelDiscard = useCallback(() => {
    setConfirmOpen(false);
  }, []);

  return {
    requestClose,
    discardConfirmOpen: confirmOpen,
    confirmDiscard: leave,
    cancelDiscard,
  };
}
